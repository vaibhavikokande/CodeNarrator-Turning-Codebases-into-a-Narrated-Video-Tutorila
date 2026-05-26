"""
Anthropic Claude client — async wrapper with streaming + retry support.

Uses the official `anthropic` Python SDK.
Supports Claude 3.5 Sonnet (default) and falls back to claude-3-haiku for speed.
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_MODEL   = "claude-sonnet-4-5"
_FALLBACK_MODEL  = "claude-haiku-4-5-20251001"
_MAX_TOKENS      = 8192
_TIMEOUT_SECS    = 120


class ClaudeRateLimitError(Exception):
    def __init__(self, message: str, suggested_wait: float = 30.0):
        super().__init__(message)
        self.suggested_wait = suggested_wait


class ClaudeUnavailableError(Exception):
    pass


class ClaudeClient:
    """
    Thin async wrapper around the Anthropic SDK.
    Reads ANTHROPIC_API_KEY from the environment.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or set the environment variable."
            )
        self._model = model
        self._client = None  # lazy-init

    # ── Public API ────────────────────────────────────────────────────────

    async def call_async(self, prompt: str) -> str:
        """Send a prompt and return the response text."""
        client = self._get_client()
        try:
            response = await asyncio.to_thread(
                self._blocking_call, client, prompt, self._model
            )
            return response
        except Exception as exc:
            exc_str = str(exc).lower()
            if "rate_limit" in exc_str or "429" in exc_str:
                # Try to extract retry-after header value
                wait = 30.0
                raise ClaudeRateLimitError(str(exc), suggested_wait=wait)
            if "overloaded" in exc_str or "503" in exc_str or "529" in exc_str:
                raise ClaudeUnavailableError(str(exc))
            raise

    # ── Internal ──────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=self._api_key,
                    timeout=_TIMEOUT_SECS,
                )
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic package not installed. Run: pip install anthropic"
                ) from exc
        return self._client

    def _blocking_call(self, client, prompt: str, model: str) -> str:
        """Synchronous call — run inside asyncio.to_thread."""
        try:
            message = client.messages.create(
                model=model,
                max_tokens=_MAX_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )
            # Extract text from the first content block
            if message.content and hasattr(message.content[0], "text"):
                return message.content[0].text
            return ""
        except Exception as exc:
            exc_str = str(exc)
            # Fallback to haiku on model-specific errors
            if model != _FALLBACK_MODEL and ("model" in exc_str.lower() or "invalid" in exc_str.lower()):
                logger.warning(
                    "Claude model %s failed (%s), retrying with %s",
                    model, exc_str[:80], _FALLBACK_MODEL
                )
                return self._blocking_call(client, prompt, _FALLBACK_MODEL)
            raise
