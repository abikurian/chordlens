"""FastAPI server for ChordLens."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.analyze import analyze_audio
from backend.ffmpeg_utils import friendly_error_message, get_system_status
from backend.log_utils import append_to_app_log, get_recent_logs, safe_json_loads, log_startup_toolchain
from backend.paths import (
    CACHE_DIR,
    CACHE_YT_DIR,
    DATA_DIR,
    LOGS_DIR,
    MODELS_DIR,
    UPLOAD_DIR,
    clear_app_cache,
    get_frontend_dir,
)
from backend.version import get_version
from backend.youtube import download_youtube_audio, normalize_youtube_url

FRONTEND_DIR = get_frontend_dir()

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac"}
EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOBS: dict[str, dict[str, Any]] = {}

app = FastAPI(title="ChordLens", version=get_version())


@app.on_event("startup")
def on_startup() -> None:
    log_startup_toolchain()


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if not path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


class AnalyzeUrlRequest(BaseModel):
    url: str
    mode: str = "fast"
    cookies_browser: str | None = None


def _find_audio_file(audio_id: str) -> Path | None:
    # Prevent path traversal by allowing only alphanumeric characters
    if not audio_id.isalnum():
        return None
    for directory in (UPLOAD_DIR, CACHE_YT_DIR):
        for candidate in directory.glob(f"{audio_id}.*"):
            if candidate.is_file() and candidate.suffix.lower() != ".json":
                return candidate
    return None


def _get_or_download_youtube(
    url: str,
    cookies_browser: str | None = None,
) -> tuple[str, Path, str]:
    clean_url = normalize_youtube_url(url)
    url_hash = hashlib.sha256(clean_url.encode("utf-8")).hexdigest()[:24]
    audio_id = f"yt{url_hash}"
    meta_path = CACHE_YT_DIR / f"{audio_id}.json"
    cached_audio = _find_audio_file(audio_id)

    if cached_audio is not None and meta_path.exists():
        meta = safe_json_loads(
            meta_path.read_text(encoding="utf-8"),
            context=f"main.py:meta_path({meta_path.name})",
            allow_fallback=True,
            fallback_value=None,
        )
        if meta and isinstance(meta, dict):
            return audio_id, cached_audio, str(meta.get("title") or "YouTube Audio")
        # Corrupted meta cache
        meta_path.unlink(missing_ok=True)

    audio_path, title = download_youtube_audio(
        clean_url,
        CACHE_YT_DIR,
        audio_id,
        cookies_browser=cookies_browser,
    )
    meta_path.write_text(
        json.dumps({"title": title, "url": clean_url}, ensure_ascii=False),
        encoding="utf-8",
    )
    return audio_id, audio_path, title


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/health")
def health() -> dict[str, Any]:
    status = get_system_status()
    models_present = bool(list(MODELS_DIR.glob("*.pt")) or list(MODELS_DIR.glob("*.pth")))
    return {
        "status": "ok",
        "version": get_version(),
        "ffmpeg": "OK" if status.get("ffmpeg_ok") else "MISSING",
        "yt_dlp": status.get("ytdlp_version") or "unknown",
        "models": "present" if models_present else "on-demand",
        "data_dir": str(DATA_DIR),
    }


@app.post("/api/system/open-data-dir")
def open_data_dir() -> dict[str, str]:
    import subprocess
    try:
        if os.name == "nt":
            os.startfile(str(DATA_DIR))
        else:
            subprocess.run(["xdg-open", str(DATA_DIR)], check=False)
        return {"status": "ok", "detail": f"Opened {DATA_DIR}"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.post("/api/system/clear-cache")
def clear_cache_endpoint() -> dict[str, Any]:
    count = clear_app_cache()
    return {"status": "ok", "detail": f"Cleared {count} cached file(s)"}


@app.post("/api/system/update-ytdlp")
def update_ytdlp_endpoint() -> dict[str, Any]:
    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "--target", str(DATA_DIR / "packages")],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if proc.returncode == 0:
            return {"status": "ok", "detail": "yt-dlp updated successfully"}
        return {"status": "error", "detail": proc.stderr or proc.stdout or "Update failed"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.get("/api/system/diagnostics")
def system_diagnostics_endpoint() -> dict[str, Any]:
    return {
        "version": get_version(),
        "logs": get_recent_logs(50),
    }


@app.exception_handler(json.JSONDecodeError)
async def json_decode_exception_handler(request: Request, exc: json.JSONDecodeError):
    append_to_app_log(f"[FASTAPI JSON ERROR] {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=400,
        content={"detail": "The request contained invalid data. Please check and try again."},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    tb = traceback.format_exc()
    append_to_app_log(f"[FASTAPI UNHANDLED] {request.method} {request.url.path}: {exc}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Use 'Copy diagnostics' for details or restart the app."},
    )


@app.post("/api/analyze")
async def analyze_upload(
    file: UploadFile = File(...),
    mode: str = Form("fast"),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Choose an audio file to analyze.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Use MP3, WAV, M4A, or FLAC.",
        )

    audio_id = uuid.uuid4().hex
    dest = UPLOAD_DIR / f"{audio_id}{ext}"

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        dest.write_bytes(content)
        result = analyze_audio(dest, mode=mode)
    except HTTPException:
        raise
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=friendly_error_message(exc, context="analysis"),
        ) from exc

    return {
        "audio_id": audio_id,
        "audio_url": f"/api/audio/{audio_id}",
        "title": Path(file.filename).stem,
        **result,
    }


@app.post("/api/analyze-url")
def analyze_url(payload: AnalyzeUrlRequest) -> dict:
    try:
        audio_id, audio_path, title = _get_or_download_youtube(
            payload.url,
            cookies_browser=payload.cookies_browser,
        )
        result = analyze_audio(audio_path, mode=payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=friendly_error_message(exc, context="youtube"),
        ) from exc

    return {
        "audio_id": audio_id,
        "audio_url": f"/api/audio/{audio_id}",
        "title": title,
        **result,
    }


def _run_file_job(job_id: str, audio_id: str, dest: Path, title: str, mode: str) -> None:
    def on_progress(stage: str) -> None:
        JOBS[job_id]["stage"] = stage

    try:
        result = analyze_audio(dest, mode=mode, progress_cb=on_progress)
        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["stage"] = "Done"
        JOBS[job_id]["result"] = {
            "audio_id": audio_id,
            "audio_url": f"/api/audio/{audio_id}",
            "title": title,
            **result,
        }
    except Exception as exc:
        dest.unlink(missing_ok=True)
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = friendly_error_message(exc, context="analysis")


def _run_url_job(
    job_id: str,
    url: str,
    mode: str,
    cookies_browser: str | None = None,
) -> None:
    def on_progress(stage: str) -> None:
        JOBS[job_id]["stage"] = stage

    try:
        JOBS[job_id]["stage"] = "Downloading audio from YouTube..."
        audio_id, audio_path, title = _get_or_download_youtube(
            url,
            cookies_browser=cookies_browser,
        )
        result = analyze_audio(audio_path, mode=mode, progress_cb=on_progress)
        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["stage"] = "Done"
        JOBS[job_id]["result"] = {
            "audio_id": audio_id,
            "audio_url": f"/api/audio/{audio_id}",
            "title": title,
            **result,
        }
    except Exception as exc:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = friendly_error_message(exc, context="youtube")


@app.post("/api/jobs/analyze")
async def start_analyze_job(
    file: UploadFile = File(...),
    mode: str = Form("fast"),
) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Choose an audio file to analyze.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Use MP3, WAV, M4A, or FLAC.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    audio_id = uuid.uuid4().hex
    job_id = uuid.uuid4().hex
    dest = UPLOAD_DIR / f"{audio_id}{ext}"
    dest.write_bytes(content)

    JOBS[job_id] = {"status": "running", "stage": "Queued...", "result": None, "error": None}
    EXECUTOR.submit(_run_file_job, job_id, audio_id, dest, Path(file.filename).stem, mode)
    return {"job_id": job_id}


@app.post("/api/jobs/analyze-url")
def start_analyze_url_job(payload: AnalyzeUrlRequest) -> dict[str, str]:
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "running", "stage": "Queued...", "result": None, "error": None}
    EXECUTOR.submit(_run_url_job, job_id, payload.url, payload.mode, payload.cookies_browser)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return job


@app.get("/api/audio/{audio_id}")
def stream_audio(audio_id: str) -> FileResponse:
    path = _find_audio_file(audio_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Audio file not found.")
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=media_type or "application/octet-stream")


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

