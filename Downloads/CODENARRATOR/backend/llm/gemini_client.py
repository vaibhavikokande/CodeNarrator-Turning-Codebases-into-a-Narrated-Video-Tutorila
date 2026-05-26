"""
Gemini 2.5 Flash client (google-genai SDK).
Extracts the retryDelay from 429 responses so the router waits exactly
as long as Gemini asks rather than a fixed guess.
"""

import asyncio
import logging
import os
import re
from typing import Optional

from google import genai

logger = logging.getLogger(__name__)

_GEMINI_MODEL = "gemini-2.5-flash"   # new key — full model, 10 RPM free tier
_BASE_DELAY         = 5.0
_MAX_DELAY          = 30.0
_MAX_INTERNAL_RETRIES = 1   # one retry inside client; rest handled by router


class GeminiRateLimitError(Exception):
    """Carries suggested_wait_secs if Gemini included a retryDelay."""
    def __init__(self, message: str, suggested_wait: float = 60.0):
        super().__init__(message)
        self.suggested_wait = suggested_wait


class GeminiUnavailableError(Exception):
    pass


def _parse_retry_delay(exc_str: str) -> float:
    """Extract retryDelay seconds from Gemini error string, default 60s."""
    m = re.search(r"retryDelay['\"]:\s*['\"](\d+(?:\.\d+)?)s", exc_str)
    if m:
        return float(m.group(1)) + 2.0   # +2s buffer
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", exc_str, re.IGNORECASE)
    if m:
        return float(m.group(1)) + 2.0
    return 62.0   # safe default


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=key)

    async def call_async(self, prompt: str) -> str:
        delay = _BASE_DELAY
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_INTERNAL_RETRIES + 1):
            try:
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=_GEMINI_MODEL,
                    contents=prompt,
                )
                text = response.text
                if not text or not text.strip():
                    raise ValueError("Gemini returned empty response")
                return text

            except Exception as exc:
                exc_str = str(exc)
                last_exc = exc

                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    wait = _parse_retry_delay(exc_str)
                    raise GeminiRateLimitError(exc_str, suggested_wait=wait) from exc

                if "503" in exc_str or "UNAVAILABLE" in exc_str or "unavailable" in exc_str.lower():
                    raise GeminiUnavailableError(exc_str) from exc

                if attempt < _MAX_INTERNAL_RETRIES:
                    logger.warning("Gemini attempt %d failed (%s), retrying in %.1fs", attempt + 1, exc, delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, _MAX_DELAY)

        raise last_exc  # type: ignore[misc]
