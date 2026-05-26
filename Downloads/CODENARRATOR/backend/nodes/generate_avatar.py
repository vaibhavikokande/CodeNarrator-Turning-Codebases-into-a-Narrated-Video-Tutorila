"""
generate_avatar.py — Talking Avatar overlay (ADDITIVE, standalone module).

Completely independent of the main video pipeline.
Called AFTER tutorial.mp4 is already generated, as a post-processing step.

Supports:
  • D-ID  (https://www.d-id.com)   — set DID_API_KEY  in .env
  • HeyGen (https://www.heygen.com) — set HEYGEN_API_KEY in .env

Workflow:
  1. Send combined narration text (or audio URL) to D-ID / HeyGen
  2. Poll until the avatar video is ready
  3. Download the avatar clip
  4. Use FFmpeg to overlay the avatar in the bottom-right corner
     of the existing tutorial.mp4  → saves tutorial_with_avatar.mp4

This file does NOT import from or modify any existing pipeline node.
"""

import asyncio
import base64
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
DID_API_KEY    = os.environ.get("DID_API_KEY", "")
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")

# Default stock avatar image hosted by D-ID (royalty-free)
DEFAULT_AVATAR_IMAGE = (
    "https://create-images-results.d-id.com/DefaultPresenters/Noelle_f/image.jpeg"
)

_POLL_INTERVAL = 4   # seconds between status checks
_MAX_POLLS     = 90  # give up after 6 minutes


# ── FFmpeg helper ────────────────────────────────────────────────────────────

def _get_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _overlay_avatar(
    main_video: str,
    avatar_video: str,
    output_path: str,
    position: str = "bottomright",   # topleft | topright | bottomleft | bottomright
    scale: float  = 0.22,            # avatar width as fraction of main video width
) -> bool:
    """
    Overlay avatar_video (corner picture-in-picture) onto main_video.
    Returns True on success.
    """
    ffmpeg = _get_ffmpeg()

    # Map position name → FFmpeg overlay expression
    pos_map = {
        "topleft":     "10:10",
        "topright":    "W-w-10:10",
        "bottomleft":  "10:H-h-10",
        "bottomright": "W-w-10:H-h-10",
    }
    overlay_pos = pos_map.get(position, pos_map["bottomright"])

    cmd = [
        ffmpeg, "-y",
        "-i", main_video,
        "-i", avatar_video,
        "-filter_complex",
        (
            f"[1:v]scale=iw*{scale}:-1,"                       # scale avatar
            f"format=yuva420p,"                                  # keep alpha if any
            f"geq=r='r(X,Y)':a='if(gt(r(X,Y)+g(X,Y)+b(X,Y),30),255,0)'[avatar];"  # remove near-black bg
            f"[0:v][avatar]overlay={overlay_pos}:shortest=1[vout]"
        ),
        "-map", "[vout]",
        "-map", "0:a",                 # keep original audio
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and Path(output_path).exists():
            logger.info("Avatar overlay written → %s", output_path)
            return True
        logger.error("FFmpeg overlay failed:\n%s", r.stderr[-600:])
        return False
    except Exception as exc:
        logger.error("FFmpeg overlay exception: %s", exc)
        return False


# ── D-ID provider ─────────────────────────────────────────────────────────────

async def _did_generate_avatar(
    narration_text: str,
    avatar_image_url: str,
    api_key: str,
    tmp_path: Path,
) -> Optional[str]:
    """
    Use D-ID /talks API to generate a talking-head video.
    Returns local path to downloaded avatar MP4, or None on failure.
    """
    # D-ID uses Basic auth: base64(api_key:)
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    # Truncate narration to D-ID max (≈5 min speech ≈ 4000 chars)
    text = narration_text[:4000].strip() or "Welcome to this code tutorial."

    payload = {
        "source_url": avatar_image_url,
        "script": {
            "type":     "text",
            "input":    text,
            "provider": {
                "type":  "microsoft",
                "voice_id": "en-US-JennyNeural",
            },
        },
        "config": {"fluent": True, "pad_audio": 0.0},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create talk
        resp = await client.post(
            "https://api.d-id.com/talks", json=payload, headers=headers
        )
        if resp.status_code not in (200, 201):
            logger.error("D-ID create failed %d: %s", resp.status_code, resp.text[:300])
            return None

        talk_id = resp.json().get("id")
        if not talk_id:
            logger.error("D-ID response missing id: %s", resp.text[:200])
            return None

        logger.info("D-ID talk created: %s", talk_id)

        # Poll for completion
        for attempt in range(_MAX_POLLS):
            await asyncio.sleep(_POLL_INTERVAL)
            status_resp = await client.get(
                f"https://api.d-id.com/talks/{talk_id}", headers=headers
            )
            data   = status_resp.json()
            status = data.get("status", "")
            logger.debug("D-ID poll %d: status=%s", attempt, status)

            if status == "done":
                video_url = data.get("result_url", "")
                if not video_url:
                    logger.error("D-ID done but no result_url")
                    return None
                # Download avatar video
                dl = await client.get(video_url, timeout=120.0)
                avatar_path = tmp_path / "avatar_raw.mp4"
                avatar_path.write_bytes(dl.content)
                logger.info("D-ID avatar downloaded → %s", avatar_path)
                return str(avatar_path)

            if status in ("error", "failed"):
                logger.error("D-ID talk failed: %s", data)
                return None

    logger.error("D-ID polling timed out after %d attempts", _MAX_POLLS)
    return None


# ── HeyGen provider ───────────────────────────────────────────────────────────

async def _heygen_generate_avatar(
    narration_text: str,
    avatar_id: str,
    api_key: str,
    tmp_path: Path,
) -> Optional[str]:
    """
    Use HeyGen v2 API to generate a talking avatar video.
    Returns local path to downloaded avatar MP4, or None on failure.
    avatar_id: a HeyGen avatar_id string from your HeyGen account.
    """
    headers = {
        "X-Api-Key":    api_key,
        "Content-Type": "application/json",
        "Accept":       "application/json",
    }

    text = narration_text[:1500].strip() or "Welcome to this code tutorial."

    payload = {
        "video_inputs": [
            {
                "character": {
                    "type":      "avatar",
                    "avatar_id": avatar_id,
                    "scale":     1.0,
                },
                "voice": {
                    "type":        "text",
                    "input_text":  text,
                    "voice_id":    "1bd001e7e50f421d891986aad5158bc8",  # HeyGen default voice
                },
            }
        ],
        "dimension": {"width": 400, "height": 400},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.heygen.com/v2/video/generate",
            json=payload, headers=headers,
        )
        if resp.status_code != 200:
            logger.error("HeyGen create failed %d: %s", resp.status_code, resp.text[:300])
            return None

        video_id = resp.json().get("data", {}).get("video_id")
        if not video_id:
            logger.error("HeyGen missing video_id: %s", resp.text[:200])
            return None

        logger.info("HeyGen video created: %s", video_id)

        # Poll for completion
        for attempt in range(_MAX_POLLS):
            await asyncio.sleep(_POLL_INTERVAL)
            status_resp = await client.get(
                f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
                headers=headers,
            )
            data   = status_resp.json().get("data", {})
            status = data.get("status", "")
            logger.debug("HeyGen poll %d: status=%s", attempt, status)

            if status == "completed":
                video_url = data.get("video_url", "")
                if not video_url:
                    logger.error("HeyGen completed but no video_url")
                    return None
                dl = await client.get(video_url, timeout=120.0)
                avatar_path = tmp_path / "avatar_raw.mp4"
                avatar_path.write_bytes(dl.content)
                logger.info("HeyGen avatar downloaded → %s", avatar_path)
                return str(avatar_path)

            if status in ("failed", "error"):
                logger.error("HeyGen video failed: %s", data)
                return None

    logger.error("HeyGen polling timed out after %d attempts", _MAX_POLLS)
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

async def apply_avatar_overlay(
    job_output_dir: str,
    narration_text: str,
    provider:          str   = "did",       # "did" | "heygen"
    api_key:           str   = "",
    avatar_image_url:  str   = DEFAULT_AVATAR_IMAGE,   # D-ID only
    heygen_avatar_id:  str   = "Angela-inblackskirt-20220820",  # HeyGen only
    position:          str   = "bottomright",
    scale:             float = 0.22,
) -> dict:
    """
    Main entry point called from the FastAPI endpoint.

    Returns:
        {"success": True,  "output_path": "...tutorial_with_avatar.mp4"}
        {"success": False, "error": "reason"}
    """
    out_dir      = Path(job_output_dir)
    main_video   = out_dir / "tutorial.mp4"
    output_video = out_dir / "tutorial_with_avatar.mp4"
    tmp_dir      = out_dir / "_avatar_tmp"
    tmp_dir.mkdir(exist_ok=True)

    if not main_video.exists():
        return {"success": False, "error": "tutorial.mp4 not found — run video generation first"}

    key = api_key or (DID_API_KEY if provider == "did" else HEYGEN_API_KEY)
    if not key:
        return {"success": False, "error": f"No API key provided for {provider}. Set DID_API_KEY or HEYGEN_API_KEY in .env"}

    # Step 1: Generate avatar video via chosen provider
    logger.info("Avatar: generating with provider=%s", provider)
    avatar_path: Optional[str] = None

    if provider == "did":
        avatar_path = await _did_generate_avatar(
            narration_text, avatar_image_url, key, tmp_dir
        )
    elif provider == "heygen":
        avatar_path = await _heygen_generate_avatar(
            narration_text, heygen_avatar_id, key, tmp_dir
        )
    else:
        return {"success": False, "error": f"Unknown provider: {provider}. Use 'did' or 'heygen'"}

    if not avatar_path:
        return {"success": False, "error": f"Avatar generation failed with provider={provider}"}

    # Step 2: Overlay avatar on main video
    logger.info("Avatar: overlaying on tutorial.mp4")
    ok = _overlay_avatar(
        str(main_video), avatar_path, str(output_video),
        position=position, scale=scale,
    )

    if ok:
        # Clean up temp files
        shutil.rmtree(tmp_dir, ignore_errors=True)
        size_mb = output_video.stat().st_size / (1024 * 1024)
        logger.info("Avatar: done → tutorial_with_avatar.mp4  %.1f MB", size_mb)
        return {"success": True, "output_path": str(output_video)}

    return {"success": False, "error": "FFmpeg overlay step failed — check logs"}


def extract_narration_text(video_script: list) -> str:
    """Helper: join all narration fields from the video script into one text blob."""
    parts = []
    for seg in video_script:
        narration = str(seg.get("narration", "")).strip()
        if narration:
            parts.append(narration)
    return " ".join(parts)
