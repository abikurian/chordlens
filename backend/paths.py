"""ChordLens storage paths and data directory management.

All writable data (cache, uploads, logs, on-demand downloaded models) lives under:
  %LOCALAPPDATA%\\ChordLens (or ~/.chordlens on non-Windows)
Never next to the exe or under Program Files.

Read-only bundled assets (bin, models, frontend) resolve from sys._MEIPASS when frozen,
or from the repository root when running from source.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def get_app_data_dir() -> Path:
    """Return the writable user data directory (%LOCALAPPDATA%\\ChordLens)."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data) / "ChordLens"
    else:
        base = Path.home() / ".chordlens"
    base.mkdir(parents=True, exist_ok=True)
    return base


DATA_DIR = get_app_data_dir()
MODELS_DIR = DATA_DIR / "models"
CACHE_DIR = DATA_DIR / "cache"
CACHE_YT_DIR = CACHE_DIR / "youtube"
UPLOAD_DIR = DATA_DIR / "uploads"
LOGS_DIR = DATA_DIR / "logs"

for _d in (MODELS_DIR, CACHE_DIR, CACHE_YT_DIR, UPLOAD_DIR, LOGS_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def get_bundled_dir() -> Path:
    """Return the base directory for bundled read-only assets."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bin_dir() -> Path:
    """Return directory containing bundled binaries (ffmpeg, ffprobe, deno)."""
    bundled = get_bundled_dir() / "bin"
    if bundled.is_dir():
        return bundled
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for cand in (exe_dir / "bin", exe_dir / "_internal" / "bin"):
            if cand.is_dir():
                return cand
    return Path(__file__).resolve().parent.parent / "bin"


def get_bundled_models_dir() -> Path:
    """Return directory containing bundled models (beat_this, btc-chord)."""
    bundled = get_bundled_dir() / "models"
    if bundled.is_dir():
        return bundled
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for cand in (exe_dir / "models", exe_dir / "_internal" / "models"):
            if cand.is_dir():
                return cand
    return Path(__file__).resolve().parent.parent / "models"


def get_frontend_dir() -> Path:
    """Return directory containing frontend web assets."""
    bundled = get_bundled_dir() / "frontend"
    if bundled.is_dir():
        return bundled
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for cand in (exe_dir / "frontend", exe_dir / "_internal" / "frontend"):
            if cand.is_dir():
                return cand
    return Path(__file__).resolve().parent.parent / "frontend"


def clear_app_cache() -> int:
    """Clear analysis cache and temporary uploads. Returns number of removed items."""
    removed = 0
    for target in (CACHE_DIR, UPLOAD_DIR):
        if target.exists():
            for item in target.iterdir():
                try:
                    if item.is_file() or item.is_symlink():
                        item.unlink(missing_ok=True)
                        removed += 1
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                        removed += 1
                except OSError:
                    pass
    try:
        CACHE_YT_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return removed
