"""YouTube audio download helper using yt-dlp and ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

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


def is_valid_youtube_url(url: str) -> bool:
    """Return True if the URL is a supported YouTube video link."""
    try:
        normalize_youtube_url(url)
        return True
    except ValueError:
        return False


def _detect_js_runtime_args() -> list[str]:
    """Return yt-dlp --js-runtimes args if Deno or Node is installed."""
    if shutil.which("deno"):
        return ["--js-runtimes", "deno"]
    if shutil.which("node"):
        return ["--js-runtimes", "node"]
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

    last_line = raw_err.strip().splitlines()[-1] if raw_err.strip() else "Download failed"
    return f"Could not download audio from YouTube ({last_line}). {fallback}"


def download_youtube_audio(
    url: str,
    output_dir: Path,
    file_stem: str,
    cookies_browser: str | None = None,
) -> tuple[Path, str]:
    """Download audio from YouTube as a WAV file via yt-dlp + ffmpeg.

    Returns (wav_path, video_title).
    """
    clean_url = normalize_youtube_url(url)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg was not found on PATH inside the server environment. "
            "Install ffmpeg and restart the server, or upload an audio file directly."
        )

    cookie_args: list[str] = []
    if cookies_browser:
        browser = cookies_browser.strip().lower()
        if browser not in ALLOWED_COOKIE_BROWSERS:
            raise ValueError(f"Unsupported cookie browser '{cookies_browser}'.")
        cookie_args = ["--cookies-from-browser", browser]

    js_args = _detect_js_runtime_args()
    base_cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", *js_args, *cookie_args]

    # Fetch title and duration first (fast, no download)
    title = "YouTube Audio"
    try:
        info_proc = subprocess.run(
            [*base_cmd, "--dump-single-json", "--skip-download", clean_url],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Timed out checking YouTube video details. Try again or download the audio yourself and use the upload box."
        ) from exc

    if info_proc.returncode == 0 and info_proc.stdout.strip():
        try:
            meta = json.loads(info_proc.stdout.strip().splitlines()[-1])
            if meta.get("title"):
                title = str(meta["title"]).strip()
            duration = meta.get("duration")
            if isinstance(duration, (int, float)) and duration > MAX_YOUTUBE_DURATION_SEC:
                mins = int(duration // 60)
                secs = int(duration % 60)
                raise ValueError(
                    f"Video is {mins}m {secs}s long (limit is 12 minutes). "
                    "Download the audio yourself and use the upload box instead."
                )
        except ValueError:
            raise
        except Exception:
            pass
    elif info_proc.returncode != 0:
        err = (info_proc.stderr or info_proc.stdout or "").strip()
        if err:
            raise RuntimeError(_friendly_yt_dlp_error(err))

    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / f"{file_stem}.%(ext)s")

    cmd = [
        *base_cmd,
        "-x",
        "--audio-format",
        "wav",
        "--audio-quality",
        "0",
        "-o",
        output_template,
        clean_url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "YouTube download timed out. Try a shorter video or download the audio yourself and use the upload box."
        ) from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "Unknown yt-dlp error").strip()
        raise RuntimeError(_friendly_yt_dlp_error(err))

    wav_path = output_dir / f"{file_stem}.wav"
    if not wav_path.exists():
        matches = list(output_dir.glob(f"{file_stem}.*"))
        if not matches:
            raise RuntimeError(
                "yt-dlp finished but no audio file was produced. "
                "Download the audio yourself and use the upload box."
            )
        wav_path = matches[0]

    return wav_path, title
