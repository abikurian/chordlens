"""Diagnostic logging and safe JSON utilities for ChordLens."""

from __future__ import annotations

import datetime
import json
import traceback
from typing import Any
from backend.paths import LOGS_DIR


def append_to_app_log(msg: str) -> None:
    """Append a timestamped message to %LOCALAPPDATA%\\ChordLens\\logs\\chordlens.log."""
    try:
        log_file = LOGS_DIR / "chordlens.log"
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def safe_json_loads(
    text: str,
    context: str = "unknown",
    allow_fallback: bool = False,
    fallback_value: Any = None,
) -> Any:
    """Parse JSON with automatic recovery and detailed diagnostic failure logging.

    If parsing fails, logs the first 300 characters, code location, and traceback
    to chordlens.log. If allow_fallback is True, returns fallback_value; otherwise
    raises a plain ValueError with no leaked Python traceback.
    """
    clean_text = text.strip() if text else ""
    if not clean_text:
        if allow_fallback:
            return fallback_value
        raise ValueError(f"No data received at {context}.")

    try:
        return json.loads(clean_text)
    except Exception as primary_exc:
        # Recovery attempt: text may contain leading or trailing warnings around JSON
        if "{" in clean_text and "}" in clean_text:
            start_idx = clean_text.find("{")
            end_idx = clean_text.rfind("}") + 1
            if start_idx < end_idx:
                try:
                    return json.loads(clean_text[start_idx:end_idx])
                except Exception:
                    pass

        # Diagnostic logging of the failure
        snippet = clean_text[:300]
        tb = traceback.format_exc()
        append_to_app_log(
            f"[JSON ERROR] Failed to parse JSON at {context}\n"
            f"  Snippet (first 300 chars): {snippet!r}\n"
            f"  Traceback:\n{tb}"
        )

        if allow_fallback:
            return fallback_value
        raise ValueError(f"Could not read data from {context}.") from primary_exc


def get_recent_logs(max_lines: int = 50) -> str:
    """Return the last max_lines from the app log file."""
    try:
        log_file = LOGS_DIR / "chordlens.log"
        if not log_file.exists():
            return "Log file is empty or not yet created."
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])
    except Exception as exc:
        return f"Could not read log file: {exc}"


def log_startup_toolchain() -> None:
    """Print and log detected helper tools at startup."""
    try:
        from backend.ffmpeg_utils import get_system_status
        status = get_system_status()
        ff_str = f"OK ({status['ffmpeg_path']})" if status.get("ffmpeg_ok") else "MISSING"
        ffprobe_str = f"OK ({status['ffprobe_path']})" if status.get("ffprobe_ok") else "MISSING"
        js_str = f"{status.get('js_runtime') or 'none'} ({status.get('js_runtime_path') or 'none'})"
        yt_str = status.get("ytdlp_version") or "unknown"
        lines = [
            f"[ChordLens startup] ffmpeg: {ff_str}",
            f"[ChordLens startup] ffprobe: {ffprobe_str}",
            f"[ChordLens startup] js_runtime: {js_str}",
            f"[ChordLens startup] yt-dlp: {yt_str}",
        ]
        for l in lines:
            print(l)
            append_to_app_log(l)
    except Exception as exc:
        append_to_app_log(f"[ChordLens startup] toolchain log failed: {exc}")
