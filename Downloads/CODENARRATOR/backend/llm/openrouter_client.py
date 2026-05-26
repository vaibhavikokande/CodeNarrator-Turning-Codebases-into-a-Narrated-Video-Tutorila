"""
OpenRouter fallback client — tries multiple free models in order until one responds.
"""

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Ordered by quality + reliability. First working model wins.
_FREE_MODELS = [
    "openai/gpt-oss-120b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-26b-a4b-it:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "nvidia/nemotron-nano-9b-v2:free",
]

_TIMEOUT       = 90.0   # per-request hard cap — never hang indefinitely
_RETRY_DELAY   = 5.0


class OpenRouterError(Exception):
    pass


class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise ValueError("OPENROUTER_API_KEY is not set")
        self._api_key = key

    async def call_async(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://code-narrator.local",
            "X-Title": "Code Narrator",
        }

        last_error = ""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for model in _FREE_MODELS:
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 4096,
                }
                try:
                    logger.info("OpenRouter: trying %s", model)
                    resp = await client.post(_OPENROUTER_URL, json=payload, headers=headers)

                    if resp.status_code == 429:
                        logger.warning("OpenRouter: %s rate-limited, trying next model", model)
                        last_error = f"{model} 429"
                        await asyncio.sleep(_RETRY_DELAY)
                        continue

                    if resp.status_code == 404:
                        logger.warning("OpenRouter: %s not found, trying next", model)
                        last_error = f"{model} 404"
                        continue

                    resp.raise_for_status()
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"]

                    if not text or not text.strip():
                        logger.warning("OpenRouter: %s returned empty, trying next", model)
                        last_error = f"{model} empty"
                        continue

                    logger.info("OpenRouter: success with %s", model)
                    return text

                except httpx.TimeoutException:
                    logger.warning("OpenRouter: %s timed out after %.0fs, trying next", model, _TIMEOUT)
                    last_error = f"{model} timeout"
                    continue
                except httpx.HTTPStatusError as exc:
                    last_error = f"{model} HTTP {exc.response.status_code}"
                    logger.warning("OpenRouter: %s error %s", model, last_error)
                    continue
                except (KeyError, IndexError) as exc:
                    last_error = f"{model} bad response shape"
                    continue
                except Exception as exc:
                    last_error = f"{model} {exc}"
                    logger.warning("OpenRouter: %s unexpected error: %s", model, exc)
                    continue

        raise OpenRouterError(
            f"All OpenRouter free models failed. Last error: {last_error}"
        )
