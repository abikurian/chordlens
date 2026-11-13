"""Resolve bundled ffmpeg, ffprobe, and JS runtime (Deno) inside the app folder first,
and format friendly user-facing messages.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.paths import get_bin_dir


def is_ffmpeg_lgpl(ffmpeg_path: str | Path) -> tuple[bool, str]:
    """Verify that the given ffmpeg binary is LGPL-compliant (no --enable-gpl, no --enable-nonfree)."""
    try:
        proc = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        out = proc.stdout + proc.stderr
        for line in out.splitlines():
            if "configuration:" in line.lower():
                has_gpl = "--enable-gpl" in line
                has_nonfree = "--enable-nonfree" in line
                if has_gpl or has_nonfree:
                    return False, f"Non-LGPL flags detected: gpl={has_gpl}, nonfree={has_nonfree}"
                return True, "LGPL verified (no GPL/nonfree flags)"
        return True, "No configuration flags found, assuming OK"
    except Exception as exc:
        return False, f"Failed to run ffmpeg: {exc}"


def _find_binary(name: str, preferred_dir: Path, fallback_to_path: bool = True) -> str | None:
    """Find a binary in preferred_dir first, then PATH."""
    exe_names = [f"{name}.exe", name] if os.name == "nt" else [name]
    for exe in exe_names:
        candidate = preferred_dir / exe
        if candidate.is_file():
            return str(candidate)

    if fallback_to_path:
        found = shutil.which(name)
        if found:
            return found

    return None


@lru_cache(maxsize=1)
def resolve_toolchain() -> dict[str, str | None]:
    """Resolve ffmpeg, ffprobe, and Deno from the bundled bin folder first, and prepend to PATH."""
    bin_dir = get_bin_dir()

    ffmpeg_path = _find_binary("ffmpeg", bin_dir, fallback_to_path=True)
    ffprobe_path = _find_binary("ffprobe", bin_dir, fallback_to_path=True)
    deno_path = _find_binary("deno", bin_dir, fallback_to_path=True)
    node_path = _find_binary("node", bin_dir, fallback_to_path=True)

    ffmpeg_dir: str | None = None
    if ffmpeg_path:
        ffmpeg_dir = str(Path(ffmpeg_path).resolve().parent)
        current_path = os.environ.get("PATH", "")
        if ffmpeg_dir.lower() not in current_path.lower():
            os.environ["PATH"] = f"{ffmpeg_dir}{os.pathsep}{current_path}" if current_path else ffmpeg_dir

    if deno_path:
        deno_dir = str(Path(deno_path).resolve().parent)
        current_path = os.environ.get("PATH", "")
        if deno_dir.lower() not in current_path.lower():
            os.environ["PATH"] = f"{deno_dir}{os.pathsep}{current_path}" if current_path else deno_dir

    return {
        "ffmpeg": ffmpeg_path,
        "ffprobe": ffprobe_path,
        "ffmpeg_dir": ffmpeg_dir,
        "deno": deno_path,
        "node": node_path,
    }


def configure_ffmpeg_env() -> dict[str, str | None]:
    """Ensure resolved ffmpeg directory is on PATH for subprocesses (yt-dlp, librosa, demucs)."""
    return resolve_toolchain()


def get_yt_dlp_version() -> str:
    """Return installed yt-dlp version string or 'MISSING'."""
    try:
        import yt_dlp.version

        ver = getattr(yt_dlp.version, "__version__", None)
        if ver:
            return str(ver)
    except Exception:
        pass

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return "MISSING"


def log_startup_toolchain() -> dict[str, str | None]:
    """Print startup diagnostics for ffmpeg, ffprobe, JS runtime, and yt-dlp."""
    tc = resolve_toolchain()
    yt_ver = get_yt_dlp_version()

    ffmpeg_msg = f"OK ({tc['ffmpeg']})" if tc["ffmpeg"] else "MISSING"
    ffprobe_msg = f"OK ({tc['ffprobe']})" if tc["ffprobe"] else "MISSING"
    if tc["deno"]:
        js_msg = f"deno ({tc['deno']})"
    elif tc["node"]:
        js_msg = f"node ({tc['node']})"
    else:
        js_msg = "MISSING"

    print(f"[ChordLens startup] ffmpeg: {ffmpeg_msg}")
    print(f"[ChordLens startup] ffprobe: {ffprobe_msg}")
    print(f"[ChordLens startup] js_runtime: {js_msg}")
    print(f"[ChordLens startup] yt-dlp: {yt_ver}")
    return tc


def get_system_status() -> dict[str, Any]:
    """Return lightweight toolchain status for UI diagnostics and health checks."""
    tc = resolve_toolchain()
    yt_ver = get_yt_dlp_version()
    return {
        "ffmpeg_ok": bool(tc["ffmpeg"]),
        "ffmpeg_path": tc["ffmpeg"],
        "ffprobe_ok": bool(tc["ffprobe"]),
        "ffprobe_path": tc["ffprobe"],
        "js_runtime": tc["deno"] or tc["node"],
        "ytdlp_version": yt_ver if yt_ver != "MISSING" else None,
    }


def friendly_missing_ffmpeg_message() -> str:
    """Plain-language instructions when bundled ffmpeg is not found."""
    return (
        "ChordLens helper program (ffmpeg) was not found. "
        "The application installation may be incomplete or corrupted. Please reinstall ChordLens."
    )


def friendly_error_message(exc: Exception, context: str = "analysis") -> str:
    """Log the full traceback to chordlens.log and return a plain-language UI message."""
    tb = traceback.format_exc()
    raw = str(exc).strip()
    low = raw.lower()

    try:
        from backend.log_utils import append_to_app_log

        append_to_app_log(f"[{context.upper()} EXCEPTION] {type(exc).__name__}: {raw}\n{tb}")
    except Exception:
        pass

    # Helper executable not found
    if isinstance(exc, FileNotFoundError) or "winerror 2" in low or "cannot find the file specified" in low:
        tc = resolve_toolchain()
        if not tc.get("ffmpeg"):
            return friendly_missing_ffmpeg_message()
        return (
            "A required helper program (ffmpeg or yt-dlp) could not be launched. "
            "Please restart the app, or reinstall ChordLens if the problem continues."
        )

    if context == "youtube":
        if "limit is 12 minutes" in low or "video is " in low:
            return raw
        if "private video" in low:
            return "This YouTube video is private. Make it public, or upload the audio file instead."
        if "unavailable" in low or "removed by the uploader" in low:
            return "That YouTube video is unavailable or was removed. Check the link, or upload the audio file instead."
        if "confirm your age" in low or "age-restricted" in low:
            return "This video is age-restricted. Enable browser cookies in Options (for personal use), or upload the audio file instead."
        if "not a bot" in low or "sign in to confirm" in low:
            return "YouTube asked to confirm you are not a bot. Enable browser cookies in Options (for personal use), or upload the audio file instead."
        if "429" in low or "too many requests" in low or "403" in low:
            return "YouTube rate-limited or blocked this request. Wait a few minutes, update yt-dlp in Options, or upload the audio file instead."
        return "That link could not be read. Check that it is a normal YouTube video link, or upload the audio file instead."

    # Audio file analysis errors
    if "empty or silent" in low:
        return "The audio file appears to be empty or silent. Check the file in another media player and try uploading again."
    if "memory" in low or "out of memory" in low:
        return "The system ran out of memory during analysis. Try using Fast mode or a shorter audio file."
    if "unsupported file type" in low:
        return raw
    return "Could not analyze this audio file. Try converting it to WAV or MP3 and uploading again."
