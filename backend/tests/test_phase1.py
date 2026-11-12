"""Phase 1 smoke tests for ChordLens baseline pipeline and API."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from backend.analyze import analyze_audio
from backend.main import app


def _synth_chord_progression(out_path: Path, bpm: float = 100.0) -> Path:
    """Synthesize a clean 4-bar C - G - Am - F progression with click pulses."""
    sr = 22050
    beat_dur = 60.0 / bpm
    progression = [
        ("C", [261.63, 329.63, 392.00]),
        ("G", [196.00, 246.94, 293.66]),
        ("Am", [220.00, 261.63, 329.63]),
        ("F", [174.61, 220.00, 261.63]),
    ]

    bar_samples = int(4 * beat_dur * sr)
    beat_samples = int(beat_dur * sr)
    chunks: list[np.ndarray] = []

    for _, freqs in progression:
        t = np.arange(bar_samples) / sr
        chord_wave = sum(0.22 * np.sin(2 * np.pi * f * t) for f in freqs)
        # Add subtle percussive click on each beat so beat_track locks onto BPM
        for b in range(4):
            idx = b * beat_samples
            click_len = min(int(0.025 * sr), bar_samples - idx)
            ct = np.arange(click_len) / sr
            click = 0.35 * np.exp(-ct * 120.0) * np.sin(2 * np.pi * 1000.0 * ct)
            chord_wave[idx : idx + click_len] += click
        chunks.append(chord_wave)

    audio = np.concatenate(chunks).astype(np.float32)
    sf.write(str(out_path), audio, sr)
    return out_path


def test_phase1_analyze_synthetic(tmp_path: Path) -> None:
    wav_path = _synth_chord_progression(tmp_path / "cgamf_100bpm.wav", bpm=100.0)
    result = analyze_audio(wav_path)

    assert result["pipeline"] == "phase1-librosa"
    assert 90.0 <= result["tempo"] <= 110.0
    assert result["key"] in {"C major", "A minor"}
    assert len(result["beat_chords"]) >= 12
    detected = {seg["chord"] for seg in result["chords"]}
    assert {"C", "G", "Am", "F"}.issubset(detected)


def test_api_health_and_upload(tmp_path: Path) -> None:
    wav_path = _synth_chord_progression(tmp_path / "upload_test.wav", bpm=100.0)
    client = TestClient(app)

    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"

    with wav_path.open("rb") as f:
        res = client.post("/api/analyze", files={"file": ("upload_test.wav", f, "audio/wav")})
    assert res.status_code == 200
    data = res.json()
    assert data["audio_url"].startswith("/api/audio/")
    assert len(data["beat_chords"]) >= 12


def test_api_invalid_youtube_url() -> None:
    client = TestClient(app)
    res = client.post("/api/analyze-url", json={"url": "https://example.com/not-youtube"})
    assert res.status_code == 400

