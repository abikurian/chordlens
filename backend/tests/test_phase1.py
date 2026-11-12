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
    result = analyze_audio(wav_path, use_phase2=False, use_cache=False)

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


def test_phase1_long_track_with_drums_and_7ths(tmp_path: Path) -> None:
    """Verify >=90s track with drums + 7ths covers full duration and holds accuracy across thirds."""
    sr = 22050
    bpm = 108.0
    beat_dur = 60.0 / bpm
    n_bars = 48  # 48 * 4 = 192 beats = 106.67s (>= 90s)
    progression = [
        ("C", [130.81, 261.63, 329.63, 392.00]),
        ("G", [98.00, 196.00, 246.94, 293.66]),
        ("Am", [110.00, 220.00, 261.63, 329.63]),
        ("F", [87.31, 174.61, 220.00, 261.63]),
        ("Dm7", [146.83, 220.00, 261.63, 349.23]),
        ("G7", [98.00, 196.00, 246.94, 349.23]),
        ("C", [130.81, 261.63, 329.63, 392.00]),
        ("Cmaj7", [130.81, 261.63, 329.63, 392.00, 493.88]),
    ]

    bar_samples = int(round(4 * beat_dur * sr))
    beat_samples = int(round(beat_dur * sr))
    rng = np.random.default_rng(7)
    chunks: list[np.ndarray] = []

    for bar_i in range(n_bars):
        _, freqs = progression[bar_i % len(progression)]
        t = np.arange(bar_samples) / sr
        wave = 0.25 * np.sin(2 * np.pi * freqs[0] * t)
        for f in freqs[1:]:
            wave += 0.16 * np.sin(2 * np.pi * f * t)
        for b in range(4):
            idx = b * beat_samples
            if b in (0, 2):
                kt = np.arange(min(int(0.12 * sr), bar_samples - idx)) / sr
                kick = 0.55 * np.exp(-kt * 28) * np.sin(2 * np.pi * (110 * np.exp(-kt * 18) + 45) * kt)
                wave[idx : idx + len(kick)] += kick
            else:
                st = np.arange(min(int(0.09 * sr), bar_samples - idx)) / sr
                snare = 0.35 * np.exp(-st * 35) * rng.normal(0, 1, len(st))
                wave[idx : idx + len(snare)] += snare
        chunks.append(wave)

    audio = np.concatenate(chunks).astype(np.float32)
    audio /= np.max(np.abs(audio)) * 1.1
    wav_path = tmp_path / "long_drums_7ths.wav"
    sf.write(str(wav_path), audio, sr)

    result = analyze_audio(wav_path, use_phase2=False, use_cache=False)
    duration = result["duration"]
    assert duration >= 90.0
    assert result["chords"][-1]["end"] >= duration - 0.1
    assert result["beats"][-1] >= duration - 1.5

    bcs = result["beat_chords"]
    bar_acc: list[float] = []
    for bar_i in range(min(n_bars, len(bcs) // 4)):
        true_chord = progression[bar_i % len(progression)][0]
        preds = [bcs[bar_i * 4 + k]["chord"] for k in range(4)]
        bar_acc.append(sum(1 for c in preds if c == true_chord) / 4.0)

    third = len(bar_acc) // 3
    first_acc = float(np.mean(bar_acc[:third]))
    mid_acc = float(np.mean(bar_acc[third : 2 * third]))
    last_acc = float(np.mean(bar_acc[2 * third :]))

    assert first_acc >= 0.65
    assert mid_acc >= 0.65
    assert last_acc >= 0.65

