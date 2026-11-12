"""ChordLens storage paths and data directory management.

All writable data (cache, models, uploads, logs) lives under:
  %LOCALAPPDATA%\\ChordLens
Never next to the exe or under Program Files.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def get_app_data_dir() -> Path:
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
    _d.mkdir(parents=True, exist_ok=True)


def get_frontend_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend"
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
    CACHE_YT_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return removed
