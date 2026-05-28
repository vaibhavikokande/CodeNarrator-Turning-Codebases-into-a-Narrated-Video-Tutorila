"""
GenerateVideoScript — map-reduce video script generator.

FAST PATH: chapter summaries are extracted with Python (zero LLM calls).
Only the final reduce step (1 call) uses the LLM to write the script.
Total LLM calls: 1  (was 5) → ~10x faster.
"""

import logging
import re
from typing import Any, Dict, List

from llm.router import llm_call
from pipeline.pocketflow import AsyncNode
from utils.yaml_validator import ValidationError, validate_video_script

logger = logging.getLogger(__name__)

_TARGET_SEGMENTS = 10   # was 14 — 10 segments covers a full tutorial; saves ~30% render time
_MAX_SUMMARY_LEN = 600   # chars per chapter summary passed to LLM


# ── Python-based chapter summariser (no LLM) ─────────────────────────────────

def _extract_summary(fname: str, content: str) -> str:
    """Extract key info from a Markdown chapter without calling an LLM."""
    lines   = content.splitlines()
    heading = ""
    defs    = []
    bullets = []
    code_snippets = []
    in_code = False
    code_buf = []

    for line in lines:
        stripped = line.strip()

        # Track code blocks
        if stripped.startswith("```"):
            if in_code:
                if code_buf:
                    snippet = "\n".join(code_buf[:6])
                    code_snippets.append(snippet)
                code_buf = []
            in_code = not in_code
            continue
        if in_code:
            code_buf.append(stripped)
            continue

        # Chapter heading
        if stripped.startswith("# ") and not heading:
            heading = stripped[2:].strip()
            continue

        # Section headings → key topic labels
        if stripped.startswith("## "):
            topic = stripped[3:].strip()
            if topic.lower() not in ("motivation", "conclusion", "navigation"):
                defs.append(topic)
            continue

        # Bullet points
        if stripped.startswith(("-", "*", "•")) and len(stripped) > 4:
            bullets.append(stripped.lstrip("-*• ").strip())
            continue

        # Bold definitions: **Term**: definition
        m = re.search(r'\*\*(.+?)\*\*\s*[:\-–]?\s*(.+)', stripped)
        if m and len(m.group(2)) > 15:
            defs.append(f"{m.group(1).strip()}: {m.group(2).strip()[:80]}")

    title = heading or fname.replace(".md", "").replace("_", " ").title()
    parts = [f"Chapter: {title}"]
    if defs:
        parts.append("Key concepts: " + "; ".join(defs[:4]))
    if bullets:
        parts.append("Points: " + " | ".join(bullets[:4]))
    if code_snippets:
        parts.append("Code example:\n" + code_snippets[0])

    return "\n".join(parts)[:_MAX_SUMMARY_LEN]


# ── LLM reduce prompt ─────────────────────────────────────────────────────────

def _reduce_prompt(summaries: str, repo_name: str, language: str) -> str:
    # Build a concrete example narration in the target language so the LLM
    # has no ambiguity — English examples caused the LLM to write English narration.
    _lang_example = {
        "hindi":      "यह ट्यूटोरियल आपको इस प्रोजेक्ट की मूल अवधारणाओं से परिचित कराएगा। आइए शुरू करते हैं।",
        "spanish":    "Este tutorial le presentará los conceptos clave de este proyecto. Empecemos.",
        "french":     "Ce tutoriel vous présentera les concepts clés de ce projet. Commençons.",
        "german":     "Dieses Tutorial stellt Ihnen die Kernkonzepte dieses Projekts vor. Fangen wir an.",
        "japanese":   "このチュートリアルでは、プロジェクトの主要な概念を紹介します。始めましょう。",
        "chinese":    "本教程将向您介绍该项目的核心概念。让我们开始吧。",
        "portuguese": "Este tutorial apresentará os conceitos principais deste projeto. Vamos começar.",
        "arabic":     "سيقدم لك هذا البرنامج التعليمي المفاهيم الرئيسية لهذا المشروع. لنبدأ.",
        "korean":     "이 튜토리얼은 프로젝트의 핵심 개념을 소개합니다. 시작해 봅시다.",
        "english":    "This tutorial will introduce you to the core concepts of this project. Let us begin.",
    }
    example_narration = _lang_example.get(language.lower(),
        f"[Write this narration in {language}. Example: introduce the topic in 2 sentences.]")

    return f"""You are writing a narration script for an animated educational video about "{repo_name}".

╔══════════════════════════════════════════════════════════════════════╗
║  CRITICAL LANGUAGE REQUIREMENT — READ FIRST                         ║
║                                                                      ║
║  OUTPUT LANGUAGE: {language:<48}║
║                                                                      ║
║  Every single "narration:" field MUST be written entirely in        ║
║  {language}. Do NOT write narration in English under any            ║
║  circumstances. The narration is the spoken audio — it MUST be      ║
║  in {language} so the viewer hears {language} speech.              ║
║                                                                      ║
║  CORRECT narration example ({language}):                            ║
║  {example_narration[:64]:<64}║
║                                                                      ║
║  WRONG (do NOT do this): "This function handles the request..."     ║
╚══════════════════════════════════════════════════════════════════════╝

display_content fields (titles, headings, key_points) stay in English —
they appear as on-screen text rendered with an English font.

Here are the chapter summaries:
{summaries}

Create exactly {_TARGET_SEGMENTS} video segments. Segment types:

  title        → display_content: "Project Name\\nOne-line tagline"
  chapter_intro → display_content dict: chapter_number, chapter_title, summary
  definition   → display_content dict: concept, definition, key_points (list), analogy
  code         → display_content dict: filename, code (YAML literal block |), language, highlight_line, explanation_points (list), purpose
  architecture → display_content dict: mermaid_source (YAML literal block |), summary
  summary      → display_content dict: heading, takeaways (list), next_chapter
  bullets      → display_content dict: title, key_points (list)

CRITICAL YAML RULES:
1. "code" field — ALWAYS literal block scalar:
      code: |
        def example():
            return True
2. "mermaid_source" — ALWAYS literal block scalar.
3. Every narration: MUST be 2 full sentences (30-50 words) written in {language}.
   If you write narration in English, the audio will be WRONG.
4. No colons inside unquoted strings — wrap in double quotes.
5. No tabs — 2-space indent only.

STRUCTURE: title → chapter_intro → definition/code/bullets/architecture → summary

Return ONLY a YAML code block:
```yaml
segments:
  - type: title
    display_content: "{repo_name}\\nWhat this project does in one line"
    narration: "{example_narration}"
  - type: chapter_intro
    display_content:
      chapter_number: "01"
      chapter_title: "Getting Started"
      summary: "Overview of core setup and configuration"
    narration: "[2 sentences in {language} introducing this chapter — NOT in English]"
  - type: definition
    display_content:
      concept: "Key Term"
      definition: "Clear one-sentence definition"
      key_points:
        - "First important point"
        - "Second important point"
      analogy: "Real-world analogy"
    narration: "[2 sentences in {language} explaining this concept — NOT in English]"
  - type: code
    display_content:
      filename: "example.py"
      language: "python"
      highlight_line: 1
      purpose: "What this code achieves"
      explanation_points:
        - "What the first part does"
        - "Why this pattern is used"
      code: |
        def hello():
            return "world"
    narration: "[2 sentences in {language} describing this code — NOT in English]"
  - type: summary
    display_content:
      heading: "Key Takeaways"
      takeaways:
        - "First main lesson"
        - "Second main lesson"
      next_chapter: "What comes next"
    narration: "[2 sentences in {language} summarising what was learned — NOT in English]"
```"""


# ── Node ──────────────────────────────────────────────────────────────────────

class GenerateVideoScript(AsyncNode):
    max_retries = 3

    async def prep(self, shared: dict) -> dict:
        return {
            "chapters":  shared["chapters"],
            "repo_name": shared.get("repo_name", "Project"),
            "language":  shared.get("language", "English"),
        }

    async def _exec_attempt(self, prep_result: dict, bypass_cache: bool) -> dict:
        chapters:  Dict[str, str] = prep_result["chapters"]
        repo_name: str            = prep_result["repo_name"]
        language:  str            = prep_result["language"]

        # ── Map phase: Python only, zero LLM calls ──
        sorted_chapters = sorted(chapters.items())
        print(f"GenerateVideoScript: extracting summaries from {len(sorted_chapters)} chapters (no LLM)")
        summaries = []
        for fname, content in sorted_chapters:
            summary = _extract_summary(fname, content)
            summaries.append(f"=== {fname} ===\n{summary}")
            print(f"GenerateVideoScript:   extracted {fname} ({len(summary)} chars)")

        aggregated = "\n\n".join(summaries)

        # ── Reduce phase: 1 LLM call ──
        print(f"GenerateVideoScript: reduce — 1 LLM call to build {_TARGET_SEGMENTS}-segment script")
        raw = await llm_call(_reduce_prompt(aggregated, repo_name, language),
                             bypass_cache=bypass_cache)

        if not raw or not raw.strip():
            raise ValueError("LLM returned empty video script")

        raw = raw.encode("utf-8", errors="replace").decode("utf-8")

        try:
            data = validate_video_script(raw)
        except ValidationError as exc:
            raise ValueError(f"Video script validation failed: {exc}") from exc

        return {"video_script": data["segments"]}

    async def exec(self, prep_result: dict) -> dict:
        return await self._exec_attempt(prep_result, bypass_cache=False)

    async def _exec_retry_async(self, prep_result: dict, cur_retry: int) -> dict:
        return await self._exec_attempt(prep_result, bypass_cache=True)

    async def post(self, shared: dict, prep_result: Any, exec_result: dict) -> str:
        shared["video_script"] = exec_result["video_script"]
        print(f"GenerateVideoScript: {len(shared['video_script'])} segments ready")

        # Persist to disk so server restarts don't lose the script.
        # Zoom, Shorts, Avatar endpoints all need this after a restart.
        import json
        from pathlib import Path
        try:
            out = Path(shared["output_dir"]) / "video_script.json"
            out.write_text(
                json.dumps(exec_result["video_script"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"GenerateVideoScript: saved to video_script.json")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Could not save video_script.json: %s", exc)

        return "default"
