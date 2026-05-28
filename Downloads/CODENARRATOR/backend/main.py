"""
Code Narrator — FastAPI backend v2.0
Manages job lifecycle, background pipeline execution, and artifact serving.

Added in v2:
- /api/chat        — Claude-powered chatbot for tutorial Q&A
- /api/admin/*     — Admin monitoring (cache stats, clear cache, job listing)
- /api/jobs/{id}/search     — Full-text search inside tutorial chapters
- /api/jobs/{id}/export/pdf — Export tutorial as PDF
- WebSocket /ws/jobs/{id}   — Live progress streaming (replaces polling)
"""

import asyncio
import logging
import os
import re
import uuid
import time
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from assets.fonts.download_fonts import ensure_fonts
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

load_dotenv()
ensure_fonts()

import json as _json

def _load_video_script(job_id: str) -> list:
    """
    Return video_script for a job.
    Checks in-memory JOBS first, then falls back to video_script.json on disk.
    Raises HTTPException(400) if neither is available.
    """
    # 1. In-memory (job running or recently completed in same server session)
    script = JOBS.get(job_id, {}).get("video_script", [])
    if script:
        return script

    # 2. Disk fallback (server was restarted after video was generated)
    script_path = _OUTPUT_BASE / job_id / "video_script.json"
    if script_path.exists():
        try:
            script = _json.loads(script_path.read_text(encoding="utf-8"))
            if script:
                return script
        except Exception:
            pass

    raise HTTPException(
        status_code=400,
        detail=(
            "video_script not found. "
            "This job was generated before a server restart. "
            "Please re-generate the video tutorial to use this feature."
        ),
    )


def repo_name_slug(job_id: str, output_dir: Path) -> str:
    """Derive a filename-safe slug from the repo name for PPTX download."""
    import re as _re
    try:
        idx = output_dir / "index.md"
        if idx.exists():
            m = _re.search(r"^#\s+(.+)", idx.read_text(encoding="utf-8"), _re.MULTILINE)
            if m:
                slug = _re.sub(r"[^\w\s-]", "", m.group(1)).strip()
                slug = _re.sub(r"[\s_]+", "_", slug)[:30].lower()
                if slug:
                    return slug
    except Exception:
        pass
    return job_id[:8]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Job store ─────────────────────────────────────────────────────────────────
JOBS: Dict[str, dict] = {}

_OUTPUT_BASE = Path(os.environ.get("OUTPUT_DIR", "./output"))
_OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Code Narrator", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response models ─────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    repo_url: str
    run_video: bool = False
    language: str = "English"
    theme: str = "dark"
    voice: str = "en-US-AriaNeural"
    github_token: Optional[str] = None   # for private repos (OAuth)

class GenerateResponse(BaseModel):
    job_id: str

class JobStatus(BaseModel):
    status: str
    progress: int

class LogEntry(BaseModel):
    timestamp: float
    message: str

class LogsResponse(BaseModel):
    logs: List[LogEntry]
    total: int

class ChaptersResponse(BaseModel):
    completed_chapters: List[str]
    total_chapters: int

class ArtifactsResponse(BaseModel):
    markdown_files: List[str]
    video_url: Optional[str]

class ChatRequest(BaseModel):
    job_id: str
    message: str
    context_file: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str

class SearchResponse(BaseModel):
    results: List[dict]

class AdminStatsResponse(BaseModel):
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    active_jobs: int
    llm_cache: dict
    output_dir_size_mb: float

# ── Generate ──────────────────────────────────────────────────────────────────
@app.post("/api/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    from utils.job_log_writer import JobLogWriter
    log_writer = JobLogWriter()
    JOBS[job_id] = {
        "status": "queued",
        "progress": 0,
        "log_writer": log_writer,
        "repo_url": req.repo_url,
        "run_video": req.run_video,
        "language": req.language,
        "theme": req.theme,
        "voice": req.voice,
        "github_token": req.github_token,
        "created_at": time.time(),
    }
    background_tasks.add_task(_run_job, job_id, req)
    logger.info("Job %s queued for %s", job_id, req.repo_url)
    return GenerateResponse(job_id=job_id)

@app.get("/api/jobs/{job_id}/status", response_model=JobStatus)
async def job_status(job_id: str):
    if job_id in JOBS:
        job = JOBS[job_id]
        log_writer = job["log_writer"]
        progress = log_writer.infer_progress() if job["status"] == "processing" else (
            100 if job["status"] == "completed" else job["progress"]
        )
        return JobStatus(status=job["status"], progress=progress)
    output_dir = _OUTPUT_BASE / job_id
    if output_dir.exists() and any(output_dir.glob("*.md")):
        return JobStatus(status="completed", progress=100)
    raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

@app.get("/api/jobs/{job_id}/logs", response_model=LogsResponse)
async def job_logs(job_id: str, since: int = 0):
    job = _get_job(job_id)
    log_writer = job["log_writer"]
    entries = log_writer.since(since)
    return LogsResponse(
        logs=[LogEntry(timestamp=e["timestamp"], message=e["message"]) for e in entries],
        total=len(log_writer.lines),
    )

@app.get("/api/jobs/{job_id}/chapters", response_model=ChaptersResponse)
async def job_chapters(job_id: str):
    job = _get_job(job_id)
    log_writer = job["log_writer"]
    return ChaptersResponse(
        completed_chapters=log_writer.chapters_ready,
        total_chapters=log_writer.chapter_total,
    )

@app.get("/api/jobs/{job_id}/artifacts", response_model=ArtifactsResponse)
async def job_artifacts(job_id: str):
    output_dir = _OUTPUT_BASE / job_id
    if not output_dir.exists():
        if job_id not in JOBS:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        return ArtifactsResponse(markdown_files=[], video_url=None)
    md_files = sorted(p.name for p in output_dir.glob("*.md"))
    video_url = f"/api/jobs/{job_id}/file/tutorial.mp4" if (output_dir / "tutorial.mp4").exists() else None
    return ArtifactsResponse(markdown_files=md_files, video_url=video_url)

@app.get("/api/jobs/{job_id}/file/{filename}")
async def job_file(job_id: str, filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = _OUTPUT_BASE / job_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))

# ── Search ────────────────────────────────────────────────────────────────────
@app.get("/api/jobs/{job_id}/search", response_model=SearchResponse)
async def search_tutorial(job_id: str, q: str = ""):
    if not q.strip():
        return SearchResponse(results=[])
    output_dir = _OUTPUT_BASE / job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    results = []
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    for md_file in sorted(output_dir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            for line_num, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    snippet = line.strip()
                    if len(snippet) > 200:
                        m = pattern.search(snippet)
                        start = max(0, m.start() - 80)
                        snippet = ("..." if start > 0 else "") + snippet[start:start+200] + "..."
                    results.append({"file": md_file.name, "line": line_num, "snippet": snippet})
                    if len(results) >= 50:
                        break
        except Exception:
            continue
        if len(results) >= 50:
            break
    return SearchResponse(results=results)

# ── PDF Export ────────────────────────────────────────────────────────────────
@app.get("/api/jobs/{job_id}/export/pdf")
async def export_pdf(job_id: str):
    output_dir = _OUTPUT_BASE / job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    md_files = sorted(output_dir.glob("*.md"), key=lambda p: p.name)
    if not md_files:
        raise HTTPException(status_code=404, detail="No tutorial files found")
    combined = []
    for f in md_files:
        try:
            combined.append(f.read_text(encoding="utf-8"))
        except Exception:
            continue
    full_md = "\n\n---\n\n".join(combined)
    try:
        import markdown as md_lib
        from weasyprint import HTML as WeasyHTML
        html_content = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:40px auto;max-width:800px;line-height:1.6;color:#1a1a2e}}
code{{background:#f4f4f8;padding:2px 6px;border-radius:4px;font-size:.9em}}
pre{{background:#1a1a2e;color:#e8e8f0;padding:16px;border-radius:8px;overflow-x:auto}}
pre code{{background:none;color:inherit;padding:0}}
h1{{color:#4f46e5;border-bottom:2px solid #e5e7eb;padding-bottom:8px}}
h2{{color:#1e1b4b}}
hr{{border:none;border-top:1px solid #e5e7eb;margin:32px 0}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #e5e7eb;padding:8px 12px;text-align:left}}
th{{background:#f4f4f8}}
</style></head><body>
{md_lib.markdown(full_md, extensions=['fenced_code', 'tables', 'toc'])}
</body></html>"""
        pdf_bytes = WeasyHTML(string=html_content).write_pdf()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="tutorial_{job_id[:8]}.pdf"'},
        )
    except ImportError:
        return Response(
            content=full_md.encode("utf-8"),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="tutorial_{job_id[:8]}.md"'},
        )

# ── Chat ──────────────────────────────────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    output_dir = _OUTPUT_BASE / req.job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{req.job_id}' not found")
    context_parts = []
    if req.context_file:
        target = output_dir / req.context_file
        if target.exists() and target.suffix == ".md":
            context_parts.append(f"Current chapter:\n{target.read_text(encoding='utf-8')[:3000]}")
    else:
        for fname in ["index.md"] + sorted(f.name for f in output_dir.glob("0*.md"))[:2]:
            fp = output_dir / fname
            if fp.exists():
                context_parts.append(fp.read_text(encoding="utf-8")[:1500])
    context = "\n\n".join(context_parts)[:5000]
    prompt = f"""You are a helpful coding tutor assistant embedded in the CodeNarrator platform.
You help developers understand the tutorial content about the repository they're learning.

Tutorial context:
{context}

User question: {req.message}

Answer helpfully and concisely. Reference specific code or concepts when relevant."""
    try:
        from llm.router import llm_call
        reply = await llm_call(prompt, bypass_cache=True)
        return ChatResponse(reply=reply)
    except Exception as exc:
        logger.error("Chat error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}")

# ── Admin ─────────────────────────────────────────────────────────────────────
@app.get("/api/admin/stats", response_model=AdminStatsResponse)
async def admin_stats():
    from llm.router import get_router
    router = get_router()
    total = len(JOBS)
    completed = sum(1 for j in JOBS.values() if j["status"] == "completed")
    failed = sum(1 for j in JOBS.values() if j["status"] == "failed")
    active = sum(1 for j in JOBS.values() if j["status"] == "processing")
    disk_jobs = [d for d in _OUTPUT_BASE.iterdir() if d.is_dir()] if _OUTPUT_BASE.exists() else []
    size_bytes = sum(f.stat().st_size for f in _OUTPUT_BASE.rglob("*") if f.is_file()) if _OUTPUT_BASE.exists() else 0
    return AdminStatsResponse(
        total_jobs=max(total, len(disk_jobs)),
        completed_jobs=completed,
        failed_jobs=failed,
        active_jobs=active,
        llm_cache=router.cache_stats(),
        output_dir_size_mb=round(size_bytes / (1024*1024), 2),
    )

@app.get("/api/admin/jobs")
async def admin_list_jobs():
    jobs_out = []
    for job_id, job in JOBS.items():
        log_writer = job.get("log_writer")
        progress = log_writer.infer_progress() if job["status"] == "processing" and log_writer else (
            100 if job["status"] == "completed" else job.get("progress", 0)
        )
        jobs_out.append({
            "job_id": job_id, "status": job["status"], "progress": progress,
            "repo_url": job.get("repo_url", ""), "created_at": job.get("created_at", 0),
            "run_video": job.get("run_video", False), "language": job.get("language", "English"),
        })
    jobs_out.sort(key=lambda j: j["created_at"], reverse=True)
    return {"jobs": jobs_out}

@app.get("/api/admin/disk-jobs")
async def admin_disk_jobs():
    import re as _re
    _UUID_RE = _re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', _re.IGNORECASE)
    jobs_out = []
    if _OUTPUT_BASE.exists():
        for d in sorted(_OUTPUT_BASE.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not d.is_dir():
                continue
            # Only include real job directories (UUID-named) — skip any accidental file-named dirs
            if not _UUID_RE.match(d.name):
                continue
            md_files = list(d.glob("*.md"))
            has_video = (d / "tutorial.mp4").exists()
            size_mb = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / (1024*1024)
            jobs_out.append({
                "job_id": d.name, "md_count": len(md_files), "has_video": has_video,
                "size_mb": round(size_mb, 2), "mtime": d.stat().st_mtime,
                "in_memory": d.name in JOBS,
                "status": JOBS.get(d.name, {}).get("status", "completed"),
            })
    return {"jobs": jobs_out}

@app.post("/api/admin/cache/clear")
async def admin_clear_cache():
    from llm.router import get_router
    count = get_router().clear_cache()
    return {"cleared": count, "message": f"Cleared {count} cached LLM responses"}

@app.get("/api/admin/provider")
async def admin_provider():
    from llm.router import get_router
    router = get_router()
    return {
        "active_provider": router.get_active_provider(),
        "llm_provider_env": os.environ.get("LLM_PROVIDER", "claude"),
        "tts_provider_env": os.environ.get("TTS_PROVIDER", "elevenlabs"),
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "has_gemini_key": bool(os.environ.get("GEMINI_API_KEY")),
        "has_elevenlabs_key": bool(os.environ.get("ELEVENLABS_API_KEY")),
        "has_github_token": bool(os.environ.get("GITHUB_TOKEN")),
    }

# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/jobs/{job_id}")
async def ws_job_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    cursor = 0
    try:
        while True:
            if job_id not in JOBS:
                output_dir = _OUTPUT_BASE / job_id
                if output_dir.exists() and any(output_dir.glob("*.md")):
                    await websocket.send_json({"type":"status","status":"completed","progress":100})
                else:
                    await websocket.send_json({"type":"error","message":"Job not found"})
                break
            job = JOBS[job_id]
            log_writer = job["log_writer"]
            status = job["status"]
            progress = log_writer.infer_progress() if status=="processing" else (100 if status=="completed" else job.get("progress",0))
            new_entries = log_writer.since(cursor)
            if new_entries:
                cursor += len(new_entries)
                await websocket.send_json({"type":"logs","logs":[{"timestamp":e["timestamp"],"message":e["message"]} for e in new_entries],"total":len(log_writer.lines)})
            await websocket.send_json({"type":"status","status":status,"progress":progress,"chapters_done":len(log_writer.chapters_ready),"chapters_total":log_writer.chapter_total})
            if status in ("completed","failed"):
                break
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        logger.debug("WS disconnected for job %s", job_id)
    except Exception as exc:
        logger.warning("WS error for %s: %s", job_id, exc)
        try:
            await websocket.send_json({"type":"error","message":str(exc)})
        except Exception:
            pass

# ── Background job runner ─────────────────────────────────────────────────────
async def _run_job(job_id: str, req: GenerateRequest) -> None:
    job = JOBS[job_id]
    log_writer = job["log_writer"]
    from pipeline.shared_state import make_shared_state
    from pipeline.text_pipeline import run_text_pipeline
    from pipeline.video_pipeline import run_video_pipeline
    shared = make_shared_state(
        job_id=job_id, repo_url=req.repo_url, run_video=req.run_video,
        language=req.language, theme=req.theme, voice=req.voice,
        github_token=req.github_token,
    )
    job["status"] = "processing"
    try:
        with log_writer.capture():
            await run_text_pipeline(shared)
            if req.run_video:
                await run_video_pipeline(shared)
        job["status"] = "completed"
        log_writer.write("Job completed\n")
        logger.info("Job %s completed", job_id)
    except PermissionError as exc:
        _fail_job(job_id, f"Repository access denied: {exc}")
    except FileNotFoundError as exc:
        _fail_job(job_id, f"Not found: {exc}")
    except OSError as exc:
        _fail_job(job_id, f"Disk or I/O error: {exc}")
    except Exception as exc:
        _fail_job(job_id, str(exc))
        logger.exception("Job %s failed", job_id)

def _fail_job(job_id: str, message: str) -> None:
    job = JOBS.get(job_id)
    if job:
        job["status"] = "failed"
        job["log_writer"].write(f"ERROR: {message}\n")
    logger.error("Job %s failed: %s", job_id, message)

def _get_job(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return JOBS[job_id]

# ═══════════════════════════════════════════════════════════════════════════════
#  AVATAR FEATURE — additive only, does not touch existing endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class AvatarRequest(BaseModel):
    provider:         str   = "did"           # "did" | "heygen"
    api_key:          str   = ""
    avatar_image_url: str   = ""              # D-ID: URL to avatar image
    heygen_avatar_id: str   = "Angela-inblackskirt-20220820"
    position:         str   = "bottomright"   # topleft|topright|bottomleft|bottomright
    scale:            float = 0.22

@app.post("/api/jobs/{job_id}/avatar")
async def add_avatar(job_id: str, req: AvatarRequest):
    output_dir = _OUTPUT_BASE / job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if not (output_dir / "tutorial.mp4").exists():
        raise HTTPException(status_code=400, detail="tutorial.mp4 not found — generate the video first")

    from nodes.generate_avatar import apply_avatar_overlay, extract_narration_text
    # Load video_script from memory or disk, then extract narration text
    try:
        script = _load_video_script(job_id)
        narration = extract_narration_text(script)
    except HTTPException:
        narration = "Welcome to this code tutorial."   # graceful fallback

    result = await apply_avatar_overlay(
        job_output_dir    = str(output_dir),
        narration_text    = narration,
        provider          = req.provider,
        api_key           = req.api_key,
        avatar_image_url  = req.avatar_image_url or None,
        heygen_avatar_id  = req.heygen_avatar_id,
        position          = req.position,
        scale             = req.scale,
    )
    if result["success"]:
        return {"success": True,
                "download_url": f"/api/jobs/{job_id}/file/tutorial_with_avatar.mp4"}
    raise HTTPException(status_code=500, detail=result.get("error", "Avatar generation failed"))

# ═══════════════════════════════════════════════════════════════════════════════
#  ZOOM-CODE FEATURE — additive only, does not touch existing endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/jobs/{job_id}/zoom-code")
async def zoom_code_segments(job_id: str):
    """
    Post-process all code-segment clips with an animated zoom-in effect,
    then re-assemble into tutorial_with_zoom.mp4.
    The original tutorial.mp4 is never modified.
    """
    output_dir = _OUTPUT_BASE / job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if not (output_dir / "visuals").exists():
        raise HTTPException(status_code=400, detail="visuals/ not found — run video generation first")

    from nodes.zoom_code_segments import apply_zoom_to_code_segments, reassemble_with_zoom
    import shutil as _shutil

    script = _load_video_script(job_id)
    job    = JOBS.get(job_id, {})

    # Step 1: Apply zoom to code clips (modifies clips in-place in visuals/)
    zoom_result = apply_zoom_to_code_segments(str(output_dir), script)
    if not zoom_result["success"]:
        raise HTTPException(status_code=500, detail=zoom_result.get("error"))

    # Step 2: Back up original tutorial.mp4, re-assemble with zoomed clips
    orig = output_dir / "tutorial.mp4"
    backup = output_dir / "tutorial_original.mp4"
    if orig.exists() and not backup.exists():
        _shutil.copy2(str(orig), str(backup))   # keep original safe

    assemble_result = reassemble_with_zoom(str(output_dir), job)

    # Restore original from backup so tutorial.mp4 is always the clean version
    if backup.exists():
        _shutil.copy2(str(backup), str(orig))

    if assemble_result["success"]:
        return {
            "success":        True,
            "zoomed_clips":   zoom_result["zoomed"],
            "skipped_clips":  zoom_result["skipped"],
            "download_url":   f"/api/jobs/{job_id}/file/tutorial_with_zoom.mp4",
        }
    raise HTTPException(status_code=500, detail=assemble_result.get("error", "Re-assembly failed"))

# ═══════════════════════════════════════════════════════════════════════════════
#  SHORTS FEATURE — additive only, does not touch existing endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/jobs/{job_id}/shorts")
async def create_shorts(job_id: str):
    """Generate per-chapter short clips from the existing tutorial.mp4."""
    output_dir = _OUTPUT_BASE / job_id
    if not (output_dir / "tutorial.mp4").exists():
        raise HTTPException(status_code=400, detail="tutorial.mp4 not found — generate the video first")

    from nodes.generate_shorts import generate_short_clips
    script = _load_video_script(job_id)

    result = await asyncio.to_thread(generate_short_clips, str(output_dir), script)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error"))

    # Add download URLs to each clip
    for clip in result["clips"]:
        clip["download_url"] = f"/api/jobs/{job_id}/file/shorts/{clip['filename']}"
    return result


@app.get("/api/jobs/{job_id}/shorts")
async def list_shorts(job_id: str):
    """List already-generated short clips for a job."""
    output_dir = _OUTPUT_BASE / job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    from nodes.generate_shorts import list_existing_shorts
    clips = list_existing_shorts(str(output_dir))
    for clip in clips:
        clip["download_url"] = f"/api/jobs/{job_id}/file/shorts/{clip['filename']}"
    return {"clips": clips}


@app.get("/api/jobs/{job_id}/file/shorts/{filename}")
async def get_short_file(job_id: str, filename: str):
    """Serve an individual short clip file."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = _OUTPUT_BASE / job_id / "shorts" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Short clip not found")
    return FileResponse(str(file_path))

# ═══════════════════════════════════════════════════════════════════════════════
#  PPTX EXPORT FEATURE — additive only, does not touch existing endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/jobs/{job_id}/export/pptx")
async def export_pptx(job_id: str):
    """Export the tutorial as a PowerPoint (.pptx) file with one slide per segment."""
    output_dir = _OUTPUT_BASE / job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if not (output_dir / "visuals").exists():
        raise HTTPException(status_code=400, detail="visuals/ not found — run video generation first")

    # Educational PPTX: reads from markdown chapters on disk, no video_script needed
    from nodes.export_pptx import export_to_pptx_educational
    result = await export_to_pptx_educational(str(output_dir))

    if result["success"]:
        pptx_path = Path(result["output_path"])
        fname = f"{repo_name_slug(job_id, output_dir)}_tutorial.pptx"
        return Response(
            content=pptx_path.read_bytes(),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    raise HTTPException(status_code=500, detail=result.get("error", "PPTX export failed"))

# ═══════════════════════════════════════════════════════════════════════════════
#  v3 FEATURES: GitHub OAuth · Quiz Generation · Notion/Confluence Export
# ═══════════════════════════════════════════════════════════════════════════════

# ── New models ────────────────────────────────────────────────────────────────
class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    correct: int
    explanation: str

class QuizResponse(BaseModel):
    questions: List[QuizQuestion]
    chapter: str

class NotionExportRequest(BaseModel):
    notion_token: str
    parent_page_id: str

class ConfluenceExportRequest(BaseModel):
    confluence_url: str
    username: str
    api_token: str
    space_key: str
    parent_page_id: Optional[str] = None

class ExportResult(BaseModel):
    success: bool
    url: Optional[str] = None
    message: str

# ── GitHub OAuth ──────────────────────────────────────────────────────────────
_GH_CLIENT_ID     = os.environ.get("GITHUB_CLIENT_ID", "")
_GH_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
_FRONTEND_URL     = os.environ.get("FRONTEND_URL", "http://localhost:3000")

@app.get("/api/auth/github")
async def github_oauth_start():
    if not _GH_CLIENT_ID:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env")
    import secrets
    state = secrets.token_urlsafe(16)
    redirect_uri = f"{_FRONTEND_URL.rstrip('/')}/auth/callback"
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={_GH_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=repo,read:user"
        f"&state={state}"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=url)

@app.get("/api/auth/github/callback")
async def github_oauth_callback(code: str, state: str = ""):
    if not _GH_CLIENT_ID or not _GH_CLIENT_SECRET:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://github.com/login/oauth/access_token",
                json={"client_id": _GH_CLIENT_ID, "client_secret": _GH_CLIENT_SECRET, "code": code},
                headers={"Accept": "application/json"},
            )
            data = r.json()
        token = data.get("access_token", "")
        if not token:
            raise HTTPException(status_code=400, detail=f"OAuth failed: {data.get('error_description', data)}")
        # Fetch user info
        async with _httpx.AsyncClient(timeout=10) as client:
            ur = await client.get("https://api.github.com/user", headers={"Authorization": f"token {token}", "Accept": "application/json"})
            user = ur.json()
        from fastapi.responses import RedirectResponse
        import urllib.parse
        params = urllib.parse.urlencode({"token": token, "login": user.get("login",""), "avatar": user.get("avatar_url","")})
        return RedirectResponse(url=f"{_FRONTEND_URL}/auth/callback?{params}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OAuth error: {exc}")

@app.get("/api/auth/me")
async def get_me(authorization: Optional[str] = None):
    from fastapi import Header
    token = authorization.replace("Bearer ", "") if authorization else ""
    if not token:
        return {"authenticated": False}
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.github.com/user", headers={"Authorization": f"token {token}", "Accept": "application/json"})
            if r.status_code != 200:
                return {"authenticated": False}
            u = r.json()
            return {"authenticated": True, "login": u.get("login"), "name": u.get("name"), "avatar_url": u.get("avatar_url")}
    except Exception:
        return {"authenticated": False}

# ── Quiz Generation ───────────────────────────────────────────────────────────
_QUIZ_CACHE: dict = {}

@app.get("/api/jobs/{job_id}/quiz/{chapter}", response_model=QuizResponse)
async def generate_quiz(job_id: str, chapter: str):
    cache_key = f"{job_id}:{chapter}"
    if cache_key in _QUIZ_CACHE:
        return _QUIZ_CACHE[cache_key]

    output_dir = _OUTPUT_BASE / job_id
    chapter_path = output_dir / chapter
    if not chapter_path.exists() or chapter_path.suffix != ".md":
        raise HTTPException(status_code=404, detail="Chapter not found")

    content = chapter_path.read_text(encoding="utf-8")[:4000]
    prompt = f"""You are a coding tutor. Based on the tutorial chapter below, generate exactly 5 multiple-choice quiz questions to test understanding.

Chapter content:
{content}

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{{
  "questions": [
    {{
      "question": "What does X do?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct": 0,
      "explanation": "Option A is correct because..."
    }}
  ]
}}

Rules:
- Each question must have exactly 4 options
- "correct" is the 0-based index of the correct answer
- Questions should test real understanding, not trivia
- Keep questions concise and clear"""

    try:
        from llm.router import llm_call
        raw = await llm_call(prompt, bypass_cache=False)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        import json as _json
        data = _json.loads(raw)
        questions = [QuizQuestion(**q) for q in data["questions"]]
        result = QuizResponse(questions=questions, chapter=chapter)
        _QUIZ_CACHE[cache_key] = result
        return result
    except Exception as exc:
        logger.error("Quiz generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {exc}")

# ── Notion Export ─────────────────────────────────────────────────────────────
@app.post("/api/jobs/{job_id}/export/notion", response_model=ExportResult)
async def export_to_notion(job_id: str, req: NotionExportRequest):
    output_dir = _OUTPUT_BASE / job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    md_files = sorted(output_dir.glob("*.md"), key=lambda p: p.name)
    if not md_files:
        raise HTTPException(status_code=404, detail="No tutorial files found")
    try:
        import httpx as _httpx
        headers = {
            "Authorization": f"Bearer {req.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        # Create parent page for this tutorial
        repo_url = JOBS.get(job_id, {}).get("repo_url", job_id)
        repo_name = repo_url.rstrip("/").split("/")[-1] if "/" in repo_url else job_id

        async with _httpx.AsyncClient(timeout=30) as client:
            # Create top-level page
            parent_page = await client.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
                json={
                    "parent": {"page_id": req.parent_page_id},
                    "properties": {"title": {"title": [{"text": {"content": f"CodeNarrator: {repo_name}"}}]}},
                    "children": [{
                        "object": "block", "type": "callout",
                        "callout": {"rich_text": [{"text": {"content": f"Auto-generated tutorial for {repo_url}"}}], "icon": {"emoji": "📚"}}
                    }]
                }
            )
            if parent_page.status_code not in (200, 201):
                return ExportResult(success=False, message=f"Notion API error: {parent_page.text[:200]}")
            top_page_id = parent_page.json()["id"]
            top_page_url = parent_page.json().get("url", "")

            # Create a child page per chapter
            for md_file in md_files:
                text = md_file.read_text(encoding="utf-8")
                title = md_file.stem.replace("_", " ").replace("-", " ").title()
                # Split into paragraphs (max 2000 chars each for Notion API)
                paragraphs = [text[i:i+1900] for i in range(0, min(len(text), 9500), 1900)]
                children = [{"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content": p}}]}} for p in paragraphs]
                await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=headers,
                    json={
                        "parent": {"page_id": top_page_id},
                        "properties": {"title": {"title": [{"text": {"content": title}}]}},
                        "children": children[:100],
                    }
                )
        return ExportResult(success=True, url=top_page_url, message=f"Exported {len(md_files)} chapters to Notion")
    except Exception as exc:
        logger.error("Notion export failed: %s", exc)
        return ExportResult(success=False, message=f"Export failed: {exc}")

# ── Confluence Export ─────────────────────────────────────────────────────────
@app.post("/api/jobs/{job_id}/export/confluence", response_model=ExportResult)
async def export_to_confluence(job_id: str, req: ConfluenceExportRequest):
    output_dir = _OUTPUT_BASE / job_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    md_files = sorted(output_dir.glob("*.md"), key=lambda p: p.name)
    if not md_files:
        raise HTTPException(status_code=404, detail="No tutorial files found")
    try:
        import httpx as _httpx
        import base64 as _b64
        import markdown as _md

        creds = _b64.b64encode(f"{req.username}:{req.api_token}".encode()).decode()
        base = req.confluence_url.rstrip("/")
        headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/json", "Accept": "application/json"}
        repo_url = JOBS.get(job_id, {}).get("repo_url", job_id)
        repo_name = repo_url.rstrip("/").split("/")[-1] if "/" in repo_url else job_id

        async with _httpx.AsyncClient(timeout=30) as client:
            # Create parent page
            parent_body = {
                "type": "page",
                "title": f"CodeNarrator: {repo_name}",
                "space": {"key": req.space_key},
                "body": {"storage": {"value": f"<p>Auto-generated tutorial for <a href='{repo_url}'>{repo_url}</a></p>", "representation": "storage"}},
            }
            if req.parent_page_id:
                parent_body["ancestors"] = [{"id": req.parent_page_id}]
            pr = await client.post(f"{base}/rest/api/content", headers=headers, json=parent_body)
            if pr.status_code not in (200, 201):
                return ExportResult(success=False, message=f"Confluence error: {pr.text[:200]}")
            parent_id = pr.json()["id"]
            parent_link = pr.json().get("_links", {}).get("webui", "")
            full_url = f"{base}{parent_link}" if parent_link else ""

            for md_file in md_files:
                text = md_file.read_text(encoding="utf-8")
                title = md_file.stem.replace("_", " ").replace("-", " ").title()
                html = _md.markdown(text[:8000], extensions=["fenced_code", "tables"])
                page_body = {
                    "type": "page",
                    "title": title,
                    "ancestors": [{"id": parent_id}],
                    "space": {"key": req.space_key},
                    "body": {"storage": {"value": html, "representation": "storage"}},
                }
                await client.post(f"{base}/rest/api/content", headers=headers, json=page_body)

        return ExportResult(success=True, url=full_url, message=f"Exported {len(md_files)} chapters to Confluence")
    except Exception as exc:
        logger.error("Confluence export failed: %s", exc)
        return ExportResult(success=False, message=f"Export failed: {exc}")
