"""YouTube audio download helper using yt-dlp and ffmpeg."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from backend.ffmpeg_utils import (
    configure_ffmpeg_env,
    friendly_error_message,
    friendly_missing_ffmpeg_message,
)
from backend.log_utils import append_to_app_log, safe_json_loads

MAX_YOUTUBE_DURATION_SEC = 12 * 60  # 12 minutes
ALLOWED_COOKIE_BROWSERS = {"chrome", "edge", "firefox", "brave", "opera", "safari"}
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
STRIP_QUERY_PARAMS = {
    "list",
    "index",
    "start_radio",
    "rv",
    "si",
    "pp",
    "feature",
    "ab_channel",
    "fbclid",
    "gclid",
}


def normalize_youtube_url(url: str) -> str:
    """Validate and normalize a YouTube URL, stripping playlist and tracking params."""
    raw = (url or "").strip()
    try:
        parsed = urlparse(raw)
    except Exception as exc:
        raise ValueError(
            "Enter a valid YouTube link (youtube.com, youtu.be, or music.youtube.com)."
        ) from exc

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            "Enter a valid YouTube link starting with https:// (youtube.com, youtu.be, or music.youtube.com)."
        )

    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        raise ValueError(
            "Only YouTube links are supported (youtube.com, youtu.be, or music.youtube.com)."
        )

    qs = parse_qs(parsed.query, keep_blank_values=False)
    cleaned_qs: dict[str, list[str]] = {}
    for k, vals in qs.items():
        lk = k.lower()
        if lk in STRIP_QUERY_PARAMS or lk.startswith("utm_"):
            continue
        cleaned_qs[k] = vals

    if host != "youtu.be" and parsed.path.rstrip("/") == "/watch" and "v" not in cleaned_qs:
        raise ValueError("This YouTube watch link is missing a video ID (?v=...).")
    if host == "youtu.be" and not parsed.path.strip("/"):
        raise ValueError("This youtu.be link is missing a video ID.")

    new_query = urlencode(cleaned_qs, doseq=True)
    return urlunparse(("https", host, parsed.path, "", new_query, ""))


def extract_youtube_video_id(url: str) -> str:
    """Extract canonical YouTube video ID from any watch, short, embed, or youtu.be URL."""
    clean_url = normalize_youtube_url(url)
    parsed = urlparse(clean_url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        vid = parsed.path.strip("/").split("/")[0]
        if vid:
            return vid
    qs = parse_qs(parsed.query)
    if "v" in qs and qs["v"]:
        return qs["v"][0]
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] in ("embed", "v", "shorts"):
        return parts[1]
    return hashlib.sha256(clean_url.encode("utf-8")).hexdigest()[:16]


def is_valid_youtube_url(url: str) -> bool:
    """Return True if the URL is a supported YouTube video link."""
    try:
        normalize_youtube_url(url)
        return True
    except ValueError:
        return False


def _detect_js_runtime_args(toolchain: dict[str, str | None]) -> list[str]:
    """Return yt-dlp --js-runtimes args if Deno or Node is installed."""
    if toolchain.get("deno"):
        return ["--js-runtimes", f"deno:{toolchain['deno']}"]
    if toolchain.get("node"):
        return ["--js-runtimes", f"node:{toolchain['node']}"]
    return []


def _friendly_yt_dlp_error(raw_err: str) -> str:
    """Map raw yt-dlp stderr/stdout to a plain-language message with next steps."""
    low = raw_err.lower()
    fallback = "If YouTube keeps failing, download the audio yourself and use the upload box."

    if "private video" in low:
        return f"This YouTube video is private. Make it public, or {fallback[0].lower()}{fallback[1:]}"
    if "video unavailable" in low or "is not available" in low or "removed by the uploader" in low:
        return f"This YouTube video is unavailable. Check the link, or {fallback[0].lower()}{fallback[1:]}"
    if "confirm your age" in low or "age-restricted" in low:
        return (
            "This video is age-restricted and requires sign-in. "
            f"Enable browser cookies in Options (for personal use), or {fallback[0].lower()}{fallback[1:]}"
        )
    if "not a bot" in low or "sign in to confirm" in low or "cookies" in low:
        return (
            "YouTube asked to confirm you are not a bot. "
            f"Enable browser cookies in Options (for personal use), or {fallback[0].lower()}{fallback[1:]}"
        )
    if "429" in low or "too many requests" in low or "http error 403" in low or "403: forbidden" in low:
        return (
            "YouTube blocked or rate-limited this request (HTTP 403/429). "
            f"Wait a few minutes or update yt-dlp (`pip install -U yt-dlp`). {fallback}"
        )
    if "unable to extract" in low or "nsig" in low or "signature extraction" in low:
        return (
            "yt-dlp could not read this YouTube page and may need an update (`pip install -U yt-dlp`). "
            f"{fallback}"
        )
    if "ffmpeg" in low and ("not found" in low or "missing" in low):
        return "ffmpeg was not found on PATH. Install ffmpeg and restart the server, or upload a WAV/MP3 file."

    append_to_app_log(f"[YOUTUBE ERROR] raw yt-dlp error output:\n{raw_err.strip()}")
    return "That link could not be read. Check that it is a normal YouTube video link, or upload the audio file instead."


def download_youtube_audio(
    url: str,
    output_dir: Path,
    file_stem: str,
    cookies_browser: str | None = None,
) -> tuple[Path, str]:
    """Download audio from YouTube in a single fast yt-dlp call (audio only, concurrent fragments).

    Returns (audio_path, video_title).
    """
    clean_url = normalize_youtube_url(url)
    toolchain = configure_ffmpeg_env()
    if not toolchain.get("ffmpeg"):
        raise RuntimeError(friendly_missing_ffmpeg_message())

    cookie_args: list[str] = []
    if cookies_browser:
        browser = cookies_browser.strip().lower()
        if browser not in ALLOWED_COOKIE_BROWSERS:
            raise ValueError(f"Unsupported cookie browser '{cookies_browser}'.")
        cookie_args = ["--cookies-from-browser", browser]

    ffmpeg_args: list[str] = []
    if toolchain.get("ffmpeg_dir"):
        ffmpeg_args = ["--ffmpeg-location", str(toolchain["ffmpeg_dir"])]

    js_args = _detect_js_runtime_args(toolchain)
    base_cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", *ffmpeg_args, *js_args, *cookie_args]

    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / f"{file_stem}.%(ext)s")

    # Fast single-pass download: fetch audio stream with concurrent fragments and dump JSON metadata in one command
    cmd = [
        *base_cmd,
        "-f", "ba[ext=m4a]/ba",
        "-x",
        "--audio-format", "m4a",
        "--concurrent-fragments", "5",
        "--print-json",
        "-o", output_template,
        clean_url,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "YouTube download timed out. Try a shorter video or download the audio yourself and use the upload box."
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(friendly_error_message(exc, context="youtube")) from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "Unknown yt-dlp error").strip()
        append_to_app_log(f"[YOUTUBE ERROR] yt-dlp download failed (code {proc.returncode}):\n{err}")
        raise RuntimeError(_friendly_yt_dlp_error(err))

    title = "YouTube Audio"
    meta = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            meta = safe_json_loads(
                line,
                context="youtube.py:download_youtube_audio(print-json)",
                allow_fallback=True,
                fallback_value=None,
            )
            if isinstance(meta, dict) and meta.get("title"):
                break

    if isinstance(meta, dict):
        if meta.get("title"):
            title = str(meta["title"]).strip()
        duration = meta.get("duration")
        if isinstance(duration, (int, float)) and duration > MAX_YOUTUBE_DURATION_SEC:
            # Clean up downloaded files
            for candidate in output_dir.glob(f"{file_stem}.*"):
                candidate.unlink(missing_ok=True)
            mins = int(duration // 60)
            secs = int(duration % 60)
            raise ValueError(
                f"Video is {mins}m {secs}s long (limit is 12 minutes). "
                "Download the audio yourself and use the upload box instead."
            )

    matches = [
        p for p in output_dir.glob(f"{file_stem}.*")
        if p.is_file() and p.suffix.lower() != ".json"
    ]
    if not matches:
        raise RuntimeError(
            "yt-dlp finished but no audio file was produced. "
            "Download the audio yourself and use the upload box."
        )

    # Prefer m4a if multiple extensions exist, else take first
    chosen = next((p for p in matches if p.suffix.lower() == ".m4a"), matches[0])
    return chosen, title
