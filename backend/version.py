"""Single source of application version and Windows metadata."""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "ChordLens"
APP_DESCRIPTION = "ChordLens - Chord & Beat Analyzer"
COMPANY_NAME = "Abi Kurian Varghese"
COPYRIGHT = "Copyright (c) 2026 Abi Kurian Varghese"


def _version_file_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "VERSION"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent / "VERSION"


def get_version() -> str:
    """Return semantic version string from VERSION file (e.g. '0.1.0')."""
    try:
        text = _version_file_path().read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    return "0.1.0"


def get_version_tuple() -> tuple[int, int, int, int]:
    """Return 4-part Windows version tuple (major, minor, patch, 0)."""
    parts = [int(p) if p.isdigit() else 0 for p in get_version().split(".")[:3]]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2], 0)
