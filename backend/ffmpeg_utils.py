"""Resolve ffmpeg, ffprobe, and JS runtime paths once at startup and format friendly errors."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from functools import lru_cache
from pathlib import Path


def _candidate_bin_dirs() -> list[Path]:
    """Return common Windows/cross-platform install directories for ffmpeg."""
    dirs: list[Path] = []
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        winget_links = Path(local_app) / "Microsoft" / "WinGet" / "Links"
        if winget_links.is_dir():
            dirs.append(winget_links)
        winget_pkgs = Path(local_app) / "Microsoft" / "WinGet" / "Packages"
        if winget_pkgs.is_dir():
            for bin_dir in winget_pkgs.glob("Gyan.FFmpeg*/**/bin"):
                if bin_dir.is_dir():
                    dirs.append(bin_dir)

    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    choco_bin = Path(program_data) / "chocolatey" / "bin"
    if choco_bin.is_dir():
        dirs.append(choco_bin)

    for fixed in (
        Path(r"C:\ffmpeg\bin"),
        Path(r"C:\Program Files\ffmpeg\bin"),
        Path(r"C:\Program Files (x86)\ffmpeg\bin"),
    ):
        if fixed.is_dir():
            dirs.append(fixed)
    return dirs


def _find_binary(name: str, extra_dirs: list[Path]) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    exe_names = [f"{name}.exe", name] if os.name == "nt" else [name]
    for directory in extra_dirs:
        for exe in exe_names:
            candidate = directory / exe
            if candidate.is_file():
                return str(candidate)
    return None


@lru_cache(maxsize=1)
def resolve_toolchain() -> dict[str, str | None]:
    """Resolve ffmpeg, ffprobe, and JS runtime once and prepend ffmpeg's folder to PATH."""
    extra_dirs = _candidate_bin_dirs()
    ffmpeg_path = _find_binary("ffmpeg", extra_dirs)
    ffprobe_path = _find_binary("ffprobe", extra_dirs)

    if ffmpeg_path is None:
        try:
            import imageio_ffmpeg  # type: ignore

            bundled = imageio_ffmpeg.get_ffmpeg_exe()
            if bundled and Path(bundled).is_file():
                ffmpeg_path = bundled
        except Exception:
            pass

    ffmpeg_dir: str | None = None
    if ffmpeg_path:
        ffmpeg_dir = str(Path(ffmpeg_path).resolve().parent)
        current_path = os.environ.get("PATH", "")
        if ffmpeg_dir.lower() not in current_path.lower():
            os.environ["PATH"] = f"{ffmpeg_dir}{os.pathsep}{current_path}" if current_path else ffmpeg_dir

    # Also check common Node/Deno locations
    js_extra: list[Path] = []
    if os.name == "nt":
        for p in (
            Path(r"C:\Program Files\nodejs"),
            Path.home() / ".deno" / "bin",
        ):
            if p.is_dir():
                js_extra.append(p)

    deno_path = _find_binary("deno", js_extra)
    node_path = _find_binary("node", js_extra)

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
    yt_ver = None
    try:
        import yt_dlp.version

        yt_ver = getattr(yt_dlp.version, "__version__", None)
    except Exception:
        pass
    return {
        "ffmpeg_ok": bool(tc["ffmpeg"]),
        "ffmpeg_path": tc["ffmpeg"],
        "ffprobe_ok": bool(tc["ffprobe"]),
        "ffprobe_path": tc["ffprobe"],
        "js_runtime": tc["deno"] or tc["node"],
        "ytdlp_version": yt_ver,
    }


def friendly_missing_ffmpeg_message() -> str:
    """Plain-language instructions when ffmpeg is not installed."""
    return (
        "ffmpeg was not found on this PC. "
        "Install it with: winget install Gyan.FFmpeg, then restart your terminal and the app "
        "(or upload a WAV file)."
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
            "Check that ffmpeg is installed, restart the app, or upload a WAV file instead."
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

