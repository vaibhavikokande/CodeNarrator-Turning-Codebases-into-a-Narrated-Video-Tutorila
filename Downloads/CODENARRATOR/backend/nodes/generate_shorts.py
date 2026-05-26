"""
generate_shorts.py — Short-form clip generator (ADDITIVE, standalone module).

Completely independent of the main video pipeline.
Called AFTER tutorial.mp4 is already generated, as a post-processing step.

What it does:
  1. Reads the merged/ clip directory that AssembleVideo already produces
  2. Uses ffprobe to get the exact duration of every merged clip
  3. Identifies chapter boundaries from filenames (trans_ prefix marks chapter start)
  4. Cuts tutorial.mp4 at those boundaries → one MP4 per chapter → shorts/ folder
  5. If a chapter exceeds MAX_SHORT_SECS (60 s), further splits it into sub-clips
     named  chapter_01_title_part1.mp4,  chapter_01_title_part2.mp4, etc.

Output structure:
  output/<job_id>/shorts/
    chapter_01_<slug>.mp4
    chapter_02_<slug>.mp4
    ...
    chapter_01_<slug>_part1.mp4   (only if chapter > 60 s)
    chapter_01_<slug>_part2.mp4

This file does NOT import from or modify any existing pipeline node.
"""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_SHORT_SECS = 60.0   # YouTube Shorts maximum duration


# ── FFmpeg / ffprobe helpers ──────────────────────────────────────────────────

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
    """Return duration of a video/audio file in seconds."""
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             path],
            capture_output=True, text=True, timeout=15,
        )
        return max(float(r.stdout.strip()), 0.1)
    except Exception:
        return 4.0   # safe fallback


def _cut_segment(
    ffmpeg: str,
    source: str,
    start: float,
    duration: float,
    output: str,
) -> bool:
    """Extract a time slice from source video. Returns True on success."""
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{start:.3f}",
        "-i", source,
        "-t",  f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and Path(output).exists() and Path(output).stat().st_size > 1000:
            return True
        logger.error("FFmpeg cut failed for %s:\n%s", output, r.stderr[-400:])
        return False
    except Exception as exc:
        logger.error("FFmpeg cut exception: %s", exc)
        return False


# ── Chapter boundary detection ────────────────────────────────────────────────

def _slug(text: str) -> str:
    """Convert chapter title to filename-safe slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "_", text)
    return text[:40].strip("_") or "chapter"


def _parse_merged_clips(merged_dir: Path, ffprobe: str) -> List[Dict[str, Any]]:
    """
    Scan the merged/ directory and return a list of clip info dicts, sorted
    by clip index.

    Each dict:
      { "path": str, "label": str, "duration": float,
        "is_trans": bool, "is_intro": bool, "is_outro": bool }
    """
    clips = []
    # clips are named  clip_NNN_label.mp4
    pattern = re.compile(r"^clip_(\d+)_(.+)\.mp4$", re.IGNORECASE)

    for f in sorted(merged_dir.iterdir()):
        m = pattern.match(f.name)
        if not m:
            continue
        idx   = int(m.group(1))
        label = m.group(2)
        dur   = _clip_duration(ffprobe, str(f))
        clips.append({
            "index":    idx,
            "path":     str(f),
            "label":    label,
            "duration": dur,
            "is_intro": label == "intro",
            "is_outro": label == "outro",
            "is_trans": label.startswith("trans_"),
        })

    clips.sort(key=lambda c: c["index"])
    return clips


def _build_chapter_timeline(
    clips: List[Dict[str, Any]],
    video_script: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Walk through clips in order, accumulate timestamps, and return
    a list of chapter dicts:
      { "number": int, "title": str, "start": float, "end": float }
    """
    # Build a map: chapter_number → title, from video_script
    ch_titles: Dict[int, str] = {}
    ch_idx = 0
    for seg in video_script:
        if seg.get("type") == "chapter_intro":
            ch_idx += 1
            dc = seg.get("display_content", {})
            title = (dc.get("chapter_title", "") if isinstance(dc, dict) else "") or f"Chapter {ch_idx}"
            ch_titles[ch_idx] = title

    chapters      = []
    current_ch    = 0
    current_start = 0.0
    cumulative    = 0.0

    for clip in clips:
        dur = clip["duration"]

        if clip["is_trans"]:
            # A transition marks the END of the previous chapter and start of new one
            if current_ch > 0:
                chapters.append({
                    "number": current_ch,
                    "title":  ch_titles.get(current_ch, f"Chapter {current_ch}"),
                    "start":  current_start,
                    "end":    cumulative,
                })
            current_ch    += 1
            current_start  = cumulative   # transition itself is part of next chapter

        cumulative += dur

    # Close final chapter (before outro)
    if current_ch > 0:
        # Find where outro begins
        outro_start = cumulative
        for clip in reversed(clips):
            if clip["is_outro"]:
                outro_start = cumulative - clip["duration"]
                break
        chapters.append({
            "number": current_ch,
            "title":  ch_titles.get(current_ch, f"Chapter {current_ch}"),
            "start":  current_start,
            "end":    outro_start,
        })

    return chapters


# ── Main public function ──────────────────────────────────────────────────────

def generate_short_clips(
    job_output_dir: str,
    video_script:   List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Main entry point. Called from the FastAPI endpoint.

    Args:
        job_output_dir : e.g. "./output/<job_id>"
        video_script   : shared["video_script"]

    Returns:
        {
          "success":  True,
          "clips":    [ {"filename": "chapter_01_foo.mp4", "duration": 42.3,
                         "download_url": "/api/jobs/<id>/file/shorts/chapter_01_foo.mp4"}, ... ],
          "chapters": N,
        }
        or {"success": False, "error": "..."}
    """
    out_dir    = Path(job_output_dir)
    main_video = out_dir / "tutorial.mp4"
    merged_dir = out_dir / "merged"
    shorts_dir = out_dir / "shorts"

    if not main_video.exists():
        return {"success": False, "error": "tutorial.mp4 not found — generate the video first"}
    if not merged_dir.exists():
        return {"success": False, "error": "merged/ directory not found — generate the video first"}

    shorts_dir.mkdir(exist_ok=True)

    ffmpeg  = _get_ffmpeg()
    ffprobe = _get_ffprobe(ffmpeg)

    # Step 1: Build clip timeline from merged/ directory
    logger.info("Shorts: scanning merged clips…")
    clips = _parse_merged_clips(merged_dir, ffprobe)
    if not clips:
        return {"success": False, "error": "No merged clips found in merged/ directory"}

    # Step 2: Identify chapter boundaries
    chapters = _build_chapter_timeline(clips, video_script)
    if not chapters:
        return {"success": False, "error": "Could not identify chapter boundaries from video_script"}

    logger.info("Shorts: found %d chapters", len(chapters))

    # Step 3: Cut one clip per chapter; split if > MAX_SHORT_SECS
    output_clips = []

    for ch in chapters:
        ch_num    = ch["number"]
        ch_title  = ch["title"]
        ch_start  = ch["start"]
        ch_dur    = max(ch["end"] - ch["start"], 0.5)
        slug      = _slug(ch_title)
        base_name = f"chapter_{ch_num:02d}_{slug}"

        if ch_dur <= MAX_SHORT_SECS:
            # Single clip for this chapter
            out_path = shorts_dir / f"{base_name}.mp4"
            ok = _cut_segment(ffmpeg, str(main_video), ch_start, ch_dur, str(out_path))
            if ok:
                actual_dur = _clip_duration(ffprobe, str(out_path))
                output_clips.append({
                    "filename":  out_path.name,
                    "chapter":   ch_num,
                    "title":     ch_title,
                    "duration":  round(actual_dur, 1),
                    "part":      None,
                })
                logger.info("Shorts: %s  (%.1fs)", out_path.name, actual_dur)
        else:
            # Split into 60-second sub-clips
            part      = 1
            offset    = 0.0
            while offset < ch_dur:
                seg_dur   = min(MAX_SHORT_SECS, ch_dur - offset)
                if seg_dur < 5.0:
                    break          # skip tiny tail fragments
                out_path  = shorts_dir / f"{base_name}_part{part}.mp4"
                ok = _cut_segment(
                    ffmpeg, str(main_video),
                    ch_start + offset, seg_dur, str(out_path),
                )
                if ok:
                    actual_dur = _clip_duration(ffprobe, str(out_path))
                    output_clips.append({
                        "filename": out_path.name,
                        "chapter":  ch_num,
                        "title":    f"{ch_title} (Part {part})",
                        "duration": round(actual_dur, 1),
                        "part":     part,
                    })
                    logger.info("Shorts: %s  (%.1fs)", out_path.name, actual_dur)
                offset += MAX_SHORT_SECS
                part   += 1

    if not output_clips:
        return {"success": False, "error": "No short clips could be generated"}

    total_dur = sum(c["duration"] for c in output_clips)
    logger.info(
        "Shorts: done — %d clips, total %.1fs", len(output_clips), total_dur
    )
    return {
        "success":  True,
        "chapters": len(chapters),
        "clips":    output_clips,
    }


def list_existing_shorts(job_output_dir: str) -> List[Dict[str, Any]]:
    """Return already-generated short clips without re-processing."""
    shorts_dir = Path(job_output_dir) / "shorts"
    if not shorts_dir.exists():
        return []
    clips = []
    for f in sorted(shorts_dir.glob("*.mp4")):
        clips.append({
            "filename": f.name,
            "size_mb":  round(f.stat().st_size / (1024 * 1024), 2),
        })
    return clips
