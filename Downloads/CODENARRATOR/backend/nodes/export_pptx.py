"""
export_pptx.py — PowerPoint export (ADDITIVE, standalone module).

Completely independent of the main video pipeline.
Called AFTER tutorial generation, as an on-demand export step.

What it does:
  1. For each segment in video_script, extracts the mid-point frame from
     the corresponding visual clip (segment_NNN.mp4) using FFmpeg
  2. Creates one 16:9 slide per segment using python-pptx:
       • Full-bleed background = the extracted frame
       • Slide title label     = segment type + title/concept text
       • Speaker notes         = narration text (for presenter view)
  3. Chapter intro segments get a special divider-slide style
  4. Saves tutorial.pptx to the job output directory

This file does NOT import from or modify any existing pipeline node.
"""

import io
import logging
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Slide dimensions — 16:9 widescreen
_SLIDE_W_IN = 13.333   # inches
_SLIDE_H_IN = 7.5      # inches

# Colour palette matching the video's GitHub Dark theme
_C_BG       = "0D1117"
_C_ACCENT   = "58A6FF"
_C_TEXT     = "E6EDF3"
_C_MUTED    = "8B949E"
_C_GREEN    = "3FB950"
_C_PURPLE   = "BC8CFF"
_C_CARD     = "161B22"
_C_BORDER   = "30363D"


# ── FFmpeg helpers ────────────────────────────────────────────────────────────

def _get_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _get_ffprobe(ffmpeg: str) -> str:
    probe = ffmpeg.replace("ffmpeg", "ffprobe")
    if os.path.exists(probe):
        return probe
    p = shutil.which("ffprobe")
    return p or probe


def _clip_duration(ffprobe: str, path: str) -> float:
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return max(float(r.stdout.strip()), 0.5)
    except Exception:
        return 3.0


def _extract_frame(ffmpeg: str, clip_path: str, timestamp: float, out_path: str) -> bool:
    """Extract a single JPEG frame from a video at the given timestamp."""
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{timestamp:.3f}",
        "-i", clip_path,
        "-vframes", "1",
        "-q:v", "2",        # high quality JPEG
        "-vf", "scale=1280:720",   # consistent frame size
        out_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        return r.returncode == 0 and Path(out_path).exists()
    except Exception:
        return False


# ── python-pptx helpers ───────────────────────────────────────────────────────

def _hex_to_rgb(hex_str: str):
    """Convert 6-char hex string to pptx RGBColor."""
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    h = hex_str.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _add_text_box(slide, text: str, left_in: float, top_in: float,
                  width_in: float, height_in: float,
                  font_size: int = 18, bold: bool = False,
                  color_hex: str = _C_TEXT,
                  bg_hex: Optional[str] = None,
                  alpha: int = 180,
                  wrap_width: int = 60) -> None:
    """Add a styled text box to a slide."""
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    txBox = slide.shapes.add_textbox(
        Inches(left_in), Inches(top_in),
        Inches(width_in), Inches(height_in),
    )
    tf = txBox.text_frame
    tf.word_wrap = True

    # Background fill on the text box shape
    if bg_hex:
        fill = txBox.fill
        fill.solid()
        fill.fore_color.rgb = _hex_to_rgb(bg_hex)

    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    wrapped = textwrap.fill(text, wrap_width)
    run.text = wrapped
    run.font.size  = Pt(font_size)
    run.font.bold  = bold
    run.font.color.rgb = _hex_to_rgb(color_hex)


def _add_full_bleed_image(slide, image_path: str) -> None:
    """Set an image as the full-bleed slide background."""
    from pptx.util import Inches
    pic = slide.shapes.add_picture(
        image_path,
        Inches(0), Inches(0),
        Inches(_SLIDE_W_IN), Inches(_SLIDE_H_IN),
    )
    # Move to back (index 0)
    slide.shapes._spTree.remove(pic._element)
    slide.shapes._spTree.insert(2, pic._element)


def _add_dark_fallback_bg(slide, title_text: str = "") -> None:
    """Fallback: solid dark background when no frame image is available."""
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor

    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = _hex_to_rgb(_C_BG)

    if title_text:
        _add_text_box(
            slide, title_text,
            left_in=1.0, top_in=2.5, width_in=11.33, height_in=2.0,
            font_size=40, bold=True, color_hex=_C_TEXT,
        )


def _set_speaker_notes(slide, narration: str) -> None:
    """Add narration text as presenter/speaker notes."""
    if not narration:
        return
    notes_slide = slide.notes_slide
    tf = notes_slide.notes_text_frame
    tf.text = narration


# ── Segment title extraction ──────────────────────────────────────────────────

def _get_slide_title(seg: dict) -> str:
    """Extract a short display title from a segment dict."""
    seg_type = seg.get("type", "slide")
    dc = seg.get("display_content", {})

    if isinstance(dc, str):
        return dc.split("\n")[0][:60]

    if seg_type == "title":
        return dc.get("title", dc.get("text", "Introduction"))[:60]
    if seg_type == "chapter_intro":
        num   = dc.get("chapter_number", "")
        title = dc.get("chapter_title", "")
        return f"Chapter {num}: {title}"[:60]
    if seg_type == "definition":
        return dc.get("concept", dc.get("term", "Definition"))[:60]
    if seg_type == "code":
        fname = dc.get("filename", "")
        purp  = dc.get("purpose", "Code")
        return (fname or purp)[:60]
    if seg_type == "architecture":
        return "Architecture Overview"
    if seg_type == "summary":
        return dc.get("heading", "Summary")[:60]
    if seg_type == "bullets":
        return dc.get("title", "Key Points")[:60]

    return dc.get("title", dc.get("text", seg_type.title()))[:60]


def _get_label_color(seg_type: str) -> str:
    """Return accent colour for the type label pill."""
    return {
        "title":        _C_ACCENT,
        "chapter_intro":_C_PURPLE,
        "code":         _C_GREEN,
        "definition":   _C_ACCENT,
        "architecture": "D29922",
        "summary":      _C_ACCENT,
    }.get(seg_type, _C_MUTED)


# ── Main export function ──────────────────────────────────────────────────────

def export_to_pptx(
    job_output_dir: str,
    video_script:   List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Main entry point. Called from the FastAPI endpoint.

    Args:
        job_output_dir : e.g. "./output/<job_id>"
        video_script   : shared["video_script"]

    Returns:
        {"success": True,  "output_path": ".../tutorial.pptx", "slides": N}
        {"success": False, "error": "..."}
    """
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
    except ImportError:
        return {"success": False,
                "error": "python-pptx not installed. Run: pip install python-pptx"}

    out_dir     = Path(job_output_dir)
    visuals_dir = out_dir / "visuals"
    tmp_dir     = out_dir / "_pptx_frames"
    out_pptx    = out_dir / "tutorial.pptx"

    if not visuals_dir.exists():
        return {"success": False,
                "error": "visuals/ not found — run video generation first"}

    tmp_dir.mkdir(exist_ok=True)
    ffmpeg  = _get_ffmpeg()
    ffprobe = _get_ffprobe(ffmpeg)

    # ── Create presentation ──────────────────────────────────────────────────
    prs = Presentation()
    prs.slide_width  = Inches(_SLIDE_W_IN)
    prs.slide_height = Inches(_SLIDE_H_IN)

    # Use blank layout (index 6) for all slides
    blank_layout = prs.slide_layouts[6]

    slides_added = 0

    for idx, seg in enumerate(video_script):
        seg_type  = seg.get("type", "slide")
        narration = str(seg.get("narration", "")).strip()
        title     = _get_slide_title(seg)
        clip_path = visuals_dir / f"segment_{idx:03d}.mp4"

        slide = prs.slides.add_slide(blank_layout)

        # ── Extract mid-point frame from visual clip ──────────────────────
        frame_path = str(tmp_dir / f"frame_{idx:03d}.jpg")
        frame_ok   = False

        if clip_path.exists():
            duration  = _clip_duration(ffprobe, str(clip_path))
            # Use 60 % through the clip — animations are fully visible by then
            timestamp = duration * 0.60
            frame_ok  = _extract_frame(ffmpeg, str(clip_path), timestamp, frame_path)

        if frame_ok:
            _add_full_bleed_image(slide, frame_path)
        else:
            # Fallback: dark background with title text
            _add_dark_fallback_bg(slide, title)

        # ── Bottom label bar (semi-transparent) ──────────────────────────
        # Dark strip at bottom with segment type badge + title
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        # Background strip
        strip = slide.shapes.add_shape(
            1,   # MSO_SHAPE_TYPE.RECTANGLE
            Inches(0), Inches(6.6),
            Inches(_SLIDE_W_IN), Inches(0.9),
        )
        strip.fill.solid()
        strip.fill.fore_color.rgb = _hex_to_rgb("0A0F16")  # slightly darker than C_BG
        strip.line.fill.background()   # no border line

        # Type badge text
        badge_label = seg_type.replace("_", " ").upper()
        badge_color = _get_label_color(seg_type)
        _add_text_box(
            slide,
            badge_label,
            left_in=0.15, top_in=6.65, width_in=1.8, height_in=0.55,
            font_size=11, bold=True, color_hex=badge_color,
        )

        # Slide title
        _add_text_box(
            slide,
            title,
            left_in=2.0, top_in=6.62, width_in=10.8, height_in=0.6,
            font_size=20, bold=True, color_hex=_C_TEXT,
        )

        # Slide number (top-right corner)
        _add_text_box(
            slide,
            f"{idx + 1} / {len(video_script)}",
            left_in=12.3, top_in=0.1, width_in=1.0, height_in=0.35,
            font_size=10, bold=False, color_hex=_C_MUTED,
        )

        # ── Speaker notes = narration ─────────────────────────────────────
        if narration:
            _set_speaker_notes(slide, narration)

        slides_added += 1

    if slides_added == 0:
        return {"success": False, "error": "No slides were generated"}

    # ── Save PPTX ────────────────────────────────────────────────────────────
    prs.save(str(out_pptx))

    # Clean up temp frames
    import shutil as _sh
    _sh.rmtree(tmp_dir, ignore_errors=True)

    size_mb = out_pptx.stat().st_size / (1024 * 1024)
    logger.info("PPTX export done → tutorial.pptx  %.1f MB  %d slides", size_mb, slides_added)

    return {
        "success":     True,
        "output_path": str(out_pptx),
        "slides":      slides_added,
        "size_mb":     round(size_mb, 2),
    }
