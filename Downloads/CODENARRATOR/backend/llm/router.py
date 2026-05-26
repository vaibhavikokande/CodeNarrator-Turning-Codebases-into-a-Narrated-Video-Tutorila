"""
Multi-provider LLM router with rate pacing + cache + failover.

Provider priority (LLM_PROVIDER env var):
  gemini     -> Google Gemini 2.5 Flash (default)
  claude     -> Anthropic Claude
  openrouter -> OpenRouter

Failover: Gemini -> OpenRouter  (or Claude -> Gemini -> OpenRouter)
"""

import asyncio
import collections
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from .claude_client import ClaudeClient, ClaudeRateLimitError, ClaudeUnavailableError
from .gemini_client import GeminiClient, GeminiRateLimitError, GeminiUnavailableError
from .openrouter_client import OpenRouterClient, OpenRouterError

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).parent.parent / "llm_cache.json"

_MAX_RPM_CLAUDE  = 40   # Claude Tier-1 target
_MAX_RPM_GEMINI  = 8    # Gemini 2.5 Flash free tier target (10 RPM hard limit)
_WINDOW_SECS     = 60.0
_UNAVAILABLE_WAIT = 15
_MAX_RETRIES     = 3

# Primary provider — default gemini, override via LLM_PROVIDER env var
_PRIMARY_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()


class AllProvidersFailedError(Exception):
    pass


class LLMRouter:
    def __init__(self) -> None:
        self._claude:     Optional[ClaudeClient]     = None
        self._gemini:     Optional[GeminiClient]     = None
        self._openrouter: Optional[OpenRouterClient] = None
        self._cache:      dict                       = {}
        self._cache_loaded = False
        self._lock = asyncio.Lock()

        max_rpm = _MAX_RPM_CLAUDE if _PRIMARY_PROVIDER == "claude" else _MAX_RPM_GEMINI
        self._min_gap_secs = _WINDOW_SECS / max_rpm
        self._timestamps: collections.deque = collections.deque(maxlen=max_rpm)

    # ── Public API ────────────────────────────────────────────────────────────

    async def call(self, prompt: str, bypass_cache: bool = False) -> str:
        self._ensure_cache()
        key = _hash(prompt)

        if not bypass_cache and key in self._cache:
            logger.debug("Cache hit %s...", key[:8])
            return self._cache[key]

        await self._pace()
        result = await self._call_with_retry(prompt)

        self._cache[key] = result
        self._save_cache()
        return result

    def get_active_provider(self) -> str:
        return _PRIMARY_PROVIDER

    def cache_stats(self) -> dict:
        self._ensure_cache()
        size_bytes = _CACHE_PATH.stat().st_size if _CACHE_PATH.exists() else 0
        return {
            "entries": len(self._cache),
            "size_kb": round(size_bytes / 1024, 1),
            "provider": _PRIMARY_PROVIDER,
        }

    def clear_cache(self) -> int:
        count = len(self._cache)
        self._cache = {}
        if _CACHE_PATH.exists():
            _CACHE_PATH.unlink()
        self._cache_loaded = False
        logger.info("LLM cache cleared (%d entries)", count)
        return count

    # ── Rate pacer ────────────────────────────────────────────────────────────

    async def _pace(self) -> None:
        async with self._lock:
            now = time.monotonic()

            if self._timestamps:
                gap = now - self._timestamps[-1]
                if gap < self._min_gap_secs:
                    await asyncio.sleep(self._min_gap_secs - gap)
                    now = time.monotonic()

            max_rpm = _MAX_RPM_CLAUDE if _PRIMARY_PROVIDER == "claude" else _MAX_RPM_GEMINI
            if len(self._timestamps) == max_rpm:
                oldest = self._timestamps[0]
                elapsed = now - oldest
                if elapsed < _WINDOW_SECS:
                    wait = _WINDOW_SECS - elapsed + 0.1
                    logger.info("Rate pacer: window full, sleeping %.1fs", wait)
                    await asyncio.sleep(wait)
                    now = time.monotonic()

            self._timestamps.append(now)

    # ── Failover chain ────────────────────────────────────────────────────────

    async def _call_with_retry(self, prompt: str) -> str:
        last_exc: Optional[Exception] = None

        if _PRIMARY_PROVIDER == "claude":
            for attempt in range(_MAX_RETRIES):
                try:
                    return await self._get_claude().call_async(prompt)
                except ClaudeRateLimitError as exc:
                    last_exc = exc
                    logger.warning("Claude 429 (attempt %d) waiting %.0fs",
                                   attempt + 1, exc.suggested_wait)
                    await asyncio.sleep(exc.suggested_wait)
                except ClaudeUnavailableError as exc:
                    last_exc = exc
                    logger.warning("Claude 503 waiting %ds", _UNAVAILABLE_WAIT)
                    await asyncio.sleep(_UNAVAILABLE_WAIT)
                except Exception as exc:
                    last_exc = exc
                    logger.warning("Claude error: %s -- falling back", exc)
                    break

            # Claude failed -> try Gemini
            logger.info("Claude failed, trying Gemini")
            try:
                return await self._get_gemini().call_async(prompt)
            except Exception as exc:
                last_exc = exc
                logger.warning("Gemini also failed: %s -- trying OpenRouter", exc)

        elif _PRIMARY_PROVIDER == "gemini":
            for attempt in range(_MAX_RETRIES):
                try:
                    return await self._get_gemini().call_async(prompt)
                except GeminiRateLimitError as exc:
                    last_exc = exc
                    logger.warning("Gemini 429 (attempt %d) waiting %.0fs",
                                   attempt + 1, exc.suggested_wait)
                    await asyncio.sleep(exc.suggested_wait)
                except GeminiUnavailableError as exc:
                    last_exc = exc
                    logger.warning("Gemini 503 waiting %ds", _UNAVAILABLE_WAIT)
                    await asyncio.sleep(_UNAVAILABLE_WAIT)
                except Exception as exc:
                    last_exc = exc
                    logger.warning("Gemini error: %s -- falling back", exc)
                    break

        # Final fallback: OpenRouter
        logger.info("Falling back to OpenRouter")
        try:
            return await self._get_openrouter().call_async(prompt)
        except ValueError as exc:
            raise AllProvidersFailedError(
                f"All providers failed. Last: {last_exc}. "
                "Check your API keys in .env."
            ) from exc
        except OpenRouterError as exc:
            raise AllProvidersFailedError(
                f"All providers failed. Gemini: {last_exc} | OpenRouter: {exc}"
            ) from exc

    # ── Lazy client factories ─────────────────────────────────────────────────

    def _get_claude(self) -> ClaudeClient:
        if self._claude is None:
            self._claude = ClaudeClient()
        return self._claude

    def _get_gemini(self) -> GeminiClient:
        if self._gemini is None:
            self._gemini = GeminiClient()
        return self._gemini

    def _get_openrouter(self) -> OpenRouterClient:
        if self._openrouter is None:
            self._openrouter = OpenRouterClient()
        return self._openrouter

    # ── Cache I/O ─────────────────────────────────────────────────────────────

    def _ensure_cache(self) -> None:
        if self._cache_loaded:
            return
        if _CACHE_PATH.exists():
            try:
                self._cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
                logger.info("Loaded %d cached LLM responses", len(self._cache))
            except Exception as exc:
                logger.warning("Could not load LLM cache: %s", exc)
        self._cache_loaded = True

    def _save_cache(self) -> None:
        try:
            _CACHE_PATH.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Could not save LLM cache: %s", exc)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


async def llm_call(prompt: str, bypass_cache: bool = False) -> str:
    return await get_router().call(prompt, bypass_cache=bypass_cache)
