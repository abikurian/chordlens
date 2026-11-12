"""Phase 2 tests: BTC chord recognition, SHA-256 caching, and fallback behavior."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from backend.analyze import analyze_audio
from backend.btc_chord import format_mirex_chord, predict_chords_btc


def test_format_mirex_chord() -> None:
    assert format_mirex_chord("C:maj") == "C"
    assert format_mirex_chord("A:min") == "Am"
    assert format_mirex_chord("D:min7") == "Dm7"
    assert format_mirex_chord("C:maj7") == "Cmaj7"
    assert format_mirex_chord("G:7") == "G7"
    assert format_mirex_chord("N") == "N"


def test_btc_predict_synthetic() -> None:
    sr = 22050
    bpm = 100.0
    beat_dur = 60.0 / bpm
    progression = [
        ("C", [130.81, 261.63, 329.63, 392.00]),
        ("G", [98.00, 196.00, 246.94, 293.66]),
        ("Am", [110.00, 220.00, 261.63, 329.63]),
        ("F", [87.31, 174.61, 220.00, 261.63]),
    ]
    bar_samples = int(round(4 * beat_dur * sr))
    chunks = []
    for _, freqs in progression:
        t = np.arange(bar_samples) / sr
        wave = sum(
            0.20 * np.sin(2 * np.pi * f * t)
            + 0.08 * np.sin(2 * np.pi * 2 * f * t)
            + 0.04 * np.sin(2 * np.pi * 3 * f * t)
            for f in freqs
        )
        chunks.append(wave)
    audio = np.concatenate(chunks).astype(np.float32)
    duration = len(audio) / sr
    beat_times = np.arange(0.0, duration, beat_dur).tolist()[:16]

    beat_chords, chords = predict_chords_btc(audio, sr, beat_times, duration)
    assert len(beat_chords) == 16
    detected = {c["chord"] for c in chords}
    assert {"C", "G", "Am", "F"}.issubset(detected)


def test_phase2_cache_and_fallback(tmp_path: Path, monkeypatch) -> None:
    import backend.analyze as analyze_mod

    monkeypatch.setattr(analyze_mod, "CACHE_DIR", tmp_path / "cache")
    sr = 22050
    t = np.arange(int(3.0 * sr)) / sr
    wave = (0.25 * np.sin(2 * np.pi * 261.63 * t) + 0.25 * np.sin(2 * np.pi * 329.63 * t)).astype(np.float32)
    wav_path = tmp_path / "cache_test.wav"
    sf.write(str(wav_path), wave, sr)

    # Force fallback path so test runs quickly without Demucs
    with patch("backend.separate.separate_stems", side_effect=RuntimeError("mock demucs off")), \
         patch("backend.analyze._track_beats_beat_this", side_effect=RuntimeError("mock beat_this off")):
        res1 = analyze_audio(wav_path, use_phase2=True, use_cache=True)
        assert res1["cached"] is False
        assert "hpss" in res1["pipeline"]
        assert "btc" in res1["pipeline"]

        t0 = time.perf_counter()
        res2 = analyze_audio(wav_path, use_phase2=True, use_cache=True)
        elapsed = time.perf_counter() - t0
        assert res2["cached"] is True
        assert elapsed < 0.2
        assert res2["chords"] == res1["chords"]

