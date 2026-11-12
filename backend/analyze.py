"""Phase 1 baseline audio analysis pipeline using librosa."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import librosa
import numpy as np

NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# Intervals (semitones from root) and a mild parsimony penalty for 4-note chords
# so clean triads are not over-predicted as 7th chords.
CHORD_QUALITIES: list[tuple[str, tuple[int, ...], float]] = [
    ("", (0, 4, 7), 0.0),
    ("m", (0, 3, 7), 0.0),
    ("7", (0, 4, 7, 10), 0.04),
    ("maj7", (0, 4, 7, 11), 0.04),
    ("m7", (0, 3, 7, 10), 0.04),
    ("sus2", (0, 2, 7), 0.03),
    ("sus4", (0, 5, 7), 0.03),
]

# Krumhansl-Schmuckler key-finding profiles
KRUMHANSL_MAJOR = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float64,
)
KRUMHANSL_MINOR = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float64,
)

LOW_CONFIDENCE_THRESHOLD = 0.55


def build_chord_templates() -> tuple[list[str], np.ndarray, np.ndarray]:
    """Build L2-normalized 12-bin chroma templates and parsimony penalties."""
    labels: list[str] = []
    templates: list[np.ndarray] = []
    penalties: list[float] = []

    for root_idx, root_name in enumerate(NOTE_NAMES):
        for suffix, intervals, penalty in CHORD_QUALITIES:
            vec = np.zeros(12, dtype=np.float64)
            for iv in intervals:
                vec[(root_idx + iv) % 12] = 1.0
            # Slightly emphasize the root pitch class
            vec[root_idx] = 1.2
            vec /= np.linalg.norm(vec)
            labels.append(f"{root_name}{suffix}")
            templates.append(vec)
            penalties.append(penalty)

    # No-chord template (uniform low-contrast)
    nc_vec = np.ones(12, dtype=np.float64) / np.sqrt(12.0)
    labels.append("N")
    templates.append(nc_vec)
    penalties.append(0.12)

    return labels, np.vstack(templates), np.array(penalties, dtype=np.float64)


def detect_key_krumhansl(chroma_mean: np.ndarray) -> str:
    """Estimate musical key using Krumhansl-Schmuckler pitch-class profiles."""
    if np.allclose(chroma_mean, 0):
        return "Unknown"

    best_score = -np.inf
    best_key = "C major"
    for shift, name in enumerate(NOTE_NAMES):
        maj_profile = np.roll(KRUMHANSL_MAJOR, shift)
        min_profile = np.roll(KRUMHANSL_MINOR, shift)

        maj_corr = float(np.corrcoef(chroma_mean, maj_profile)[0, 1])
        min_corr = float(np.corrcoef(chroma_mean, min_profile)[0, 1])

        if maj_corr > best_score:
            best_score = maj_corr
            best_key = f"{name} major"
        if min_corr > best_score:
            best_score = min_corr
            best_key = f"{name} minor"

    return best_key


def _build_transition_matrix(n_states: int, self_prob: float = 0.82) -> np.ndarray:
    """Create an ergodic HMM transition matrix favoring chord continuity."""
    off_prob = (1.0 - self_prob) / max(1, n_states - 1)
    mat = np.full((n_states, n_states), off_prob, dtype=np.float64)
    np.fill_diagonal(mat, self_prob)
    return mat


def _softmax(x: np.ndarray, temperature: float = 0.08) -> np.ndarray:
    scaled = (x - np.max(x, axis=0, keepdims=True)) / temperature
    exp_x = np.exp(scaled)
    return exp_x / np.sum(exp_x, axis=0, keepdims=True)


def analyze_audio(file_path: str | Path) -> dict[str, Any]:
    """Run Phase 1 librosa analysis: tempo, beats, key, and Viterbi-smoothed chords."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    sr = 22050
    y, sr = librosa.load(str(path), sr=sr, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    if duration < 0.5 or np.max(np.abs(y)) < 1e-6:
        raise ValueError("The audio file appears to be empty or silent.")

    # Separate harmonic and percussive components
    y_harm, y_perc = librosa.effects.hpss(y)

    # Beat tracking on percussive signal (fall back to full mix if percussive is near-silent)
    beat_source = y_perc if np.max(np.abs(y_perc)) > 1e-4 else y
    tempo_raw, beat_frames = librosa.beat.beat_track(y=beat_source, sr=sr, trim=False)
    tempo = float(np.atleast_1d(tempo_raw)[0]) if tempo_raw is not None else 120.0
    if tempo <= 0 or np.isnan(tempo):
        tempo = 120.0

    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    # Ensure we have a usable beat grid even on very short or beatless clips
    if len(beat_times) < 2:
        step = 60.0 / tempo
        beat_times = np.arange(0.0, max(duration, step), step).tolist()
        beat_frames = librosa.time_to_frames(np.array(beat_times), sr=sr)

    # Beat-synchronous CQT chroma on the harmonic stem
    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr, bins_per_octave=36)
    beat_frames_clipped = np.clip(beat_frames, 0, chroma.shape[1] - 1)
    beat_chroma = librosa.util.sync(chroma, beat_frames_clipped, aggregate=np.median)

    # sync() returns shape (12, len(beat_frames) + 1) when frames don't start at 0 / end at N;
    # slice to match the exact number of beat intervals.
    n_beats = len(beat_times)
    if beat_chroma.shape[1] > n_beats:
        beat_chroma = beat_chroma[:, :n_beats]
    elif beat_chroma.shape[1] < n_beats:
        n_beats = beat_chroma.shape[1]
        beat_times = beat_times[:n_beats]

    # Normalize each beat's chroma vector
    norms = np.linalg.norm(beat_chroma, axis=0, keepdims=True)
    beat_energy = norms.squeeze(0)
    safe_norms = np.where(norms > 1e-8, norms, 1.0)
    norm_chroma = beat_chroma / safe_norms

    # Template matching
    labels, templates, penalties = build_chord_templates()
    # Cosine similarity: (n_states, 12) @ (12, n_beats) -> (n_states, n_beats)
    scores = templates @ norm_chroma - penalties[:, np.newaxis]

    # Mark near-silent beats strongly toward "N" (last state)
    silent_mask = beat_energy < (np.median(beat_energy) * 0.08 + 1e-6)
    scores[-1, silent_mask] += 0.35

    probs = _softmax(scores)
    transition = _build_transition_matrix(len(labels), self_prob=0.82)
    path_states = librosa.sequence.viterbi(probs, transition)

    # Confidence per beat: probability of chosen state, scaled cleanly
    beat_chords: list[dict[str, Any]] = []
    for idx in range(n_beats):
        start_t = float(beat_times[idx])
        end_t = float(beat_times[idx + 1]) if idx + 1 < n_beats else duration
        state_idx = int(path_states[idx])
        chord_label = labels[state_idx]
        conf = float(np.clip(probs[state_idx, idx], 0.0, 1.0))
        beat_chords.append(
            {
                "beat_index": idx,
                "start": round(start_t, 3),
                "end": round(max(end_t, start_t), 3),
                "chord": chord_label,
                "confidence": round(conf, 3),
                "low_confidence": conf < LOW_CONFIDENCE_THRESHOLD,
            }
        )

    # Merge consecutive identical chords into timeline segments
    chords: list[dict[str, Any]] = []
    for item in beat_chords:
        if chords and chords[-1]["chord"] == item["chord"]:
            prev = chords[-1]
            prev["end"] = item["end"]
            prev["beat_end"] = item["beat_index"]
            prev["_confs"].append(item["confidence"])
            avg_c = float(np.mean(prev["_confs"]))
            prev["confidence"] = round(avg_c, 3)
            prev["low_confidence"] = avg_c < LOW_CONFIDENCE_THRESHOLD
        else:
            chords.append(
                {
                    "start": item["start"],
                    "end": item["end"],
                    "beat_start": item["beat_index"],
                    "beat_end": item["beat_index"],
                    "chord": item["chord"],
                    "confidence": item["confidence"],
                    "low_confidence": item["low_confidence"],
                    "_confs": [item["confidence"]],
                }
            )
    for seg in chords:
        seg.pop("_confs", None)

    # Phase 1: assume 4/4 downbeats every 4 beats
    downbeats = [round(float(beat_times[i]), 3) for i in range(0, len(beat_times), 4)]
    key = detect_key_krumhansl(np.mean(chroma, axis=1))

    return {
        "duration": round(duration, 3),
        "tempo": round(tempo, 1),
        "key": key,
        "time_signature": "4/4",
        "beats": [round(float(t), 3) for t in beat_times],
        "downbeats": downbeats,
        "chords": chords,
        "beat_chords": beat_chords,
        "pipeline": "phase1-librosa",
    }

