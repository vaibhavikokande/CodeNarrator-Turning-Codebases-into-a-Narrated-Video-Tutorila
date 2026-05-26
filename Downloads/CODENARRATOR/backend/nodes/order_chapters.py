"""
OrderChapters node — asks LLM to arrange abstractions from foundational to advanced.
Truncates result to FAST_TUTORIAL_MAX_FILES.
"""

import logging
import os
from typing import Any, List

from llm.router import llm_call
from pipeline.pocketflow import AsyncNode
from utils.yaml_validator import ValidationError, validate_chapter_order

logger = logging.getLogger(__name__)

FAST_TUTORIAL_MAX_FILES = int(os.environ.get("FAST_TUTORIAL_MAX_FILES", "5"))


def _build_prompt(abstraction_names: List[str], language: str) -> str:
    names_str = "\n".join(f"- {n}" for n in abstraction_names)
    return f"""Order these abstractions from foundational to advanced for a progressive tutorial:
{names_str}

Generate all content in {language}. Code syntax, identifiers, and structural strings like "Chapter", "Source Repository" must remain in English.

Return ONLY valid YAML:
```yaml
order: [<name>, <name>, ...]
```
No other text."""


class OrderChapters(AsyncNode):
    max_retries = 3

    async def prep(self, shared: dict) -> dict:
        return {
            "abstractions":       shared["abstractions"],
            "language":           shared.get("language", "English"),
            # If AnalyzeRelationships already captured the order, carry it here
            # so exec() can skip the LLM call and return it directly.
            "prefilled_order":    shared.get("chapter_order", []),
        }

    async def _exec_attempt(self, prep_result: dict, bypass_cache: bool) -> dict:
        abstractions    = prep_result["abstractions"]
        names           = [a["name"] for a in abstractions]
        prefilled_order = prep_result.get("prefilled_order", [])

        # Fast path: AnalyzeRelationships already gave us the order — skip LLM call
        if prefilled_order and len(prefilled_order) >= 2:
            capped = prefilled_order[:FAST_TUTORIAL_MAX_FILES]
            logger.info("OrderChapters: using pre-filled order (%d chapters) — LLM call skipped ✓", len(capped))
            return {"chapter_order": capped}

        # Slow path: ask LLM (fallback if AnalyzeRelationships didn't return order)
        prompt = _build_prompt(names, prep_result["language"])
        logger.info("OrderChapters: calling LLM (bypass_cache=%s)", bypass_cache)
        raw = await llm_call(prompt, bypass_cache=bypass_cache)

        if not raw or not raw.strip():
            raise ValueError("LLM returned empty response for chapter order")

        raw = raw.encode("utf-8", errors="replace").decode("utf-8")

        try:
            data = validate_chapter_order(raw, names)
        except ValidationError as exc:
            raise ValueError(f"Chapter order validation failed: {exc}") from exc

        ordered = data["order"][:FAST_TUTORIAL_MAX_FILES]
        return {"chapter_order": ordered}

    async def exec(self, prep_result: dict) -> dict:
        return await self._exec_attempt(prep_result, bypass_cache=False)

    async def _exec_retry_async(self, prep_result: dict, cur_retry: int) -> dict:
        return await self._exec_attempt(prep_result, bypass_cache=True)

    async def post(self, shared: dict, prep_result: Any, exec_result: dict) -> str:
        shared["chapter_order"] = exec_result["chapter_order"]
        total = len(shared["chapter_order"])
        print(f"CHAPTER_TOTAL: {total}")
        logger.info("OrderChapters: %d chapters ordered", total)
        return "default"
