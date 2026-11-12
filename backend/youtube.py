"""YouTube audio download helper using yt-dlp and ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


def is_valid_youtube_url(url: str) -> bool:
    """Return True if the URL looks like a YouTube watch or share link."""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }


def download_youtube_audio(url: str, output_dir: Path, file_stem: str) -> tuple[Path, str]:
    """Download audio from YouTube as a WAV file via yt-dlp + ffmpeg.

    Returns (wav_path, video_title).
    """
    clean_url = url.strip()
    if not is_valid_youtube_url(clean_url):
        raise ValueError(
            "Enter a valid YouTube link (youtube.com or youtu.be)."
        )

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg was not found on PATH. Install ffmpeg and restart the server."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / f"{file_stem}.%(ext)s")

    # Fetch title first (fast, no download)
    title = "YouTube Audio"
    try:
        title_proc = subprocess.run(
            ["yt-dlp", "--no-playlist", "--print", "%(title)s", clean_url],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        if title_proc.returncode == 0 and title_proc.stdout.strip():
            title = title_proc.stdout.strip().splitlines()[0]
    except Exception:
        pass

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-x",
        "--audio-format",
        "wav",
        "--audio-quality",
        "0",
        "-o",
        output_template,
        clean_url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "Unknown yt-dlp error").strip()
        last_line = err.splitlines()[-1] if err else "Download failed"
        raise RuntimeError(
            f"Could not download audio from YouTube ({last_line}). "
            "Check that the video is public and yt-dlp is up to date."
        )

    wav_path = output_dir / f"{file_stem}.wav"
    if not wav_path.exists():
        matches = list(output_dir.glob(f"{file_stem}.*"))
        if not matches:
            raise RuntimeError("yt-dlp finished but no audio file was produced.")
        wav_path = matches[0]

    return wav_path, title

