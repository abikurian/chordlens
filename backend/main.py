"""FastAPI server for ChordLens."""

from __future__ import annotations

import mimetypes
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.analyze import analyze_audio
from backend.youtube import download_youtube_audio

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "tmp" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac"}
EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOBS: dict[str, dict[str, Any]] = {}

app = FastAPI(title="ChordLens", version="0.2.0")


class AnalyzeUrlRequest(BaseModel):
    url: str
    mode: str = "fast"


def _find_audio_file(audio_id: str) -> Path | None:
    # Prevent path traversal by allowing only hex UUID characters
    if not audio_id.isalnum():
        return None
    for candidate in UPLOAD_DIR.glob(f"{audio_id}.*"):
        if candidate.is_file():
            return candidate
    return None


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
            detail=f"Analysis failed: {exc}. Try converting the file to WAV or MP3 and retry.",
        ) from exc

    return {
        "audio_id": audio_id,
        "audio_url": f"/api/audio/{audio_id}",
        "title": Path(file.filename).stem,
        **result,
    }


@app.post("/api/analyze-url")
def analyze_url(payload: AnalyzeUrlRequest) -> dict:
    audio_id = uuid.uuid4().hex
    try:
        audio_path, title = download_youtube_audio(payload.url, UPLOAD_DIR, audio_id)
        result = analyze_audio(audio_path, mode=payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not analyze YouTube audio: {exc}",
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
        JOBS[job_id]["error"] = str(exc)


def _run_url_job(job_id: str, audio_id: str, url: str, mode: str) -> None:
    def on_progress(stage: str) -> None:
        JOBS[job_id]["stage"] = stage

    try:
        JOBS[job_id]["stage"] = "Downloading audio from YouTube..."
        audio_path, title = download_youtube_audio(url, UPLOAD_DIR, audio_id)
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
        JOBS[job_id]["error"] = str(exc)


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
    audio_id = uuid.uuid4().hex
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "running", "stage": "Queued...", "result": None, "error": None}
    EXECUTOR.submit(_run_url_job, job_id, audio_id, payload.url, payload.mode)
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

