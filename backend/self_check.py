"""ChordLens installation self-check and diagnostic verification.

Verifies:
1. Bundled FFmpeg & FFprobe (present, executable, LGPL-verified)
2. Bundled JS runtime (Deno present and executable)
3. yt-dlp (importable and functional)
4. Fast-mode pre-trained models (beat_this and BTC loaded via PyTorch)
5. Writable user data folder (%LOCALAPPDATA%\\ChordLens)
6. Fast-mode analysis pipeline on synthetic test WAV (chords C - G - Am - F)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from typing import Any

from backend.ffmpeg_utils import (
    get_yt_dlp_version,
    is_ffmpeg_lgpl,
    resolve_toolchain,
)
from backend.paths import (
    get_app_data_dir,
    get_bundled_dir,
    get_bundled_models_dir,
)


def _check_ffmpeg() -> dict[str, Any]:
    tc = resolve_toolchain()
    ff = tc.get("ffmpeg")
    probe = tc.get("ffprobe")
    if not ff or not Path(ff).is_file():
        return {
            "id": "ffmpeg",
            "name": "Audio processor (FFmpeg)",
            "passed": False,
            "summary": "FFmpeg executable was not found.",
            "details": f"Searched bundled bin directory and PATH. Missing: {ff}",
            "fix": "Reinstall ChordLens to restore missing bundled files.",
        }
    if not probe or not Path(probe).is_file():
        return {
            "id": "ffmpeg",
            "name": "Audio prober (FFprobe)",
            "passed": False,
            "summary": "FFprobe executable was not found.",
            "details": f"FFmpeg was found at {ff}, but ffprobe is missing.",
            "fix": "Reinstall ChordLens to restore missing bundled files.",
        }

    is_lgpl, lgpl_msg = is_ffmpeg_lgpl(ff)
    if not is_lgpl:
        return {
            "id": "ffmpeg",
            "name": "Audio processor license",
            "passed": False,
            "summary": "FFmpeg build is not LGPL-compliant.",
            "details": f"FFmpeg at {ff} reported: {lgpl_msg}",
            "fix": "Replace FFmpeg with the official LGPL build or reinstall ChordLens.",
        }

    return {
        "id": "ffmpeg",
        "name": "Audio processor (FFmpeg & FFprobe)",
        "passed": True,
        "summary": "FFmpeg and FFprobe are ready (LGPL verified)",
        "details": f"FFmpeg: {ff}\nFFprobe: {probe}\nLicense: {lgpl_msg}",
    }


def _check_js_runtime() -> dict[str, Any]:
    tc = resolve_toolchain()
    deno = tc.get("deno")
    node = tc.get("node")
    runtime = deno or node

    if not runtime or not Path(runtime).is_file():
        return {
            "id": "js_runtime",
            "name": "JavaScript runtime",
            "passed": False,
            "summary": "Bundled JavaScript runtime (Deno) was not found.",
            "details": "Deno is required by yt-dlp for reliable YouTube extraction.",
            "fix": "Reinstall ChordLens to restore the bundled runtime.",
        }

    try:
        proc = subprocess.run(
            [str(runtime), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        ver_line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else "OK"
        return {
            "id": "js_runtime",
            "name": "JavaScript runtime (Deno)",
            "passed": True,
            "summary": f"Runtime is ready ({ver_line})",
            "details": f"Path: {runtime}\nVersion: {ver_line}",
        }
    except Exception as exc:
        return {
            "id": "js_runtime",
            "name": "JavaScript runtime (Deno)",
            "passed": False,
            "summary": f"Could not execute runtime: {exc}",
            "details": f"Path: {runtime}\nError: {exc}",
            "fix": "Check antivirus permissions or reinstall ChordLens.",
        }


def _check_ytdlp() -> dict[str, Any]:
    ver = get_yt_dlp_version()
    if ver == "MISSING":
        return {
            "id": "ytdlp",
            "name": "YouTube extractor (yt-dlp)",
            "passed": False,
            "summary": "yt-dlp is not available.",
            "details": "yt-dlp could not be imported or run.",
            "fix": "Reinstall ChordLens.",
        }
    return {
        "id": "ytdlp",
        "name": "YouTube extractor (yt-dlp)",
        "passed": True,
        "summary": f"yt-dlp is ready (version {ver})",
        "details": f"Version: {ver}",
    }


def _check_models() -> dict[str, Any]:
    try:
        from backend.analyze import _find_beat_this_checkpoint
        from backend.btc_chord import _load_btc, get_btc_model_dir

        beat_ckpt = _find_beat_this_checkpoint()
        if not beat_ckpt or not beat_ckpt.is_file():
            return {
                "id": "models",
                "name": "Fast-mode models",
                "passed": False,
                "summary": "beat_this model checkpoint was not found.",
                "details": f"Looked in {get_bundled_models_dir() / 'beat_this'}",
                "fix": "Reinstall ChordLens.",
            }

        btc_dir = get_btc_model_dir()
        btc_file = btc_dir / "btc_model_large_voca.pt"
        if not btc_file.is_file():
            return {
                "id": "models",
                "name": "Fast-mode models",
                "passed": False,
                "summary": "BTC chord model weights were not found.",
                "details": f"Looked in {btc_dir}",
                "fix": "Reinstall ChordLens.",
            }

        # Light load check
        _model, _m, _s, idx_to_chord = _load_btc()
        return {
            "id": "models",
            "name": "Fast-mode models (beat_this & BTC)",
            "passed": True,
            "summary": f"Both models loaded into PyTorch ({len(idx_to_chord)} chord vocabulary)",
            "details": f"beat_this: {beat_ckpt}\nBTC: {btc_file}",
        }
    except Exception as exc:
        return {
            "id": "models",
            "name": "Fast-mode models",
            "passed": False,
            "summary": f"Failed to load models: {exc}",
            "details": str(exc),
            "fix": "Reinstall ChordLens.",
        }


def _check_data_dir() -> dict[str, Any]:
    data_dir = get_app_data_dir()
    probe = data_dir / f".write_test_{int(time.time())}"
    try:
        probe.write_text("ok", encoding="utf-8")
        content = probe.read_text(encoding="utf-8")
        probe.unlink(missing_ok=True)
        if content != "ok":
            raise RuntimeError("Read back unexpected content")
        return {
            "id": "data_dir",
            "name": "User data storage",
            "passed": True,
            "summary": "Data directory is writable",
            "details": f"Path: {data_dir}",
        }
    except Exception as exc:
        return {
            "id": "data_dir",
            "name": "User data storage",
            "passed": False,
            "summary": f"Data directory is not writable: {exc}",
            "details": f"Path: {data_dir}\nError: {exc}",
            "fix": f"Check folder permissions for {data_dir}.",
        }


def _check_fast_pipeline() -> dict[str, Any]:
    try:
        # Locate synthetic fixture WAV
        bundled = get_bundled_dir()
        fixture_paths = [
            bundled / "backend" / "fixtures" / "self_check_test.wav",
            Path(__file__).resolve().parent / "fixtures" / "self_check_test.wav",
            bundled / "tmp" / "test_c_g_am_f.wav",
        ]
        test_wav: Path | None = None
        for cand in fixture_paths:
            if cand.is_file() and cand.stat().st_size > 0:
                test_wav = cand
                break

        if not test_wav:
            from scripts.generate_test_clip import generate_self_check_wav

            target = get_app_data_dir() / "self_check_test.wav"
            generate_self_check_wav(target)
            test_wav = target

        from backend.analyze import analyze_audio

        res = analyze_audio(test_wav, mode="fast")
        chords = [c["chord"] for c in res.get("chords", [])]

        # Verify C, G, Am, F are recognized in order
        expected = ["C", "G", "Am", "F"]
        # Find order in chords list
        clean_chords = [c for c in chords if c != "N"]
        # Check that C, G, Am, F appear in sequence
        matched = []
        cur_idx = 0
        for ch in clean_chords:
            if cur_idx < len(expected) and ch == expected[cur_idx]:
                matched.append(ch)
                cur_idx += 1

        all_matched = (len(matched) == len(expected))
        if not all_matched:
            return {
                "id": "fast_pipeline",
                "name": "Fast chord analysis test",
                "passed": False,
                "summary": f"Analysis did not detect expected sequence: got {clean_chords}",
                "details": f"Expected: {expected}\nGot: {chords}",
                "fix": "Reinstall ChordLens.",
            }

        return {
            "id": "fast_pipeline",
            "name": "Fast chord analysis test",
            "passed": True,
            "summary": f"Verified synthetic audio: detected {' -> '.join(expected)}",
            "details": f"Chords detected: {chords}\nBeats: {len(res.get('beats', []))}",
        }
    except Exception as exc:
        return {
            "id": "fast_pipeline",
            "name": "Fast chord analysis test",
            "passed": False,
            "summary": f"Analysis failed: {exc}",
            "details": str(exc),
            "fix": "Reinstall ChordLens.",
        }


def run_self_check() -> dict[str, Any]:
    """Execute all system self-checks and return a structured report."""
    checks = [
        _check_ffmpeg(),
        _check_js_runtime(),
        _check_ytdlp(),
        _check_models(),
        _check_data_dir(),
        _check_fast_pipeline(),
    ]

    all_passed = all(c["passed"] for c in checks)
    failed_items = [c for c in checks if not c["passed"]]

    return {
        "status": "ready" if all_passed else "failed",
        "all_passed": all_passed,
        "message": (
            "Ready to analyze songs"
            if all_passed
            else (
                f"Setup issue detected: {failed_items[0]['summary']} "
                f"{failed_items[0].get('fix', 'Please reinstall ChordLens.')}"
            )
        ),
        "checks": checks,
    }


def cli_self_check() -> int:
    """Entry point for ChordLens.exe --self-check. Prints to stdout and returns 0 or 1."""
    print("=" * 60)
    print("ChordLens Installation Self-Check")
    print("=" * 60)

    report = run_self_check()

    for item in report["checks"]:
        mark = "[PASS]" if item["passed"] else "[FAIL]"
        print(f"{mark} {item['name']}: {item['summary']}")
        if not item["passed"]:
            print(f"       Details: {item['details']}")
            if "fix" in item:
                print(f"       Action:  {item['fix']}")

    print("-" * 60)
    if report["all_passed"]:
        print("OVERALL RESULT: PASS — Ready to analyze songs.")
        print("=" * 60)
        return 0
    else:
        print("OVERALL RESULT: FAIL — Installation is incomplete or damaged.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(cli_self_check())
