"""Phase 1 audio analysis pipeline using librosa with tuning, bass weighting, and margin confidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import librosa
import numpy as np
import scipy.ndimage

NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# (suffix, intervals, root_weight, parsimony_penalty)
CHORD_QUALITIES: list[tuple[str, tuple[int, ...], float]] = [
    ("", (0, 4, 7), 0.0),
    ("m", (0, 3, 7), 0.0),
    ("7", (0, 4, 7, 10), 0.02),
    ("maj7", (0, 4, 7, 11), 0.02),
    ("m7", (0, 3, 7, 10), 0.02),
    ("sus2", (0, 2, 7), 0.03),
    ("sus4", (0, 5, 7), 0.03),
]

# Minimum margin by which a 7th or sus chord must beat its base triad
EXTENSION_MIN_MARGIN = 0.045

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


def build_chord_templates() -> tuple[list[str], np.ndarray, np.ndarray, list[int]]:
    """Build L2-normalized, root-weighted 12-bin chroma templates."""
    labels: list[str] = []
    templates: list[np.ndarray] = []
    penalties: list[float] = []
    roots: list[int] = []

    for root_idx, root_name in enumerate(NOTE_NAMES):
        for suffix, intervals, penalty in CHORD_QUALITIES:
            vec = np.zeros(12, dtype=np.float64)
            for iv in intervals:
                vec[(root_idx + iv) % 12] = 1.0
            # Emphasize root and fifth for stronger root stability
            vec[root_idx] = 1.5
            vec[(root_idx + 7) % 12] = 1.1
            vec /= np.linalg.norm(vec)
            labels.append(f"{root_name}{suffix}")
            templates.append(vec)
            penalties.append(penalty)
            roots.append(root_idx)

    # No-chord template (used for genuine silence only)
    nc_vec = np.ones(12, dtype=np.float64) / np.sqrt(12.0)
    labels.append("N")
    templates.append(nc_vec)
    penalties.append(0.5)
    roots.append(-1)

    return labels, np.vstack(templates), np.array(penalties, dtype=np.float64), roots


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


def _diatonic_chords_for_key(key: str) -> set[str]:
    """Return the set of diatonic triads and 7th chords for a detected key."""
    parts = key.split()
    if len(parts) != 2 or parts[0] not in NOTE_NAMES:
        return set()
    tonic = NOTE_NAMES.index(parts[0])
    mode = parts[1].lower()

    if mode == "major":
        degrees = [
            (0, ("", "maj7")),
            (2, ("m", "m7")),
            (4, ("m", "m7")),
            (5, ("", "maj7")),
            (7, ("", "7")),
            (9, ("m", "m7")),
        ]
    else:
        degrees = [
            (0, ("m", "m7")),
            (3, ("", "maj7")),
            (5, ("m", "m7")),
            (7, ("m", "", "7")),
            (8, ("", "maj7")),
            (10, ("", "7")),
        ]

    diatonic: set[str] = set()
    for offset, suffixes in degrees:
        root = NOTE_NAMES[(tonic + offset) % 12]
        for s in suffixes:
            diatonic.add(f"{root}{s}")
    return diatonic


def _build_transition_matrix(n_states: int, self_prob: float = 0.85) -> np.ndarray:
    """Create an ergodic HMM transition matrix favoring chord continuity."""
    off_prob = (1.0 - self_prob) / max(1, n_states - 1)
    mat = np.full((n_states, n_states), off_prob, dtype=np.float64)
    np.fill_diagonal(mat, self_prob)
    return mat


def _softmax(x: np.ndarray, temperature: float = 0.08) -> np.ndarray:
    scaled = (x - np.max(x, axis=0, keepdims=True)) / temperature
    exp_x = np.exp(scaled)
    return exp_x / np.sum(exp_x, axis=0, keepdims=True)


def _sync_beats_exact(feature: np.ndarray, beat_frames: np.ndarray) -> np.ndarray:
    """Synchronize frame-level features to exact [beat_i, beat_{i+1}) intervals."""
    n_frames = feature.shape[1]
    clipped = np.clip(beat_frames, 0, max(0, n_frames - 1))
    synced = librosa.util.sync(feature, clipped, aggregate=np.median)
    n_beats = len(clipped)
    # librosa.util.sync splits at [0, b0, b1, ..., b_{k-1}, N], producing k+1 columns.
    # Column 0 is [0, b0); columns 1..k are [b0, b1) .. [b_{k-1}, N).
    if synced.shape[1] >= n_beats + 1:
        return synced[:, 1 : n_beats + 1]
    return synced[:, :n_beats]


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

    # Harmonic/percussive separation
    y_harm, y_perc = librosa.effects.hpss(y)

    # Beat tracking on percussive onset envelope with tempo prior and tightness
    beat_source = y_perc if np.max(np.abs(y_perc)) > 1e-4 else y
    onset_env = librosa.onset.onset_strength(y=beat_source, sr=sr)
    tempo_est_arr = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
    start_bpm = float(np.atleast_1d(tempo_est_arr)[0]) if tempo_est_arr is not None else 120.0
    if start_bpm <= 0 or np.isnan(start_bpm):
        start_bpm = 120.0

    tempo_raw, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env,
        sr=sr,
        start_bpm=start_bpm,
        tightness=120,
        trim=False,
    )
    tempo = float(np.atleast_1d(tempo_raw)[0]) if tempo_raw is not None else start_bpm
    if tempo <= 0 or np.isnan(tempo):
        tempo = start_bpm

    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    # Ensure we have a usable beat grid even on beatless clips
    if len(beat_times) < 2:
        step = 60.0 / tempo
        beat_times = np.arange(0.0, max(duration, step), step).tolist()
        beat_frames = librosa.time_to_frames(np.array(beat_times), sr=sr)

    # Tuning-corrected CQT chroma + temporal median smoothing before beat sync
    tuning = float(librosa.estimate_tuning(y=y_harm, sr=sr))
    chroma = librosa.feature.chroma_cqt(
        y=y_harm, sr=sr, tuning=tuning, bins_per_octave=36
    )
    chroma = scipy.ndimage.median_filter(chroma, size=(1, 9))

    # Bass-range CQT chroma (C2-B3, 2 octaves) for root-note weighting
    bass_chroma = librosa.feature.chroma_cqt(
        y=y_harm,
        sr=sr,
        tuning=tuning,
        fmin=librosa.note_to_hz("C2"),
        n_octaves=2,
        bins_per_octave=36,
    )
    bass_chroma = scipy.ndimage.median_filter(bass_chroma, size=(1, 9))

    beat_chroma = _sync_beats_exact(chroma, beat_frames)
    beat_bass = _sync_beats_exact(bass_chroma, beat_frames)

    n_beats = min(len(beat_times), beat_chroma.shape[1])
    beat_times = beat_times[:n_beats]
    beat_chroma = beat_chroma[:, :n_beats]
    beat_bass = beat_bass[:, :n_beats]

    # Normalize chroma and bass chroma per beat
    norms = np.linalg.norm(beat_chroma, axis=0, keepdims=True)
    beat_energy = norms.squeeze(0)
    norm_chroma = beat_chroma / np.where(norms > 1e-8, norms, 1.0)

    bass_norms = np.linalg.norm(beat_bass, axis=0, keepdims=True)
    norm_bass = beat_bass / np.where(bass_norms > 1e-8, bass_norms, 1.0)

    # Key detection & diatonic chord prior
    key = detect_key_krumhansl(np.mean(chroma, axis=1))
    diatonic = _diatonic_chords_for_key(key)

    labels, templates, penalties, roots = build_chord_templates()
    scores = templates @ norm_chroma - penalties[:, np.newaxis]

    # Add bass-root boost and diatonic key bias
    for state_idx, (label, root_idx) in enumerate(zip(labels, roots)):
        if root_idx >= 0:
            scores[state_idx] += 0.22 * norm_bass[root_idx]
        if label in diatonic:
            scores[state_idx] += 0.04

    # Save raw scores before extension gating so confidence reflects true ambiguity
    raw_scores = scores.copy()

    # Gate 7th and sus chords unless they beat their base triad by a clear margin
    n_qualities = len(CHORD_QUALITIES)
    for r in range(len(NOTE_NAMES)):
        base = r * n_qualities
        maj_idx, min_idx = base, base + 1
        scores[base + 2] = np.where(
            scores[base + 2] - scores[maj_idx] >= EXTENSION_MIN_MARGIN,
            scores[base + 2],
            scores[maj_idx] - 0.05,
        )
        scores[base + 3] = np.where(
            scores[base + 3] - scores[maj_idx] >= EXTENSION_MIN_MARGIN,
            scores[base + 3],
            scores[maj_idx] - 0.05,
        )
        scores[base + 4] = np.where(
            scores[base + 4] - scores[min_idx] >= EXTENSION_MIN_MARGIN,
            scores[base + 4],
            scores[min_idx] - 0.05,
        )
        best_triad = np.maximum(scores[maj_idx], scores[min_idx])
        for sus_offset in (5, 6):
            scores[base + sus_offset] = np.where(
                scores[base + sus_offset] - best_triad >= EXTENSION_MIN_MARGIN,
                scores[base + sus_offset],
                best_triad - 0.05,
            )

    # Keep "N" for genuine silence only
    silence_thresh = float(np.median(beat_energy)) * 0.03 + 1e-6
    silent_mask = beat_energy < silence_thresh
    scores[-1, silent_mask] = 1.0
    scores[-1, ~silent_mask] = -1.5

    probs = _softmax(scores)
    transition = _build_transition_matrix(len(labels), self_prob=0.85)
    path_states = librosa.sequence.viterbi(probs, transition)

    # Margin-based confidence per beat (stationary over time, independent of template count)
    beat_chords: list[dict[str, Any]] = []
    for idx in range(n_beats):
        start_t = float(beat_times[idx])
        end_t = float(beat_times[idx + 1]) if idx + 1 < n_beats else duration
        state_idx = int(path_states[idx])
        chord_label = labels[state_idx]

        col = raw_scores[:, idx]
        chosen_score = float(col[state_idx])
        # Compare against the strongest competing state in raw_scores
        other_scores = np.delete(col, state_idx)
        runner_up = float(np.max(other_scores)) if len(other_scores) > 0 else 0.0
        margin = chosen_score - runner_up
        conf = float(1.0 / (1.0 + np.exp(-margin / 0.12)))
        conf = float(np.clip(conf, 0.0, 1.0))

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

    downbeats = [round(float(beat_times[i]), 3) for i in range(0, len(beat_times), 4)]

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
