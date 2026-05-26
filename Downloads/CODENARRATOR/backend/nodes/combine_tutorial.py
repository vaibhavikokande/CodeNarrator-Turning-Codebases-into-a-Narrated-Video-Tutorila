"""
CombineTutorial node — assembles index.md with Mermaid architecture diagram.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from pipeline.pocketflow import AsyncNode

logger = logging.getLogger(__name__)


def _node_id(text: str) -> str:
    """Convert abstraction name to a valid Mermaid node ID (no spaces/specials)."""
    safe = re.sub(r'[^a-zA-Z0-9]', '_', text.strip())
    safe = re.sub(r'_+', '_', safe).strip('_')
    return safe or "Node"


def _node_label(text: str) -> str:
    """Quoted display label — strip inner quotes and newlines."""
    return re.sub(r'["\n]', ' ', text).strip()


def _build_mermaid_graph(relationships: List[Dict]) -> str:
    lines = ["graph TD"]
    # Collect unique nodes and emit label definitions first
    seen_ids: dict = {}
    for rel in relationships:
        for key in ("from_abstraction", "to_abstraction"):
            name = rel.get(key, "?")
            nid  = _node_id(name)
            if nid not in seen_ids:
                seen_ids[nid] = _node_label(name)

    for nid, label in seen_ids.items():
        lines.append(f'    {nid}["{label}"]')

    lines.append("")  # blank line before edges

    for rel in relationships:
        src   = _node_id(rel.get("from_abstraction", "?"))
        dst   = _node_id(rel.get("to_abstraction", "?"))
        label = _node_label(rel.get("label", ""))
        # Keep edge labels short to avoid Mermaid parser issues
        short = label[:40] + "…" if len(label) > 40 else label
        lines.append(f'    {src} -->|"{short}"| {dst}')

    return "\n".join(lines)


def _chapter_links(chapter_order: List[str], chapters: Dict[str, str]) -> str:
    lines = []
    # Sort by filename prefix to get numbered order
    sorted_files = sorted(
        [(fname, _get_chapter_name(fname, content)) for fname, content in chapters.items()],
        key=lambda x: x[0],
    )
    for i, (fname, title) in enumerate(sorted_files, 1):
        lines.append(f"{i}. [{title}]({fname})")
    return "\n".join(lines)


def _get_chapter_name(filename: str, content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return filename.replace(".md", "").replace("_", " ").title()


class CombineTutorial(AsyncNode):

    async def prep(self, shared: dict) -> dict:
        return {
            "repo_url": shared["repo_url"],
            "repo_name": shared.get("repo_name", "Project"),
            "summary": shared["summary"],
            "relationships": shared["relationships"],
            "chapter_order": shared["chapter_order"],
            "chapters": shared["chapters"],
            "output_dir": shared["output_dir"],
        }

    async def exec(self, prep_result: dict) -> dict:
        repo_url = prep_result["repo_url"]
        repo_name = prep_result["repo_name"]
        summary = prep_result["summary"]
        relationships = prep_result["relationships"]
        chapters = prep_result["chapters"]
        output_dir = Path(prep_result["output_dir"])

        mermaid_graph = _build_mermaid_graph(relationships)
        chapter_links = _chapter_links(prep_result["chapter_order"], chapters)

        index_content = f"""# {repo_name}

{summary}

**Source:** [{repo_url}]({repo_url})

## Architecture

```mermaid
{mermaid_graph}
```

## Chapters

{chapter_links}
"""
        index_path = output_dir / "index.md"
        index_path.write_text(index_content, encoding="utf-8")
        logger.info("CombineTutorial: wrote index.md")

        return {"index_md_path": str(index_path)}

    async def post(self, shared: dict, prep_result: Any, exec_result: dict) -> str:
        shared["index_md_path"] = exec_result["index_md_path"]
        logger.info("CombineTutorial: tutorial assembly complete")
        return "default"
