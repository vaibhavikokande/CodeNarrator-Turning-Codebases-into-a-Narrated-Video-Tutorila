"""
IdentifyAbstractions node — asks the LLM to find 5-10 core abstractions.
"""

import logging
from typing import Any, List, Tuple

from llm.router import llm_call
from pipeline.pocketflow import AsyncNode
from utils.yaml_validator import ValidationError, validate_abstractions

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 40_000   # was 120000 — top files already scored highest
_MAX_FILE_PREVIEW  = 1_500    # was 3500 — first 1500 chars captures the signature


def _build_context(files: List[Tuple[str, str]]) -> str:
    parts = []
    total = 0
    for idx, (path, content) in enumerate(files):
        snippet = content[:_MAX_FILE_PREVIEW]
        chunk = f"{idx} # {path}\n{snippet}\n"
        if total + len(chunk) > _MAX_CONTEXT_CHARS:
            logger.warning("Context cap reached at file %d — truncating.", idx)
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n".join(parts)


def _build_prompt(context: str, language: str) -> str:
    return f"""You are analyzing a software repository. Identify 5–10 core architectural abstractions.

Generate all content in {language}. Code syntax, identifiers, and structural strings like "Chapter", "Source Repository" must remain in English.

Here are the repository files:
{context}

Return ONLY valid YAML in this exact format. IMPORTANT: description values must NOT contain colons — rephrase if needed:
```yaml
abstractions:
  - name: <string>
    description: <1-2 sentence description without colons>
    file_indices: [<integer>, ...]
```
No other text, no markdown outside the YAML block."""


class IdentifyAbstractions(AsyncNode):
    max_retries = 3

    async def prep(self, shared: dict) -> dict:
        return {
            "files": shared["files"],
            "language": shared.get("language", "English"),
        }

    async def _exec_attempt(self, prep_result: dict, bypass_cache: bool) -> dict:
        files = prep_result["files"]
        language = prep_result["language"]
        num_files = len(files)
        context = _build_context(files)
        prompt = _build_prompt(context, language)

        logger.info("IdentifyAbstractions: calling LLM (bypass_cache=%s)", bypass_cache)
        raw = await llm_call(prompt, bypass_cache=bypass_cache)

        if not raw or not raw.strip():
            raise ValueError("LLM returned empty response for abstractions")

        try:
            raw_utf8 = raw.encode("utf-8", errors="replace").decode("utf-8")
            data = validate_abstractions(raw_utf8)
        except ValidationError as exc:
            raise ValueError(f"Abstraction validation failed: {exc}") from exc

        # Clamp file_indices to valid range
        abstractions = data["abstractions"]
        for abst in abstractions:
            abst["file_indices"] = [
                max(0, min(int(i), num_files - 1)) for i in abst["file_indices"]
            ]

        return {"abstractions": abstractions}

    async def exec(self, prep_result: dict) -> dict:
        return await self._exec_attempt(prep_result, bypass_cache=False)

    async def _exec_retry_async(self, prep_result: dict, cur_retry: int) -> dict:
        return await self._exec_attempt(prep_result, bypass_cache=True)

    async def post(self, shared: dict, prep_result: Any, exec_result: dict) -> str:
        shared["abstractions"] = exec_result["abstractions"]
        logger.info(
            "IdentifyAbstractions: found %d abstractions", len(shared["abstractions"])
        )
        return "default"
