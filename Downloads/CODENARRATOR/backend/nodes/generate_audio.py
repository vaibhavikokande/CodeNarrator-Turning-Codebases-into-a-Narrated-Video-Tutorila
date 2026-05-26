"""
GenerateAudio node — ElevenLabs TTS (primary) + edge-tts (fallback).

TTS_PROVIDER env: elevenlabs (default) | edge_tts
ELEVENLABS_API_KEY required for ElevenLabs.
ELEVENLABS_VOICE_ID overrides default voice (Sarah).

eleven_multilingual_v2 supports 29 languages — used for ALL languages.
edge-tts is the fallback when ElevenLabs fails or is unavailable.
Audio clips are generated concurrently (max 5 at a time).
"""

import asyncio
import logging
import os
import re
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any, List

from pipeline.pocketflow import AsyncNode

logger = logging.getLogger(__name__)

_DEFAULT_VOICE      = "en-US-AriaNeural"
_RATE               = "-5%"
_TTS_PROVIDER       = os.environ.get("TTS_PROVIDER", "elevenlabs").lower()
_ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
_ELEVENLABS_VOICE   = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

# Map tutorial language -> best edge-tts neural voice for that language
_LANG_VOICE_MAP = {
    "english":    "en-US-AriaNeural",
    "spanish":    "es-ES-ElviraNeural",
    "french":     "fr-FR-DeniseNeural",
    "german":     "de-DE-KatjaNeural",
    "japanese":   "ja-JP-NanamiNeural",
    "chinese":    "zh-CN-XiaoxiaoNeural",
    "portuguese": "pt-BR-FranciscaNeural",
    "hindi":      "hi-IN-SwaraNeural",
    "arabic":     "ar-SA-ZariyahNeural",
    "korean":     "ko-KR-SunHiNeural",
}


def _sanitize(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[{}]', '', text)
    # Keep all unicode — only strip control chars
    text = re.sub(r'[\x00-\x1F\x7F]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 900:
        text = text[:900].rsplit(' ', 1)[0].rstrip(',;') + '.'
    return text or "Let's continue to the next section."


def _get_ffmpeg() -> str:
    import shutil
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _silence_wav(path: Path, secs: float = 4.0) -> None:
    rate = 22050
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * int(rate * secs))


def _add_padding(ffmpeg: str, src: Path, dst: Path) -> bool:
    try:
        r = subprocess.run(
            [ffmpeg, "-y", "-i", str(src), "-af",
             "adelay=300:all=1,apad=pad_dur=0.5", str(dst)],
            capture_output=True, timeout=30,
        )
        return r.returncode == 0 and dst.exists() and dst.stat().st_size > 200
    except Exception as exc:
        logger.warning("Padding error: %s", exc)
        return False


def _elevenlabs_tts(text: str, out_path: Path, voice_id: str) -> bool:
    if not _ELEVENLABS_API_KEY:
        logger.warning("ELEVENLABS_API_KEY not set — skipping ElevenLabs")
        return False
    try:
        import httpx
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.80,
                "style": 0.05,
                "use_speaker_boost": True,
            },
        }
        headers = {
            "xi-api-key": _ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                out_path.write_bytes(response.content)
                return out_path.stat().st_size > 200
            logger.warning("ElevenLabs API error %d: %s",
                           response.status_code, response.text[:200])
            return False
    except ImportError:
        logger.warning("httpx not installed — cannot use ElevenLabs")
        return False
    except Exception as exc:
        logger.warning("ElevenLabs error: %s", exc)
        return False


def _edge_tts_cli(text: str, out_path: Path, voice: str) -> bool:
    cmd = [
        sys.executable, "-m", "edge_tts",
        "--voice", voice, "--rate", _RATE,
        "--text", text, "--write-media", str(out_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=40)
        if r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 200:
            return True
        logger.warning("edge-tts failed (rc=%d): %s", r.returncode, r.stderr[:200])
        return False
    except subprocess.TimeoutExpired:
        logger.warning("edge-tts timed out for: %r", text[:60])
        return False
    except Exception as exc:
        logger.warning("edge-tts error: %s", exc)
        return False


class GenerateAudio(AsyncNode):

    async def prep(self, shared: dict) -> dict:
        language  = shared.get("language", "English").lower()
        req_voice = shared.get("voice", _DEFAULT_VOICE) or _DEFAULT_VOICE

        native_voice  = _LANG_VOICE_MAP.get(language, _DEFAULT_VOICE)
        english_voices = {
            "en-US-AriaNeural", "en-US-GuyNeural",
            "en-GB-SoniaNeural", "en-AU-NatashaNeural",
        }
        # If an English voice was sent but the language is non-English, override
        if language != "english" and req_voice in english_voices:
            req_voice = native_voice

        return {
            "video_script": shared["video_script"],
            "voice":        req_voice,
            "language":     language,
            "output_dir":   shared["output_dir"],
        }

    async def exec(self, prep_result: dict) -> List[str]:
        segments = prep_result["video_script"]
        voice    = prep_result.get("voice") or _DEFAULT_VOICE
        out_dir  = Path(prep_result["output_dir"]) / "audio"
        out_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg   = _get_ffmpeg()

        # ElevenLabs eleven_multilingual_v2 supports 29 languages natively.
        # Use it for ALL languages. Fall back to edge-tts only if it fails.
        use_eleven = _TTS_PROVIDER == "elevenlabs" and bool(_ELEVENLABS_API_KEY)
        provider   = "ElevenLabs(multilingual)" if use_eleven else f"edge-tts({voice})"
        total      = len(segments)

        print(f"GenerateAudio: {total} clips  provider={provider}  rate={_RATE}")

        # Concurrency: max 5 TTS calls at once to respect API rate limits
        sem = asyncio.Semaphore(5)

        async def _process_clip(i: int, seg: dict) -> str:
            async with sem:
                raw_narration = str(seg.get("narration", "")).strip()
                narration     = _sanitize(raw_narration)
                if len(narration) < 10 and len(raw_narration) > 5:
                    narration = raw_narration[:900].strip()
                if len(narration) < 5:
                    narration = "Moving to the next section."

                raw_path = out_dir / f"segment_{i:03d}_raw.mp3"
                fin_path = out_dir / f"segment_{i:03d}.mp3"
                sil_path = out_dir / f"segment_{i:03d}.wav"

                if i % 5 == 0 or i == total - 1:
                    print(f"GenerateAudio: clip {i+1}/{total} [{provider}] "
                          f"({len(narration)} chars)")

                tts_ok = False
                if use_eleven:
                    # FIX 2: use the language-appropriate ElevenLabs voice when
                    # the request language is non-English.  eleven_multilingual_v2
                    # supports all languages; the env-var ELEVENLABS_VOICE_ID is
                    # the English default — override it for non-English jobs.
                    # Non-English languages use a multilingual preset voice (Adam)
                    # which has strong multilingual support across 29 languages.
                    _ELEVEN_MULTILINGUAL_VOICE = "pNInz6obpgDQGcFmaJgB"   # Adam — multilingual
                    eleven_voice = (
                        _ELEVENLABS_VOICE          # keep user's chosen voice for English
                        if prep_result.get("language", "english") == "english"
                        else _ELEVEN_MULTILINGUAL_VOICE
                    )
                    tts_ok = await asyncio.to_thread(
                        _elevenlabs_tts, narration, raw_path, eleven_voice)
                    if not tts_ok:
                        logger.warning(
                            "ElevenLabs failed segment %d — fallback to edge-tts", i)

                if not tts_ok:
                    tts_ok = await asyncio.to_thread(
                        _edge_tts_cli, narration, raw_path, voice)

                if tts_ok:
                    pad_ok = await asyncio.to_thread(
                        _add_padding, ffmpeg, raw_path, fin_path)
                    return str(fin_path if pad_ok else raw_path)

                # Both TTS providers failed — write silence
                try:
                    _silence_wav(sil_path, 5.0)
                    return str(sil_path)
                except Exception as exc:
                    logger.warning("Silence fallback failed segment %d: %s", i, exc)
                    return str(raw_path) if raw_path.exists() else str(sil_path)

        results = await asyncio.gather(
            *[_process_clip(i, seg) for i, seg in enumerate(segments)]
        )
        paths = list(results)

        voiced  = sum(1 for p in paths if str(p).endswith(".mp3"))
        silence = sum(1 for p in paths if str(p).endswith(".wav"))
        print(f"GenerateAudio: {voiced} voiced, {silence} silent fallbacks")
        return paths

    async def post(self, shared: dict, prep_result: Any, exec_result: List[str]) -> str:
        shared["audio_paths"] = exec_result
        return "default"
