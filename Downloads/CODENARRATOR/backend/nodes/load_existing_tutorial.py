"""
LoadExistingTutorial node — reads generated Markdown files for the video pipeline.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict

from pipeline.pocketflow import AsyncNode

logger = logging.getLogger(__name__)

_CHAPTER_RE = re.compile(r"^\d+_.*\.md$")


class LoadExistingTutorial(AsyncNode):

    async def prep(self, shared: dict) -> dict:
        return {"output_dir": shared["output_dir"]}

    async def exec(self, prep_result: dict) -> dict:
        output_dir = Path(prep_result["output_dir"])
        if not output_dir.exists():
            raise FileNotFoundError(f"Output directory not found: {output_dir}")

        chapters: Dict[str, str] = {}
        index_content = ""

        index_path = output_dir / "index.md"
        if index_path.exists():
            index_content = index_path.read_text(encoding="utf-8")

        for md_file in sorted(output_dir.glob("*.md")):
            if _CHAPTER_RE.match(md_file.name):
                chapters[md_file.name] = md_file.read_text(encoding="utf-8")

        if not chapters:
            raise FileNotFoundError(
                f"No chapter files found in {output_dir}. "
                "Run the text pipeline first."
            )

        logger.info("LoadExistingTutorial: loaded %d chapters", len(chapters))
        return {"chapters": chapters, "index_content": index_content}

    async def post(self, shared: dict, prep_result: Any, exec_result: dict) -> str:
        shared["chapters"] = exec_result["chapters"]
        shared["index_content"] = exec_result.get("index_content", "")
        return "default"
