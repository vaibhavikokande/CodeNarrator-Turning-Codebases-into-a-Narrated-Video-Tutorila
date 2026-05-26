"""
AnalyzeRelationships node — generates project summary and abstraction relationships.
"""

import logging
from typing import Any

import yaml

from llm.router import llm_call
from pipeline.pocketflow import AsyncNode
from utils.yaml_validator import ValidationError, validate_relationships

logger = logging.getLogger(__name__)


def _build_prompt(abstractions_yaml: str, language: str) -> str:
    return f"""Given these abstractions:
{abstractions_yaml}

Generate all content in {language}. Code syntax, identifiers, and structural strings like "Chapter", "Source Repository" must remain in English.

Produce ALL THREE sections in ONE response:
1. A one-paragraph project summary.
2. Directional relationships between abstractions (every abstraction must appear at least once).
3. The optimal tutorial order for these abstractions (foundational → advanced).

Return ONLY valid YAML — no other text:
```yaml
summary: <string>
relationships:
  - from_abstraction: <name>
    to_abstraction: <name>
    label: <verb phrase>
order: [<name>, <name>, ...]
```"""


class AnalyzeRelationships(AsyncNode):
    max_retries = 3

    async def prep(self, shared: dict) -> dict:
        abstractions_yaml = yaml.dump(
            {"abstractions": shared["abstractions"]},
            default_flow_style=False, allow_unicode=True,
        )
        return {
            "abstractions_yaml": abstractions_yaml,
            "abstractions": shared["abstractions"],
            "language": shared.get("language", "English"),
        }

    async def _exec_attempt(self, prep_result: dict, bypass_cache: bool) -> dict:
        prompt = _build_prompt(prep_result["abstractions_yaml"], prep_result["language"])
        logger.info("AnalyzeRelationships: calling LLM (bypass_cache=%s)", bypass_cache)
        raw = await llm_call(prompt, bypass_cache=bypass_cache)

        if not raw or not raw.strip():
            raise ValueError("LLM returned empty response for relationships")

        raw = raw.encode("utf-8", errors="replace").decode("utf-8")

        try:
            data = validate_relationships(raw)
        except ValidationError as exc:
            raise ValueError(f"Relationship validation failed: {exc}") from exc

        result = {
            "summary":       data["summary"],
            "relationships": data["relationships"],
        }
        # Bonus: if LLM also returned the chapter order, capture it now
        # so OrderChapters can skip its LLM call entirely (saves ~25s).
        if "order" in data and isinstance(data["order"], list) and data["order"]:
            abstraction_names = [a["name"] for a in prep_result["abstractions"]]
            name_set = set(abstraction_names)
            order = [n for n in data["order"] if n in name_set]   # filter stray names
            if len(order) >= 2:
                result["chapter_order"] = order
                logger.info("AnalyzeRelationships: captured chapter order (%d chapters) — OrderChapters will be skipped", len(order))
        return result

    async def exec(self, prep_result: dict) -> dict:
        return await self._exec_attempt(prep_result, bypass_cache=False)

    async def _exec_retry_async(self, prep_result: dict, cur_retry: int) -> dict:
        return await self._exec_attempt(prep_result, bypass_cache=True)

    async def post(self, shared: dict, prep_result: Any, exec_result: dict) -> str:
        shared["summary"]       = exec_result["summary"]
        shared["relationships"] = exec_result["relationships"]
        # Pre-populate chapter_order so OrderChapters can skip its LLM call
        if "chapter_order" in exec_result:
            shared["chapter_order"] = exec_result["chapter_order"]
        logger.info(
            "AnalyzeRelationships: %d relationships", len(shared["relationships"])
        )
        return "default"
