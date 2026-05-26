"""
WriteChapters node — generates one Markdown chapter per abstraction.
Uses asyncio.Condition so chapter N waits for chapter N-1 to complete.
"""

import asyncio
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from llm.router import llm_call
from pipeline.pocketflow import AsyncParallelBatchNode

logger = logging.getLogger(__name__)

_MAX_CHARS_PER_FILE = 800   # was 1400 — enough to show structure, not full body
_MAX_TOTAL_CHARS    = 12_000  # was 30000 — cuts Gemini processing time ~60%


def _sanitize_filename(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^\w\s-]", "", name).strip()
    name = re.sub(r"[\s]+", "_", name)
    return name.lower()


def _build_file_context(
    abstraction: dict, files: List[Tuple[str, str]]
) -> str:
    indices = abstraction.get("file_indices", [])
    parts = []
    total = 0
    for idx in indices:
        if idx >= len(files):
            continue
        path, content = files[idx]
        snippet = content[:_MAX_CHARS_PER_FILE]
        chunk = f"### File: {path}\n```\n{snippet}\n```\n"
        if total + len(chunk) > _MAX_TOTAL_CHARS:
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n".join(parts)


def _chapter_listing(chapter_names: List[str], chapter_filenames: List[str]) -> str:
    lines = []
    for i, (name, fname) in enumerate(zip(chapter_names, chapter_filenames), 1):
        lines.append(f"  Chapter {i}: {name} ({fname})")
    return "\n".join(lines)


def _build_prompt(
    chapter_num: int,
    name: str,
    description: str,
    file_context: str,
    all_chapters: str,
    prev_meta: Optional[dict],
    next_meta: Optional[dict],
    language: str,
) -> str:
    prev_note = (
        f"This chapter follows '{prev_meta['name']}' ({prev_meta['filename']}). "
        "Begin with a brief transition phrase referencing the previous chapter."
        if prev_meta else "This is the first chapter."
    )
    next_note = (
        f"This chapter precedes '{next_meta['name']}' ({next_meta['filename']}). "
        "End with a forward reference to the next chapter."
        if next_meta else "This is the final chapter."
    )

    nav_prev = f"[← Previous: {prev_meta['name']}]({prev_meta['filename']})" if prev_meta else "[← Start](index.md)"
    nav_next = f"[Next: {next_meta['name']} →]({next_meta['filename']})" if next_meta else "[→ Index](index.md)"

    return f"""Generate a tutorial chapter with EXACTLY this structure.

Generate all content in {language}. Code syntax, identifiers, and structural strings like "Chapter", "Source Repository" must remain in English.

All chapters in this tutorial:
{all_chapters}

{prev_note}
{next_note}

Chapter details:
- Number: {chapter_num}
- Name: {name}
- Description: {description}

Relevant source files:
{file_context}

REQUIRED STRUCTURE (use these exact headings):

# Chapter {chapter_num}: {name}

## Motivation
[Why this abstraction exists and the problem it solves]

## Core Concepts
[Key ideas; include code blocks ≤10 lines each]

## Practical Usage
[How to use this abstraction; include code examples]

## Internal Mechanics
[How it works internally; include a Mermaid sequence diagram like:]
```mermaid
sequenceDiagram
    A->>B: message
    B-->>A: response
```

## Conclusion
[Summary and key takeaways]

---
{nav_prev} | {nav_next}

Word count target: 400–600 words. Be concise."""


class WriteChapters(AsyncParallelBatchNode):
    max_retries = 3

    async def prep(self, shared: dict) -> dict:
        return {
            "chapter_order": shared["chapter_order"],
            "abstractions": shared["abstractions"],
            "files": shared["files"],
            "output_dir": shared["output_dir"],
            "language": shared.get("language", "English"),
        }

    async def exec(self, prep_result: dict) -> dict:  # type: ignore[override]
        chapter_order = prep_result["chapter_order"]
        abstractions_map: Dict[str, dict] = {
            a["name"]: a for a in prep_result["abstractions"]
        }
        files = prep_result["files"]
        language = prep_result["language"]
        output_dir = Path(prep_result["output_dir"])

        # Build filename list upfront
        filenames = [
            f"{str(i + 1).zfill(2)}_{_sanitize_filename(name)}.md"
            for i, name in enumerate(chapter_order)
        ]

        all_chapters_str = _chapter_listing(chapter_order, filenames)

        condition = asyncio.Condition()
        completed_up_to = [-1]  # mutable int via list
        chapters: Dict[str, str] = {}

        async def write_chapter(idx: int) -> Tuple[str, str]:
            name = chapter_order[idx]
            filename = filenames[idx]
            abstraction = abstractions_map.get(name, {"name": name, "description": "", "file_indices": []})

            # Wait for previous chapter
            async with condition:
                while completed_up_to[0] < idx - 1:
                    await condition.wait()

            file_context = _build_file_context(abstraction, files)
            prev_meta = (
                {"name": chapter_order[idx - 1], "filename": filenames[idx - 1]}
                if idx > 0 else None
            )
            next_meta = (
                {"name": chapter_order[idx + 1], "filename": filenames[idx + 1]}
                if idx < len(chapter_order) - 1 else None
            )

            prompt = _build_prompt(
                chapter_num=idx + 1,
                name=name,
                description=abstraction.get("description", ""),
                file_context=file_context,
                all_chapters=all_chapters_str,
                prev_meta=prev_meta,
                next_meta=next_meta,
                language=language,
            )

            for attempt in range(self.max_retries):
                bypass = attempt > 0
                raw = await llm_call(prompt, bypass_cache=bypass)
                if raw and raw.strip():
                    content = raw.encode("utf-8", errors="replace").decode("utf-8")
                    break
            else:
                content = f"# Chapter {idx + 1}: {name}\n\n*Content generation failed.*\n"

            # Write file
            out_path = output_dir / filename
            out_path.write_text(content, encoding="utf-8")
            print(f"CHAPTER_READY: {filename}")
            logger.info("WriteChapters: wrote %s", filename)

            # Signal next chapter
            async with condition:
                completed_up_to[0] = idx
                condition.notify_all()

            return filename, content

        tasks = [write_chapter(i) for i in range(len(chapter_order))]
        results = await asyncio.gather(*tasks)

        return {filename: content for filename, content in results}

    async def post(self, shared: dict, prep_result: Any, exec_result: dict) -> str:
        shared["chapters"] = exec_result
        logger.info("WriteChapters: completed %d chapters", len(exec_result))
        return "default"
