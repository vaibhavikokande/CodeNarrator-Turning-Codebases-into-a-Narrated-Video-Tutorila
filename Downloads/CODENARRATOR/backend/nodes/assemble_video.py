"""
AssembleVideo node — merges animated video clips with audio, then adds:
  • YouTube-style branded intro (6 s)
  • Chapter transition cards (3 s each)
  • Outro with chapter recap + GitHub CTA (10 s)
  • 1280×720 thumbnail.png
  • Optional background music mix (place ambient.mp3 in assets/music/)
"""

import asyncio
import logging
import os
import shutil
import subprocess
import textwrap
import uuid
from pathlib import Path
from typing import Any, List

from pipeline.pocketflow import AsyncNode

logger = logging.getLogger(__name__)

_MAX_DURATION_WARN = 700  # ~11 minutes

# ── FFmpeg helpers ─────────────────────────────────────────────────────────────

def _get_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        e = imageio_ffmpeg.get_ffmpeg_exe()
        if e and os.path.exists(e):
            os.environ["PATH"] = os.path.dirname(e) + os.pathsep + os.environ.get("PATH", "")
            return e
    except Exception:
        pass
    raise RuntimeError("FFmpeg not found. Install from https://ffmpeg.org")


def _run(cmd: List[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{r.stderr[-800:]}")


def _audio_duration(ffmpeg: str, path: str) -> float:
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    if not os.path.exists(ffprobe):
        ffprobe = shutil.which("ffprobe") or ffprobe
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return max(float(r.stdout.strip()), 0.5)
    except Exception:
        pass
    try:
        from mutagen.mp3 import MP3
        return MP3(path).info.length
    except Exception:
        return 4.0


def _video_duration(ffmpeg: str, path: str) -> float:
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    if not os.path.exists(ffprobe):
        ffprobe = shutil.which("ffprobe") or ffprobe
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return max(float(r.stdout.strip()), 0.5)
    except Exception:
        return 6.0


def _has_moov_atom(path: Path) -> bool:
    try:
        return b"moov" in path.read_bytes()
    except OSError:
        return False


# ── AssembleVideo node ────────────────────────────────────────────────────────

class AssembleVideo(AsyncNode):

    async def prep(self, shared: dict) -> dict:
        # Extract tutorial title from the first "title" segment in the script
        script       = shared.get("video_script", [])
        repo_url     = shared.get("repo_url", "")
        tutorial_ttl = shared.get("title", "")
        if not tutorial_ttl:
            for seg in script:
                if seg.get("type") == "title":
                    dc = seg.get("display_content", {})
                    if isinstance(dc, dict):
                        tutorial_ttl = dc.get("title", dc.get("text", ""))
                    break
        if not tutorial_ttl:
            # Fall back to deriving from repo URL
            tutorial_ttl = repo_url.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").title() or "Code Narrator"

        return {
            "visual_paths":    shared["visual_paths"],
            "audio_paths":     shared["audio_paths"],
            "output_dir":      shared["output_dir"],
            "video_script":    script,
            "repo_url":        repo_url,
            "tutorial_title":  tutorial_ttl,
        }

    async def exec(self, prep_result: dict) -> str:
        return await asyncio.to_thread(self._assemble_sync, prep_result)

    # ── Main assembly logic ────────────────────────────────────────────────────

    def _assemble_sync(self, prep_result: dict) -> str:
        ffmpeg         = _get_ffmpeg()
        visual_paths   = prep_result["visual_paths"]
        audio_paths    = prep_result["audio_paths"]
        output_dir     = Path(prep_result["output_dir"])
        video_script   = prep_result["video_script"]
        repo_url       = prep_result["repo_url"]
        tutorial_title = prep_result["tutorial_title"]

        merged_dir = output_dir / "merged"
        merged_dir.mkdir(exist_ok=True)

        # ── Extract chapter info ───────────────────────────────────────────────
        chapters: List[str] = []
        for seg in video_script:
            if seg.get("type") == "chapter_intro":
                dc = seg.get("display_content", {})
                ch_title = (dc.get("chapter_title", "") if isinstance(dc, dict) else "")
                chapters.append(ch_title or f"Chapter {len(chapters)+1}")
        total_chapters = len(chapters)

        # ── Thumbnail ─────────────────────────────────────────────────────────
        self._generate_thumbnail(output_dir, tutorial_title, repo_url, chapters)

        # ── Build ordered clip list with intro / transitions / outro ───────────
        # Each entry: (visual_path, audio_path, label)
        clips_to_merge: List[tuple] = []

        # 1. Branded intro
        intro_vis = merged_dir / "extra_intro_vis.mp4"
        intro_aud = merged_dir / "extra_intro_aud.mp3"
        intro_data = {
            "title":         tutorial_title,
            "repo_url":      repo_url,
            "chapter_count": total_chapters,
        }
        print("AssembleVideo: generating branded intro (6 s)")
        self._render_extra_clip("BrandedIntroRenderer", intro_data, str(intro_vis))
        self._generate_silent_audio(4.0, str(intro_aud), ffmpeg)
        clips_to_merge.append((str(intro_vis), str(intro_aud), "intro"))

        # 2. Original clips, with chapter transitions injected before each chapter_intro
        chapter_idx = 0
        total_orig  = min(len(visual_paths), len(audio_paths))
        for i, (vpath, apath) in enumerate(zip(visual_paths, audio_paths)):
            seg      = video_script[i] if i < len(video_script) else {}
            seg_type = seg.get("type", "slide")

            if seg_type == "chapter_intro":
                dc      = seg.get("display_content", {})
                ch_ttl  = (dc.get("chapter_title", "") if isinstance(dc, dict) else "")
                chapter_idx += 1
                ch_ttl  = ch_ttl or f"Chapter {chapter_idx}"

                trans_vis = merged_dir / f"extra_trans_{chapter_idx:03d}_vis.mp4"
                trans_aud = merged_dir / f"extra_trans_{chapter_idx:03d}_aud.mp3"
                trans_data = {
                    "chapter_number":  chapter_idx,
                    "chapter_title":   ch_ttl,
                    "total_chapters":  total_chapters,
                }
                print(f"AssembleVideo: generating transition for chapter {chapter_idx}/{total_chapters}")
                self._render_extra_clip("ChapterTransitionRenderer", trans_data, str(trans_vis))
                self._generate_silent_audio(2.0, str(trans_aud), ffmpeg)
                clips_to_merge.append((str(trans_vis), str(trans_aud), f"trans_{chapter_idx}"))

            clips_to_merge.append((vpath, apath, f"seg_{i:03d}"))

        # 3. Outro
        outro_vis  = merged_dir / "extra_outro_vis.mp4"
        outro_aud  = merged_dir / "extra_outro_aud.mp3"
        outro_data = {"title": tutorial_title, "chapters": chapters, "repo_url": repo_url}
        print("AssembleVideo: generating outro (10 s)")
        self._render_extra_clip("OutroRenderer", outro_data, str(outro_vis))
        self._generate_silent_audio(6.0, str(outro_aud), ffmpeg)
        clips_to_merge.append((str(outro_vis), str(outro_aud), "outro"))

        # ── Merge each (visual, audio) pair ───────────────────────────────────
        merged_clips: List[Path] = []
        total_duration = 0.0
        total = len(clips_to_merge)

        print(f"AssembleVideo: merging {total} clips (incl. intro/transitions/outro)")

        for idx, (vpath, apath, label) in enumerate(clips_to_merge):
            if not Path(vpath).exists():
                logger.warning("Missing visual [%s]", label)
                continue
            if not Path(apath).exists():
                logger.warning("Missing audio [%s]", label)
                continue

            v_dur    = _video_duration(ffmpeg, vpath)
            a_dur    = _audio_duration(ffmpeg, apath)
            clip_dur = max(v_dur, a_dur) + 0.1
            total_duration += clip_dur

            merged_path = merged_dir / f"clip_{idx:03d}_{label}.mp4"
            cmd = [
                ffmpeg, "-y",
                "-i", vpath,
                "-i", apath,
                # FIX 1: resample audio to 44100 Hz stereo so all clips are uniform
                # and players (Windows Media Player, browsers) can decode correctly.
                # ElevenLabs outputs 24000 Hz mono — without this fix audio is silent.
                "-filter_complex",
                (
                    f"[0:v]tpad=stop_mode=clone:stop_duration={clip_dur}[vpad];"
                    f"[1:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=2.0[aout]"
                ),
                "-map", "[vpad]",
                "-map", "[aout]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-ar", "44100", "-ac", "2",
                "-t", str(clip_dur),
                "-pix_fmt", "yuv420p",
                str(merged_path),
            ]
            try:
                _run(cmd)
                merged_clips.append(merged_path)
                if idx % 5 == 0 or idx == total - 1:
                    print(f"  merged {idx+1}/{total}  [{label}]  ({clip_dur:.1f}s)")
            except Exception as exc:
                logger.warning("Clip merge failed [%s]: %s", label, exc)

        if not merged_clips:
            raise RuntimeError("No clips could be merged — check visual and audio files.")

        if total_duration > _MAX_DURATION_WARN:
            logger.warning("Total video ~%.0f s — long encode", total_duration)

        # ── Concatenate all merged clips ───────────────────────────────────────
        concat_file = merged_dir / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{c.resolve()}'" for c in merged_clips),
            encoding="utf-8",
        )

        tmp_name   = f"tutorial.{uuid.uuid4().hex[:8]}.tmp.mp4"
        tmp_path   = output_dir / tmp_name
        final_path = output_dir / "tutorial.mp4"

        print(f"AssembleVideo: concatenating {len(merged_clips)} clips "
              f"(~{total_duration:.0f}s / {total_duration/60:.1f} min)")

        # FIX 2: Re-encode concat output with faststart so moov atom is placed
        # at the START of the file. Without this the player must read the entire
        # file before it can seek, causing "stops at 0:05 / 0.05s" symptoms.
        # Also re-encode audio to ensure uniform 44100 Hz stereo across all clips.
        _run([
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",   # moov atom at front → instant playback
            str(tmp_path),
        ])

        if not _has_moov_atom(tmp_path):
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError("Output MP4 is corrupt (no moov atom).")

        os.replace(str(tmp_path), str(final_path))

        # ── Optional: mix background music ────────────────────────────────────
        bgm_path = Path(__file__).parent.parent / "assets" / "music" / "ambient.mp3"
        if bgm_path.exists():
            print("AssembleVideo: mixing background music")
            self._mix_bgm(ffmpeg, str(final_path), str(bgm_path))

        size_mb = final_path.stat().st_size / (1024 * 1024)
        print(f"AssembleVideo: DONE — tutorial.mp4  {size_mb:.1f} MB  "
              f"{total_duration:.0f}s ({total_duration/60:.1f} min)")
        return str(final_path)

    # ── Helper: render new renderer clip to file ───────────────────────────────

    def _render_extra_clip(self, renderer_name: str, data: dict, out_path: str) -> None:
        """Import and run a renderer from generate_visuals, write silent MP4."""
        try:
            from nodes.generate_visuals import render_clip_sync
            from nodes import generate_visuals as gv
            renderer_cls = getattr(gv, renderer_name)
            render_clip_sync(renderer_cls, data, out_path)
        except Exception as exc:
            logger.warning("Extra clip %s failed: %s — using black frame", renderer_name, exc)
            self._write_black_clip(out_path, dur=6.0)

    def _write_black_clip(self, path: str, dur: float = 6.0) -> None:
        import numpy as np
        from moviepy import VideoClip  # type: ignore
        W_, H_ = 1920, 1080
        black = VideoClip(lambda t: np.zeros((H_, W_, 3), dtype=np.uint8), duration=dur)
        black.write_videofile(path, fps=24, codec="libx264",
                              preset="ultrafast", audio=False, logger=None)

    # ── Helper: silent AAC audio ───────────────────────────────────────────────

    def _generate_silent_audio(self, duration: float, out_path: str, ffmpeg: str) -> None:
        # FIX 3: generate silent audio as 44100 Hz stereo MP3 — same sample rate
        # and channel count as the narration clips so the merge step is uniform.
        # The .aac extension was changed to .mp3 in the caller paths too.
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:a", "libmp3lame", "-b:a", "128k",
            "-ar", "44100", "-ac", "2",
            out_path,
        ]
        try:
            _run(cmd)
        except Exception as exc:
            logger.warning("Silent audio generation failed: %s", exc)

    # ── Helper: background music mix ──────────────────────────────────────────

    def _mix_bgm(self, ffmpeg: str, video_path: str, bgm_path: str) -> None:
        """Overlay ambient music at ~8 % volume under the narration."""
        tmp = video_path.replace(".mp4", ".bgm_tmp.mp4")
        cmd = [
            ffmpeg, "-y",
            "-i", video_path,
            "-i", bgm_path,
            "-filter_complex",
            (
                "[1:a]volume=0.08,"
                "aloop=loop=-1:size=2000000000[music];"
                "[0:a][music]amix=inputs=2:duration=first:dropout_transition=3[aout]"
            ),
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            tmp,
        ]
        try:
            _run(cmd)
            os.replace(tmp, video_path)
            print("AssembleVideo: background music mixed in ✓")
        except Exception as exc:
            logger.warning("BGM mix failed: %s", exc)
            if os.path.exists(tmp):
                os.remove(tmp)

    # ── Helper: YouTube thumbnail (1280 × 720) ─────────────────────────────────

    def _generate_thumbnail(self, output_dir: Path, title: str,
                            repo_url: str, chapters: List[str]) -> None:
        try:
            from PIL import Image, ImageDraw, ImageFont
            TW, TH = 1280, 720

            # Gradient background
            img  = Image.new("RGB", (TW, TH))
            draw = ImageDraw.Draw(img)
            for y in range(TH):
                tt = y / TH
                draw.line([(0, y), (TW, y)],
                          fill=(int(5 + 20*tt), int(5 + 12*tt), int(15 + 35*tt)))

            # Spotlight
            from nodes.generate_visuals import spotlight as _spotlight
            img = _spotlight(img, TW // 2, TH // 3, 450, color=(50, 80, 200), intensity=30)

            # Accent bars
            draw = ImageDraw.Draw(img)
            draw.rectangle([(0, 0),       (TW, 7)],    fill=(31, 111, 235))
            draw.rectangle([(0, TH - 7),  (TW, TH)],   fill=(31, 111, 235))

            # Fonts
            fonts_dir = Path(__file__).parent.parent / "assets" / "fonts"
            def _fnt(size, bold=False, mono=False):
                names = (
                    ["Roboto-Bold.ttf"]         if bold else
                    ["RobotoMono-Regular.ttf"]   if mono else
                    ["Roboto-Regular.ttf"]
                )
                for n in names:
                    try:
                        return ImageFont.truetype(str(fonts_dir / n), size)
                    except Exception:
                        pass
                return ImageFont.load_default()

            tf = _fnt(88, bold=True)
            sf = _fnt(38)
            mf = _fnt(28, mono=True)

            # Title (up to 2 lines)
            lines = textwrap.wrap(title[:55], 18)[:2]
            y = 110
            for line in lines:
                draw.text((80, y), line, font=tf, fill=(230, 237, 243))
                y += 108

            # Repo URL
            if repo_url:
                draw.text((80, y + 20), repo_url[:60], font=mf, fill=(88, 148, 200))

            # Chapter count badge
            if chapters:
                badge_txt = f"  {len(chapters)} Chapters  "
                draw.rounded_rectangle([(80, TH - 130), (80 + 280, TH - 72)],
                                       radius=12, fill=(31, 111, 235))
                draw.text((100, TH - 124), badge_txt, font=sf, fill=(230, 237, 243))

            # "AI Generated" badge
            draw.rounded_rectangle([(TW - 310, TH - 130), (TW - 30, TH - 72)],
                                   radius=12, fill=(22, 27, 34))
            draw.text((TW - 298, TH - 124), "⚡ AI Generated", font=sf, fill=(88, 166, 255))

            # Code Narrator logo bottom-right corner
            draw.text((TW - 260, TH - 50), "Code Narrator", font=_fnt(26), fill=(88, 148, 158))

            # Right side: decorative code lines
            cf = _fnt(22, mono=True)
            fake_code = [
                "def main():",
                "    # AI Tutorial",
                "    chapters = []",
                "    for seg in script:",
                "        render(seg)",
                "    assemble(chapters)",
            ]
            cx = TW - 380
            cy = 120
            draw.rounded_rectangle([(cx - 20, cy - 16), (TW - 40, cy + len(fake_code)*34 + 10)],
                                   radius=12, fill=(22, 27, 34))
            for j, cl in enumerate(fake_code):
                draw.text((cx, cy + j * 34), cl, font=cf, fill=(88, 166, 255))

            thumb_path = output_dir / "thumbnail.png"
            img.save(str(thumb_path))
            print(f"AssembleVideo: thumbnail saved → thumbnail.png  ({TW}x{TH})")

        except Exception as exc:
            logger.warning("Thumbnail generation failed: %s", exc)

    # ── Post ─────────────────────────────────────────────────────────────────

    async def post(self, shared: dict, prep_result: Any, exec_result: str) -> str:
        shared["video_path"] = exec_result
        return "default"
