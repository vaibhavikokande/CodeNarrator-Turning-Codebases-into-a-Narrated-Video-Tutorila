"""
export_pptx.py — Educational PPT Export (Archival/Scholarly Theme).

Replicates the visual identity of the "Archival Research – Ph.D. in History"
Slidesgo template, identified via python-pptx analysis:

  Background  : #2A292A  (dark charcoal — ALL slides)
  Body text   : #E2D9CA  (parchment/cream)
  Accent      : #CFBDA1  (warm tan/beige)
  Dark mauve  : #54494D
  Title font  : Josefin Sans  (fallback: Calibri)
  Body font   : Albert Sans   (fallback: Calibri Light)
  Slide size  : 10.0" × 5.625"  (widescreen)

6 slides per chapter:
  1. Title          — chapter name, repo, chapter number badge
  2. Overview       — "What is [topic]?" + bullets + AI notes
  3. Code           — monospace code block + explanation + AI notes
  4. Key Concepts   — 2×2 concept grid + AI notes
  5. Tutorial Steps — numbered steps + tips column + AI notes
  6. Summary        — recap checklist + next chapter + AI notes

Speaker notes on every slide via the existing LLM router.
"""

import asyncio
import logging
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Exact template colors (from Slidesgo template analysis) ──────────────────
_BG       = (0x2A, 0x29, 0x2A)   # #2A292A — all slide backgrounds
_PARCH    = (0xE2, 0xD9, 0xCA)   # #E2D9CA — parchment/cream — all body text
_ACCENT   = (0xCF, 0xBD, 0xA1)   # #CFBDA1 — warm tan (accent1)
_MAUVE    = (0x54, 0x49, 0x4D)   # #54494D — dark mauve
_NEAR_BLK = (0x19, 0x19, 0x19)   # #191919 — near-black (strong contrast)
_WHITE    = (0xFF, 0xFF, 0xFF)
_LINE_CLR = (0xCF, 0xBD, 0xA1)   # thin accent lines — same as accent

# Code block colors (matching dark scholarly palette)
_CODE_BG  = (0x1A, 0x19, 0x1A)   # slightly lighter than bg
_CODE_TXT = (0xE2, 0xD9, 0xCA)   # parchment on code bg

# Template fonts (Josefin Sans + Albert Sans are Google Fonts)
_FONT_TITLE = "Josefin Sans"
_FONT_BODY  = "Albert Sans"

# Slide dimensions (10.0" × 5.625" — widescreen, matches template)
_W = 10.0
_H = 5.625


# ── python-pptx helpers ───────────────────────────────────────────────────────

def _rgb(c: Tuple) -> Any:
    from pptx.dml.color import RGBColor
    return RGBColor(*c)

def _i(v: float) -> Any:
    from pptx.util import Inches
    return Inches(v)

def _pt(v: int) -> Any:
    from pptx.util import Pt
    return Pt(v)

def _new_prs():
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    prs.slide_width  = Inches(_W)
    prs.slide_height = Inches(_H)
    return prs

def _blank(prs) -> Any:
    return prs.slides.add_slide(prs.slide_layouts[6])

def _solid_bg(slide, color: Tuple) -> None:
    bg = slide.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = _rgb(color)

def _rect(slide, x, y, w, h, fill: Tuple) -> Any:
    """Add solid rectangle (all args in inches)."""
    shape = slide.shapes.add_shape(1, _i(x), _i(y), _i(w), _i(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill)
    shape.line.fill.background()
    return shape

def _txt(slide, text: str, x: float, y: float, w: float, h: float,
         size: int = 14, bold: bool = False, italic: bool = False,
         color: Tuple = _PARCH, font: str = _FONT_BODY,
         wrap: bool = True, center: bool = False) -> Any:
    """Add a text box with full styling."""
    from pptx.enum.text import PP_ALIGN
    txb = slide.shapes.add_textbox(_i(x), _i(y), _i(w), _i(h))
    tf  = txb.text_frame
    tf.word_wrap = wrap
    p   = tf.paragraphs[0]
    if center:
        p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text           = text
    run.font.name      = font
    run.font.size      = _pt(size)
    run.font.bold      = bold
    run.font.italic    = italic
    run.font.color.rgb = _rgb(color)
    return txb

def _bullet_list(slide, items: List[str], x: float, y: float,
                  w: float, h: float, size: int = 13,
                  color: Tuple = _PARCH, marker: str = "—") -> None:
    """Add a bulleted list with the template's dash marker style."""
    from pptx.util import Pt
    if not items:
        return
    txb = slide.shapes.add_textbox(_i(x), _i(y), _i(w), _i(h))
    tf  = txb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = _pt(5)
        run = p.add_run()
        run.text           = f"{marker}  {textwrap.shorten(item, 120, placeholder='…')}"
        run.font.name      = _FONT_BODY
        run.font.size      = _pt(size)
        run.font.color.rgb = _rgb(color)

def _notes(slide, text: str) -> None:
    if text:
        slide.notes_slide.notes_text_frame.text = text[:1500]

def _thin_line(slide, y: float, alpha_color: Tuple = _LINE_CLR) -> None:
    """Draw thin horizontal accent line (template motif)."""
    _rect(slide, 0, y, _W, 0.03, alpha_color)

def _chapter_badge(slide, num: int, x: float, y: float,
                    bg: Tuple = _MAUVE, text_color: Tuple = _PARCH) -> None:
    """Render the chapter number badge (e.g. '01') in Josefin Sans."""
    # Background pill
    _rect(slide, x, y, 0.72, 0.46, bg)
    # Number text
    _txt(slide, f"{num:02d}", x, y + 0.01, 0.72, 0.44,
         size=16, bold=True, font=_FONT_TITLE, color=text_color, center=True)

def _footer(slide, repo_name: str) -> None:
    """Thin bottom line + small footer text (template identity)."""
    _thin_line(slide, _H - 0.06, _MAUVE)
    _txt(slide, f"CodeNarrator  ·  {repo_name}",
         0.25, _H - 0.28, 7, 0.22, size=8, color=_MAUVE, italic=True)


# ── Markdown parser ───────────────────────────────────────────────────────────

def _parse_chapter(md_text: str) -> Dict[str, Any]:
    lines = md_text.splitlines()
    title = ""
    sections: Dict[str, List[str]] = {}
    current   = "intro"
    code_blocks: List[str] = []
    in_code   = False
    code_buf: List[str] = []

    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                if code_buf:
                    code_blocks.append("\n".join(code_buf))
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        if line.startswith("# ") and not title:
            raw   = line[2:].strip()
            title = re.sub(r"^Chapter\s+\d+:\s*", "", raw, flags=re.IGNORECASE)
            continue
        if line.startswith("## "):
            h = line[3:].strip().lower()
            current = ("motivation" if "motiv" in h
                       else "core" if "core" in h or "concept" in h
                       else "practical" if "pract" in h
                       else "internal" if "intern" in h
                       else "conclusion" if "concl" in h
                       else h[:20])
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, [])
        sections[current].append(line)

    def _j(k): return "\n".join(sections.get(k, [])).strip()
    def _bl(text, n=5):
        pts = []
        for ln in text.splitlines():
            ln = ln.strip()
            if ln.startswith(("- ", "* ", "• ")) and len(ln) > 4:
                pts.append(ln[2:].strip())
            elif re.match(r"^\d+\.\s", ln):
                pts.append(re.sub(r"^\d+\.\s+", "", ln))
        return pts[:n]

    motivation = _j("motivation")
    core       = _j("core")
    practical  = _j("practical")
    conclusion = _j("conclusion")

    overview_bullets = _bl(motivation) or _bl(core)
    if not overview_bullets:
        for ln in sections.get("intro", []) + sections.get("motivation", []):
            ln = ln.strip()
            if ln and not ln.startswith("#") and len(ln) > 20:
                overview_bullets.append(ln[:120])
                if len(overview_bullets) >= 4:
                    break

    key_concepts: List[Tuple[str, str]] = []
    for src in [core, motivation, practical]:
        for m in re.finditer(r"\*\*(.+?)\*\*\s*[:\-–]?\s*(.+?)(?:\n|$)", src):
            name = m.group(1).strip()
            defn = m.group(2).strip()[:100]
            if name and defn and len(name) < 40:
                key_concepts.append((name, defn))
                if len(key_concepts) >= 4:
                    break
        if len(key_concepts) >= 4:
            break

    steps = _bl(practical, 5) or _bl(core, 5)

    best_code = ""
    for blk in sorted(code_blocks, key=len, reverse=True):
        if len(blk.strip()) > 20:
            best_code = blk.strip()
            break

    summary_bullets = _bl(conclusion, 4)
    if not summary_bullets:
        for ln in conclusion.splitlines():
            ln = ln.strip()
            if len(ln) > 20:
                summary_bullets.append(ln[:120])
                if len(summary_bullets) >= 3:
                    break

    return {
        "title":            title or "Chapter",
        "motivation":       motivation,
        "core":             core,
        "practical":        practical,
        "conclusion":       conclusion,
        "overview_bullets": overview_bullets,
        "key_concepts":     key_concepts,
        "best_code":        best_code,
        "steps":            steps,
        "summary_bullets":  summary_bullets,
        "all_text":         md_text[:3000],
    }


# ── LLM speaker notes ─────────────────────────────────────────────────────────

async def _gen_notes(topic: str, context: str, kind: str) -> str:
    prompts = {
        "overview":  (f"You are an educational content writer. Explain '{topic}' in 4-5 sentences "
                      f"for a complete beginner. Include what it is, why it matters, and a real-world analogy. "
                      f"Context: {context[:500]}"),
        "code":      (f"You are a coding instructor. Walk through this code from '{topic}' line by line "
                      f"for a beginner. Explain what each part does. 4-5 sentences. Code: {context[:400]}"),
        "concepts":  (f"Explain the key concepts of '{topic}' to a beginner in 4-5 sentences. "
                      f"Use simple language and concrete examples. Context: {context[:500]}"),
        "steps":     (f"Give a beginner practical advice for implementing '{topic}'. "
                      f"Include tips, warnings, and best practices. 4-5 sentences. Context: {context[:400]}"),
        "summary":   (f"Summarize what a student should remember after learning '{topic}'. "
                      f"Give 3 key takeaways in 4-5 sentences. End with encouragement. Context: {context[:300]}"),
    }
    try:
        from llm.router import llm_call
        raw = await llm_call(prompts.get(kind, prompts["overview"]), bypass_cache=False)
        return raw.strip()[:1200] if raw else ""
    except Exception as exc:
        logger.warning("Notes gen failed %s/%s: %s", topic, kind, exc)
        return (f"This slide covers key aspects of {topic}. "
                f"Study the content carefully and try implementing the concepts yourself.")


# ── Slide 1: Title ────────────────────────────────────────────────────────────

def _slide_title(prs, topic: str, repo: str, num: int, total: int, notes_txt: str) -> None:
    slide = _blank(prs)
    _solid_bg(slide, _BG)

    # Top thin line (template motif)
    _thin_line(slide, 0.04)

    # Large ghost chapter number (bottom-right, very faint)
    _txt(slide, f"{num:02d}", 6.5, 1.0, 3.2, 3.5,
         size=130, bold=True, font=_FONT_TITLE,
         color=_MAUVE, center=True)

    # Vertical accent bar
    _rect(slide, 0.9, 0.55, 0.04, 4.5, _ACCENT)

    # Chapter label
    _txt(slide, f"CHAPTER {num:02d}", 1.1, 0.6, 5, 0.38,
         size=10, bold=True, font=_FONT_TITLE, color=_ACCENT)

    # Chapter title — Josefin Sans, large, parchment
    lines = textwrap.wrap(topic, 28)
    for li, line in enumerate(lines[:2]):
        _txt(slide, line, 1.1, 1.15 + li * 0.82, 7.2, 0.8,
             size=38, bold=True, font=_FONT_TITLE, color=_PARCH)

    # Repo name
    _txt(slide, f"📦  {repo}", 1.1, 2.9, 7, 0.38,
         size=13, font=_FONT_BODY, color=_ACCENT, italic=True)

    # Subtitle
    _txt(slide, "Code Tutorial", 1.1, 3.38, 4, 0.35,
         size=11, font=_FONT_BODY, color=_MAUVE)

    # Date + position
    date_str = datetime.now().strftime("%B %d, %Y")
    _txt(slide, f"{date_str}  ·  Chapter {num} of {total}", 1.1, 3.78, 6, 0.3,
         size=9, font=_FONT_BODY, color=_MAUVE)

    _footer(slide, repo)
    _notes(slide, notes_txt)


# ── Slide 2: Overview ─────────────────────────────────────────────────────────

def _slide_overview(prs, topic: str, bullets: List[str],
                    repo: str, notes_txt: str) -> None:
    slide = _blank(prs)
    _solid_bg(slide, _BG)
    _thin_line(slide, 0.04)

    # Slide type label
    _txt(slide, "OVERVIEW", 0.35, 0.12, 2, 0.28,
         size=8, bold=True, font=_FONT_TITLE, color=_MAUVE)

    # Heading
    _txt(slide, f"What is {topic}?", 0.35, 0.42, 9, 0.72,
         size=30, bold=True, font=_FONT_TITLE, color=_PARCH)

    # Accent underline (thin line below heading)
    _thin_line(slide, 1.2, _ACCENT)

    # Divider into two zones: bullets (left) + summary card (right)
    # Left: bullet points
    display = bullets[:5] if bullets else [
        f"{topic} is a core concept in this codebase.",
        "It handles a specific responsibility in the system.",
        "Understanding it helps you read and modify the code.",
        "It is used by multiple other components.",
    ]
    _bullet_list(slide, display, 0.35, 1.35, 5.8, 3.8, size=14, color=_PARCH)

    # Right card: decorative info box
    _rect(slide, 6.5, 1.28, 3.15, 3.9, _MAUVE)
    _thin_line(slide, 1.28 + 0.01, _ACCENT)
    _txt(slide, "KEY FOCUS", 6.65, 1.38, 2.8, 0.3,
         size=8, bold=True, font=_FONT_TITLE, color=_ACCENT)
    _txt(slide, textwrap.shorten(bullets[0] if bullets else topic, 160, placeholder="…"),
         6.65, 1.78, 2.85, 2.8,
         size=12, font=_FONT_BODY, color=_PARCH, wrap=True)
    # Small accent tick
    _rect(slide, 6.5, 1.28, 0.05, 3.9, _ACCENT)

    _footer(slide, repo)
    _notes(slide, notes_txt)


# ── Slide 3: Code Walkthrough ─────────────────────────────────────────────────

def _slide_code(prs, topic: str, code: str, repo: str, notes_txt: str) -> None:
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    slide = _blank(prs)
    _solid_bg(slide, _BG)
    _thin_line(slide, 0.04)

    # Label + heading
    _txt(slide, "CODE WALKTHROUGH", 0.35, 0.12, 4, 0.28,
         size=8, bold=True, font=_FONT_TITLE, color=_MAUVE)
    _txt(slide, topic, 0.35, 0.42, 9, 0.62,
         size=26, bold=True, font=_FONT_TITLE, color=_PARCH)
    _thin_line(slide, 1.1, _ACCENT)

    if code:
        # Code panel (left ~60%)
        _rect(slide, 0.35, 1.18, 5.85, 3.98, _CODE_BG)
        # Title bar on code panel
        _rect(slide, 0.35, 1.18, 5.85, 0.3, (0x1E, 0x1D, 0x1E))
        # Traffic-light dots
        for xi, dot in enumerate([(0xBF, 0x56, 0x56), (0xBF, 0xA3, 0x56), (0x5C, 0xBF, 0x56)]):
            _rect(slide, 0.55 + xi * 0.28, 1.24, 0.18, 0.16, dot)
        _txt(slide, f"  {topic.lower().replace(' ', '_')[:18]}.py",
             1.2, 1.21, 4, 0.24, size=9, font="Consolas", color=_MAUVE)

        # Code text
        code_txb = slide.shapes.add_textbox(
            _i(0.42), _i(1.55), _i(5.68), _i(3.5)
        )
        code_tf = code_txb.text_frame
        code_tf.word_wrap = False
        for i, line in enumerate(code.splitlines()[:20]):
            p = code_tf.paragraphs[0] if i == 0 else code_tf.add_paragraph()
            run = p.add_run()
            run.text = line if line else " "
            run.font.name      = "Consolas"
            run.font.size      = Pt(10)
            run.font.color.rgb = RGBColor(*_CODE_TXT)

        # Explanation panel (right ~35%)
        _rect(slide, 6.45, 1.18, 3.2, 3.98, _MAUVE)
        _rect(slide, 6.45, 1.18, 0.05, 3.98, _ACCENT)
        _txt(slide, "WHAT IT DOES", 6.62, 1.26, 2.9, 0.28,
             size=8, bold=True, font=_FONT_TITLE, color=_ACCENT)
        _thin_line(slide, 1.58, _ACCENT)
        expl = notes_txt[:420] if notes_txt else f"This code implements core functionality of {topic}."
        _txt(slide, expl, 6.62, 1.65, 2.9, 3.3,
             size=11, font=_FONT_BODY, color=_PARCH, wrap=True)
    else:
        _rect(slide, 0.35, 1.18, 9.3, 3.98, _MAUVE)
        _txt(slide, f"No code snippet extracted for this chapter.\nSee the chapter text for implementation details.",
             0.5, 2.5, 9.0, 1.5, size=15, color=_PARCH, center=True)

    _footer(slide, repo)
    _notes(slide, notes_txt)


# ── Slide 4: Key Concepts ─────────────────────────────────────────────────────

def _slide_concepts(prs, topic: str, concepts: List[Tuple[str, str]],
                     repo: str, notes_txt: str) -> None:
    slide = _blank(prs)
    _solid_bg(slide, _BG)
    _thin_line(slide, 0.04)

    _txt(slide, "KEY CONCEPTS", 0.35, 0.12, 4, 0.28,
         size=8, bold=True, font=_FONT_TITLE, color=_MAUVE)
    _txt(slide, topic, 0.35, 0.42, 9, 0.62,
         size=26, bold=True, font=_FONT_TITLE, color=_PARCH)
    _thin_line(slide, 1.1, _ACCENT)

    # Pad to 4 concepts
    display = list(concepts[:4])
    while len(display) < 4:
        display.append((f"Concept {len(display)+1}",
                         "A key idea central to understanding this topic."))

    # 2×2 grid
    positions = [(0.35, 1.22), (5.15, 1.22), (0.35, 3.3), (5.15, 3.3)]
    # Alternate card shades for visual rhythm (template uses subtle variation)
    card_fills = [_MAUVE, (0x4A, 0x40, 0x44), _MAUVE, (0x4A, 0x40, 0x44)]

    for i, ((name, defn), (cx, cy)) in enumerate(zip(display, positions)):
        _rect(slide, cx, cy, 4.55, 1.88, card_fills[i])
        _rect(slide, cx, cy, 0.04, 1.88, _ACCENT)   # left accent bar
        # Concept number
        _txt(slide, f"{i+1:02d}", cx + 0.15, cy + 0.08, 0.55, 0.45,
             size=16, bold=True, font=_FONT_TITLE, color=_ACCENT)
        # Concept name
        _txt(slide, name[:36], cx + 0.82, cy + 0.1, 3.6, 0.45,
             size=13, bold=True, font=_FONT_TITLE, color=_PARCH)
        # Definition
        _txt(slide, textwrap.shorten(defn, 120, placeholder="…"),
             cx + 0.15, cy + 0.6, 4.25, 1.18,
             size=11, font=_FONT_BODY, color=_PARCH, wrap=True)

    _footer(slide, repo)
    _notes(slide, notes_txt)


# ── Slide 5: Tutorial Steps ───────────────────────────────────────────────────

def _slide_steps(prs, topic: str, steps: List[str],
                  repo: str, notes_txt: str) -> None:
    slide = _blank(prs)
    _solid_bg(slide, _BG)
    _thin_line(slide, 0.04)

    _txt(slide, "TUTORIAL STEPS", 0.35, 0.12, 4, 0.28,
         size=8, bold=True, font=_FONT_TITLE, color=_MAUVE)
    _txt(slide, f"How to Use {topic}", 0.35, 0.42, 9, 0.62,
         size=26, bold=True, font=_FONT_TITLE, color=_PARCH)
    _thin_line(slide, 1.1, _ACCENT)

    display_steps = steps[:5] if steps else [
        f"Import {topic} into your project",
        "Configure the required parameters",
        "Test with a simple example first",
        "Integrate with the rest of the codebase",
        "Test edge cases and handle errors",
    ]

    # Step rows
    for i, step in enumerate(display_steps):
        sy = 1.2 + i * 0.76
        # Number circle
        _rect(slide, 0.35, sy, 0.52, 0.52, _ACCENT)
        _txt(slide, str(i + 1), 0.35, sy, 0.52, 0.52,
             size=14, bold=True, font=_FONT_TITLE, color=_BG, center=True)
        # Step background
        _rect(slide, 1.05, sy, 5.65, 0.52, _MAUVE)
        _txt(slide, textwrap.shorten(step, 95, placeholder="…"),
             1.18, sy + 0.04, 5.42, 0.44,
             size=12, font=_FONT_BODY, color=_PARCH)

    # Tips column (right)
    _rect(slide, 7.0, 1.18, 2.65, 3.88, _MAUVE)
    _rect(slide, 7.0, 1.18, 0.04, 3.88, _ACCENT)
    _txt(slide, "TIPS", 7.12, 1.26, 2.4, 0.3,
         size=9, bold=True, font=_FONT_TITLE, color=_ACCENT)
    _thin_line(slide, 1.6, _ACCENT)
    tips = notes_txt[:380] if notes_txt else f"Read the official documentation for {topic}. Start with simple use-cases before advanced ones."
    _txt(slide, tips, 7.12, 1.68, 2.42, 3.2,
         size=10, font=_FONT_BODY, color=_PARCH, wrap=True)

    _footer(slide, repo)
    _notes(slide, notes_txt)


# ── Slide 6: Summary ──────────────────────────────────────────────────────────

def _slide_summary(prs, topic: str, summary_bullets: List[str],
                    next_ch: str, repo: str, notes_txt: str) -> None:
    slide = _blank(prs)
    _solid_bg(slide, _BG)
    _thin_line(slide, 0.04)

    # Large background text (ghost)
    _txt(slide, "END", 4.5, 0.9, 5, 3.5,
         size=160, bold=True, font=_FONT_TITLE,
         color=_MAUVE, center=True)

    # Overlay content
    _txt(slide, "SUMMARY", 0.35, 0.12, 3, 0.28,
         size=8, bold=True, font=_FONT_TITLE, color=_MAUVE)
    _txt(slide, f"What You Learned — {topic}", 0.35, 0.42, 8.5, 0.65,
         size=26, bold=True, font=_FONT_TITLE, color=_PARCH)
    _thin_line(slide, 1.12, _ACCENT)

    # Checklist (left panel)
    disp = summary_bullets[:4] if summary_bullets else [
        f"The purpose and role of {topic}",
        "How to read and understand the code",
        "Key concepts and real-world applications",
        "How to implement this in your own project",
    ]
    for i, item in enumerate(disp):
        iy = 1.22 + i * 0.82
        _rect(slide, 0.35, iy, 0.46, 0.46, _ACCENT)
        _txt(slide, "✓", 0.35, iy, 0.46, 0.46,
             size=14, bold=True, font=_FONT_TITLE, color=_BG, center=True)
        _txt(slide, textwrap.shorten(item, 80, placeholder="…"),
             0.95, iy + 0.06, 4.8, 0.44,
             size=12, font=_FONT_BODY, color=_PARCH)

    # What's next card (right)
    _rect(slide, 6.2, 1.18, 3.45, 2.15, _MAUVE)
    _rect(slide, 6.2, 1.18, 0.04, 2.15, _ACCENT)
    _txt(slide, "NEXT UP", 6.35, 1.26, 3.0, 0.3,
         size=9, bold=True, font=_FONT_TITLE, color=_ACCENT)
    _thin_line(slide, 1.6, _ACCENT)
    next_text = next_ch if next_ch else "Continue to the next chapter to deepen your understanding."
    _txt(slide, next_text, 6.35, 1.68, 3.18, 1.5,
         size=11, font=_FONT_BODY, color=_PARCH, wrap=True)

    # Practice card (right, below)
    _rect(slide, 6.2, 3.55, 3.45, 1.5, _MAUVE)
    _rect(slide, 6.2, 3.55, 0.04, 1.5, _ACCENT)
    _txt(slide, "PRACTISE", 6.35, 3.63, 3.0, 0.3,
         size=9, bold=True, font=_FONT_TITLE, color=_ACCENT)
    _txt(slide, f"Try implementing {topic[:30]} in a side project to solidify your learning.",
         6.35, 3.98, 3.18, 0.95,
         size=10, font=_FONT_BODY, color=_PARCH, wrap=True)

    _footer(slide, repo)
    _notes(slide, notes_txt)


# ── Cover slide ───────────────────────────────────────────────────────────────

def _build_cover(prs, repo: str, ch_count: int) -> None:
    slide = _blank(prs)
    _solid_bg(slide, _BG)

    _thin_line(slide, 0.04)
    _thin_line(slide, _H - 0.06, _MAUVE)

    # Ghost watermark
    _txt(slide, "CODE", 3.5, 0.3, 6, 4,
         size=120, bold=True, font=_FONT_TITLE,
         color=_MAUVE, center=True)

    # Vertical accent bar
    _rect(slide, 1.2, 0.5, 0.05, 4.5, _ACCENT)

    # Title
    _txt(slide, repo, 1.5, 0.55, 8, 1.1,
         size=42, bold=True, font=_FONT_TITLE, color=_PARCH)

    # Subtitle
    _txt(slide, "AI-Generated Code Tutorial", 1.5, 1.75, 7, 0.5,
         size=18, italic=True, font=_FONT_BODY, color=_ACCENT)

    # Divider
    _thin_line(slide, 2.42, _MAUVE)

    # Stats
    date_str = datetime.now().strftime("%B %d, %Y")
    _txt(slide, f"{ch_count} Chapters   ·   Beginner Friendly   ·   {date_str}",
         1.5, 2.6, 7.5, 0.38, size=12, font=_FONT_BODY, color=_MAUVE)

    # Description
    _txt(slide,
         "Each chapter contains 6 slides: Title · Overview · Code · Concepts · Steps · Summary\n"
         "Speaker notes on every slide provide detailed explanations for self-study.",
         1.5, 3.15, 7.5, 0.9, size=11, font=_FONT_BODY, color=_MAUVE, wrap=True)

    # Badge
    _rect(slide, 1.5, 4.3, 3.6, 0.6, _MAUVE)
    _rect(slide, 1.5, 4.3, 0.04, 0.6, _ACCENT)
    _txt(slide, "  ⚡  Generated by CodeNarrator", 1.6, 4.35, 3.4, 0.5,
         size=11, bold=True, font=_FONT_TITLE, color=_PARCH)


# ── Main async export ─────────────────────────────────────────────────────────

async def export_to_pptx_educational(job_output_dir: str) -> Dict[str, Any]:
    """
    Async entry point. Reads markdown chapters, builds 6-slide-per-chapter
    educational PPTX in the Archival/Scholarly dark theme.
    """
    try:
        from pptx import Presentation  # noqa — just verify installed
    except ImportError:
        return {"success": False,
                "error": "python-pptx not installed. Run: pip install python-pptx"}

    out_dir  = Path(job_output_dir)
    out_pptx = out_dir / "tutorial_educational.pptx"

    md_files = sorted(
        [f for f in out_dir.glob("*.md") if f.name != "index.md"],
        key=lambda p: p.name,
    )
    if not md_files:
        return {"success": False,
                "error": "No chapter .md files found — run text generation first"}

    # Derive repo name
    repo_name = "Code Tutorial"
    idx_path  = out_dir / "index.md"
    if idx_path.exists():
        m = re.search(r"^#\s+(.+)", idx_path.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            repo_name = m.group(1).strip()[:55]

    chapters = []
    for f in md_files:
        try:
            chapters.append(_parse_chapter(f.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("Parse failed %s: %s", f.name, exc)

    if not chapters:
        return {"success": False, "error": "Could not parse any chapter files"}

    total = len(chapters)
    print(f"PPTXedu: {total} chapters x 6 slides + 1 cover  |  theme: Archival/Scholarly")

    # ── Generate speaker notes in parallel batches ──────────────────────────
    print("PPTXedu: generating AI speaker notes (async)...")

    async def _ch_notes(ch: Dict) -> Dict[str, str]:
        topic = ch["title"]
        results = await asyncio.gather(
            _gen_notes(topic, ch["motivation"] or ch["all_text"], "overview"),
            _gen_notes(topic, ch["best_code"] or ch["core"],       "code"),
            _gen_notes(topic, ch["core"],                          "concepts"),
            _gen_notes(topic, ch["practical"],                     "steps"),
            _gen_notes(topic, ch["conclusion"] or ch["core"],      "summary"),
        )
        return {"title": results[0][:200], "overview": results[0],
                "code": results[1], "concepts": results[2],
                "steps": results[3], "summary": results[4]}

    all_notes = []
    for i in range(0, total, 2):
        batch = await asyncio.gather(*[_ch_notes(ch) for ch in chapters[i:i+2]])
        all_notes.extend(batch)
        if i + 2 < total:
            await asyncio.sleep(1)

    # ── Build presentation ───────────────────────────────────────────────────
    prs = _new_prs()
    _build_cover(prs, repo_name, total)

    for i, (ch, nt) in enumerate(zip(chapters, all_notes), start=1):
        topic   = ch["title"]
        next_ch = chapters[i]["title"] if i < total else ""
        print(f"PPTXedu: [{i}/{total}] '{topic}'")

        _slide_title(prs, topic, repo_name, i, total, nt["title"])
        _slide_overview(prs, topic, ch["overview_bullets"], repo_name, nt["overview"])
        _slide_code(prs, topic, ch["best_code"], repo_name, nt["code"])
        _slide_concepts(prs, topic, ch["key_concepts"], repo_name, nt["concepts"])
        _slide_steps(prs, topic, ch["steps"], repo_name, nt["steps"])
        _slide_summary(prs, topic, ch["summary_bullets"], next_ch, repo_name, nt["summary"])

    prs.save(str(out_pptx))
    size_mb = out_pptx.stat().st_size / (1024 * 1024)
    slides  = 1 + total * 6
    print(f"PPTXedu: DONE  tutorial_educational.pptx  {size_mb:.1f} MB  {slides} slides")
    return {"success": True, "output_path": str(out_pptx),
            "slides": slides, "chapters": total, "size_mb": round(size_mb, 2)}


# ── Backwards-compatible sync wrapper ────────────────────────────────────────

def export_to_pptx(job_output_dir: str, video_script: list) -> Dict[str, Any]:
    """Sync wrapper — video_script is ignored; chapters come from disk."""
    try:
        return asyncio.run(export_to_pptx_educational(job_output_dir))
    except RuntimeError:
        return asyncio.get_event_loop().run_until_complete(
            export_to_pptx_educational(job_output_dir))
