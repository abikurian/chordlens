"""Audio analysis pipeline: Phase 2 (Demucs + beat_this + BTC) with Phase 1 librosa fallback and SHA-256 caching."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import scipy.ndimage

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "cache"
BEAT_THIS_CKPT_DIR = BASE_DIR / "models" / "beat_this"
BEAT_THIS_CKPT_PATH = BEAT_THIS_CKPT_DIR / "final0.ckpt"
BEAT_THIS_CKPT_URL = "https://cloud.cp.jku.at/index.php/s/7ik4RrBKTS273gp"
CACHE_VERSION = "v3"

NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

CHORD_QUALITIES: list[tuple[str, tuple[int, ...], float]] = [
    ("", (0, 4, 7), 0.0),
    ("m", (0, 3, 7), 0.0),
    ("7", (0, 4, 7, 10), 0.02),
    ("maj7", (0, 4, 7, 11), 0.02),
    ("m7", (0, 3, 7, 10), 0.02),
    ("sus2", (0, 2, 7), 0.03),
    ("sus4", (0, 5, 7), 0.03),
]

EXTENSION_MIN_MARGIN = 0.045
LOW_CONFIDENCE_THRESHOLD = 0.55

KRUMHANSL_MAJOR = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float64,
)
KRUMHANSL_MINOR = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float64,
)

_BEAT_THIS_MODEL = None


def _file_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
            vec[root_idx] = 1.5
            vec[(root_idx + 7) % 12] = 1.1
            vec /= np.linalg.norm(vec)
            labels.append(f"{root_name}{suffix}")
            templates.append(vec)
            penalties.append(penalty)
            roots.append(root_idx)

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
    if synced.shape[1] >= n_beats + 1:
        return synced[:, 1 : n_beats + 1]
    return synced[:, :n_beats]


def _fill_and_align_beat_grid(
    beat_times: list[float],
    tempo: float,
    duration: float,
    y_beat: np.ndarray,
    sr: int,
) -> tuple[list[float], list[float], int]:
    """Fill missing/intro/outro beats from tempo and align downbeats to strongest 4-beat phase."""
    beat_period = 60.0 / max(tempo, 30.0)
    expected_beats = duration * tempo / 60.0
    sorted_beats = sorted(t for t in beat_times if 0.0 <= t < duration)
    estimated_count = 0

    if not sorted_beats:
        grid = np.arange(0.0, duration, beat_period).tolist()
        downbeats = [round(grid[i], 3) for i in range(0, len(grid), 4)]
        return grid, downbeats, len(grid)

    # 1. Fill internal gaps if beat_track dropped beats in quiet/bridge sections
    filled: list[float] = [sorted_beats[0]]
    for t in sorted_beats[1:]:
        gap = t - filled[-1]
        if gap > 1.45 * beat_period:
            n_missing = max(1, int(round(gap / beat_period)) - 1)
            step = gap / (n_missing + 1)
            for k in range(1, n_missing + 1):
                filled.append(filled[-1] + step)
                estimated_count += 1
        filled.append(t)

    # 2. Extend backward from the first stable beat to cover any intro
    while filled[0] - beat_period >= 0.05:
        filled.insert(0, filled[0] - beat_period)
        estimated_count += 1

    # 3. Extend forward to cover the end of the song if fewer beats than expected
    if len(filled) < expected_beats * 0.92 or filled[-1] < duration - 1.2 * beat_period:
        while filled[-1] + beat_period < duration - 0.1:
            filled.append(filled[-1] + beat_period)
            estimated_count += 1

    # 4. Align bar lines to the strongest 4-beat phase (fixes 1-beat intro offset)
    onset_env = librosa.onset.onset_strength(y=y_beat, sr=sr)
    beat_frames = np.clip(librosa.time_to_frames(np.array(filled), sr=sr), 0, max(0, len(onset_env) - 1))
    phase_scores = [
        float(np.mean(onset_env[beat_frames[p::4]])) if len(beat_frames[p::4]) > 0 else 0.0
        for p in range(4)
    ]
    best_phase = int(np.argmax(phase_scores))
    downbeats = [round(float(filled[i]), 3) for i in range(best_phase, len(filled), 4)]

    return [float(t) for t in filled], downbeats, estimated_count


def _track_beats_librosa(
    y_beat: np.ndarray, sr: int, duration: float
) -> tuple[float, list[float], list[float], str, int]:
    """Track beats with librosa, fill missing intro/outro/gap beats, and align downbeats."""
    onset_env = librosa.onset.onset_strength(y=y_beat, sr=sr)
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

    raw_beats = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    beat_times, downbeats, beats_estimated = _fill_and_align_beat_grid(
        raw_beats, tempo, duration, y_beat, sr
    )
    return tempo, beat_times, downbeats, "4/4", beats_estimated


def _ensure_beat_this_checkpoint(progress_cb=None) -> Path:
    """Return local beat_this checkpoint path if present; otherwise instruct manual download."""
    import torch

    if BEAT_THIS_CKPT_PATH.is_file() and BEAT_THIS_CKPT_PATH.stat().st_size > 0:
        return BEAT_THIS_CKPT_PATH

    hub_ckpt = Path(torch.hub.get_dir()) / "checkpoints" / "beat_this-final0.ckpt"
    if hub_ckpt.is_file() and hub_ckpt.stat().st_size > 0:
        return hub_ckpt

    msg = (
        f"beat_this checkpoint not found. Download it manually from "
        f"{BEAT_THIS_CKPT_URL} and save it in folder '{BEAT_THIS_CKPT_DIR}' as 'final0.ckpt' "
        f"(full path: {BEAT_THIS_CKPT_PATH})."
    )
    print(msg)
    if progress_cb:
        progress_cb(msg)
    raise FileNotFoundError(msg)


def _track_beats_beat_this(
    y_beat: np.ndarray, sr: int, duration: float, progress_cb=None
) -> tuple[float, list[float], list[float], str]:
    """Track beats and downbeats using CPJKU beat_this on CPU."""
    global _BEAT_THIS_MODEL
    if _BEAT_THIS_MODEL is None:
        from beat_this.inference import Audio2Beats

        ckpt_path = _ensure_beat_this_checkpoint(progress_cb=progress_cb)
        _BEAT_THIS_MODEL = Audio2Beats(checkpoint_path=str(ckpt_path), device="cpu", dbn=False)

    beats_arr, downbeats_arr = _BEAT_THIS_MODEL(y_beat.astype(np.float32), sr)
    beat_times = [float(t) for t in np.atleast_1d(beats_arr) if 0.0 <= t <= duration]
    downbeats = [float(t) for t in np.atleast_1d(downbeats_arr) if 0.0 <= t <= duration]

    if len(beat_times) < 2:
        raise RuntimeError("beat_this produced fewer than 2 beats.")

    ibi = np.diff(beat_times)
    median_ibi = float(np.median(ibi))
    tempo = 60.0 / median_ibi if median_ibi > 0 else 120.0

    # Derive time signature from downbeat spacing
    time_sig = "4/4"
    if len(downbeats) >= 2:
        beats_np = np.array(beat_times)
        counts: list[int] = []
        for i in range(len(downbeats) - 1):
            c = int(np.sum((beats_np >= downbeats[i] - 0.08) & (beats_np < downbeats[i + 1] - 0.08)))
            if 2 <= c <= 12:
                counts.append(c)
        if counts:
            beats_per_bar = int(round(float(np.median(counts))))
            if beats_per_bar == 3:
                time_sig = "3/4"
            elif beats_per_bar == 6:
                time_sig = "6/8"
            elif beats_per_bar == 2:
                time_sig = "2/4"
            elif beats_per_bar == 5:
                time_sig = "5/4"
            else:
                time_sig = f"{beats_per_bar}/4"

    return tempo, beat_times, [round(d, 3) for d in downbeats], time_sig


def _analyze_chords_phase1(
    y_harm: np.ndarray,
    sr: int,
    beat_times: list[float],
    duration: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Phase 1 chord & key estimation on a harmonic signal given beat timestamps."""
    if sr != 22050:
        y_22k = librosa.resample(y_harm, orig_sr=sr, target_sr=22050)
        sr = 22050
    else:
        y_22k = y_harm

    beat_frames = librosa.time_to_frames(np.array(beat_times), sr=sr)

    tuning = float(librosa.estimate_tuning(y=y_22k, sr=sr))
    chroma = librosa.feature.chroma_cqt(y=y_22k, sr=sr, tuning=tuning, bins_per_octave=36)
    chroma = scipy.ndimage.median_filter(chroma, size=(1, 9))

    bass_chroma = librosa.feature.chroma_cqt(
        y=y_22k,
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

    norms = np.linalg.norm(beat_chroma, axis=0, keepdims=True)
    beat_energy = norms.squeeze(0)
    norm_chroma = beat_chroma / np.where(norms > 1e-8, norms, 1.0)

    bass_norms = np.linalg.norm(beat_bass, axis=0, keepdims=True)
    norm_bass = beat_bass / np.where(bass_norms > 1e-8, bass_norms, 1.0)

    global_key = detect_key_krumhansl(np.mean(chroma, axis=1))
    labels, templates, penalties, roots = build_chord_templates()
    scores = templates @ norm_chroma - penalties[:, np.newaxis]

    # Bass-root boost
    for state_idx, root_idx in enumerate(roots):
        if root_idx >= 0:
            scores[state_idx] += 0.22 * norm_bass[root_idx]

    # Section-local gentle diatonic prior (+0.015) over 16-beat windows to respect modulations/borrowed chords
    section_len = 16
    for start_b in range(0, n_beats, section_len):
        end_b = min(n_beats, start_b + section_len)
        sec_key = detect_key_krumhansl(np.mean(beat_chroma[:, start_b:end_b], axis=1))
        sec_diatonic = _diatonic_chords_for_key(sec_key)
        for state_idx, label in enumerate(labels):
            if label in sec_diatonic:
                scores[state_idx, start_b:end_b] += 0.015

    raw_scores = scores.copy()

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

    silence_thresh = float(np.median(beat_energy)) * 0.03 + 1e-6
    silent_mask = beat_energy < silence_thresh
    scores[-1, silent_mask] = 1.0
    scores[-1, ~silent_mask] = -1.5

    probs = _softmax(scores)
    transition = _build_transition_matrix(len(labels), self_prob=0.85)
    path_states = librosa.sequence.viterbi(probs, transition)

    beat_chords: list[dict[str, Any]] = []
    for idx in range(n_beats):
        start_t = float(beat_times[idx])
        end_t = float(beat_times[idx + 1]) if idx + 1 < n_beats else duration
        state_idx = int(path_states[idx])
        chord_label = labels[state_idx]

        col = raw_scores[:, idx]
        chosen_score = float(col[state_idx])
        other_scores = np.delete(col, state_idx)
        runner_up = float(np.max(other_scores)) if len(other_scores) > 0 else 0.0
        margin = chosen_score - runner_up
        conf = float(np.clip(1.0 / (1.0 + np.exp(-margin / 0.12)), 0.0, 1.0))

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

    return beat_chords, chords, global_key


def detect_sections(
    y_harm: np.ndarray,
    sr: int,
    beat_times: list[float],
    duration: float,
) -> list[dict[str, Any]]:
    """Estimate rough song sections (Intro, Verse, Chorus, Bridge, Outro) from bar chroma & energy."""
    if len(beat_times) < 8:
        return [
            {
                "label": "Main",
                "bar_start": 1,
                "bar_end": max(1, (len(beat_times) + 3) // 4),
                "start": round(float(beat_times[0]) if beat_times else 0.0, 3),
                "end": round(duration, 3),
                "estimated": True,
            }
        ]

    if sr != 22050:
        y_22k = librosa.resample(y_harm, orig_sr=sr, target_sr=22050)
        sr = 22050
    else:
        y_22k = y_harm

    beat_frames = librosa.time_to_frames(np.array(beat_times), sr=sr)
    chroma = librosa.feature.chroma_cqt(y=y_22k, sr=sr, bins_per_octave=24)
    rms = librosa.feature.rms(y=y_22k)

    beat_chroma = _sync_beats_exact(chroma, beat_frames)
    beat_rms = _sync_beats_exact(rms, beat_frames).squeeze(0)

    n_beats = min(len(beat_times), beat_chroma.shape[1])
    n_bars = n_beats // 4
    if n_bars < 4:
        return [
            {
                "label": "Main",
                "bar_start": 1,
                "bar_end": max(1, n_bars),
                "start": round(float(beat_times[0]), 3),
                "end": round(duration, 3),
                "estimated": True,
            }
        ]

    # Aggregate 4-beat bars
    bar_chroma = np.array(
        [np.mean(beat_chroma[:, b * 4 : (b + 1) * 4], axis=1) for b in range(n_bars)]
    )  # [n_bars, 12]
    bar_energy = np.array(
        [float(np.mean(beat_rms[b * 4 : (b + 1) * 4])) for b in range(n_bars)]
    )
    norms = np.linalg.norm(bar_chroma, axis=1, keepdims=True)
    bar_chroma_norm = bar_chroma / np.where(norms > 1e-8, norms, 1.0)

    # Bar-to-bar self-similarity + novelty curve (4-bar checkerboard window)
    sim = bar_chroma_norm @ bar_chroma_norm.T
    half = min(4, max(2, n_bars // 6))
    novelty = np.zeros(n_bars, dtype=np.float64)
    for i in range(half, n_bars - half):
        same_prev = float(np.mean(sim[i - half : i, i - half : i]))
        same_next = float(np.mean(sim[i : i + half, i : i + half]))
        cross = float(np.mean(sim[i - half : i, i : i + half]))
        e_diff = abs(float(np.mean(bar_energy[i : i + half])) - float(np.mean(bar_energy[i - half : i])))
        e_scale = float(np.median(bar_energy)) + 1e-8
        novelty[i] = max(0.0, 0.5 * (same_prev + same_next) - cross) + 0.35 * (e_diff / e_scale)

    # Pick boundary peaks with minimum 4-bar spacing (preferring 4-bar phrasing)
    boundaries = [0]
    min_len = 4
    thresh = float(np.mean(novelty) + 0.45 * np.std(novelty))
    for i in range(min_len, n_bars - min_len + 1):
        if novelty[i] >= thresh and novelty[i] >= novelty[i - 1] and novelty[i] >= novelty[i + 1]:
            if i - boundaries[-1] >= min_len:
                boundaries.append(i)
    if n_bars - boundaries[-1] < min_len and len(boundaries) > 1:
        boundaries[-1] = n_bars
    else:
        boundaries.append(n_bars)

    # Compute per-section mean chroma & energy
    raw_secs: list[dict[str, Any]] = []
    for s_idx in range(len(boundaries) - 1):
        b0, b1 = boundaries[s_idx], boundaries[s_idx + 1]
        vec = np.mean(bar_chroma_norm[b0:b1], axis=0)
        vec /= np.linalg.norm(vec) + 1e-8
        raw_secs.append(
            {
                "b0": b0,
                "b1": b1,
                "energy": float(np.mean(bar_energy[b0:b1])),
                "vec": vec,
            }
        )

    med_energy = float(np.median([s["energy"] for s in raw_secs]))
    n_sec = len(raw_secs)
    labels: list[str] = ["Verse"] * n_sec

    if n_sec >= 3 and raw_secs[0]["b1"] - raw_secs[0]["b0"] <= 8 and raw_secs[0]["energy"] <= med_energy * 1.05:
        labels[0] = "Intro"
    if n_sec >= 3 and raw_secs[-1]["b1"] - raw_secs[-1]["b0"] <= 8 and raw_secs[-1]["energy"] <= med_energy * 1.05:
        labels[-1] = "Outro"

    mid_indices = [i for i in range(n_sec) if labels[i] not in {"Intro", "Outro"}]
    if mid_indices:
        # Higher-energy middle sections become Chorus; lower-energy repeating become Verse; unique contrast becomes Bridge
        max_e = max(raw_secs[i]["energy"] for i in mid_indices)
        min_e = min(raw_secs[i]["energy"] for i in mid_indices)
        e_mid = 0.5 * (max_e + min_e)
        for i in mid_indices:
            if raw_secs[i]["energy"] >= e_mid and max_e > min_e * 1.08:
                labels[i] = "Chorus"
            else:
                labels[i] = "Verse"
        # Check for a contrasting middle section (Bridge) if >= 4 middle sections
        if len(mid_indices) >= 4:
            for i in mid_indices[1:-1]:
                sims = [float(np.dot(raw_secs[i]["vec"], raw_secs[j]["vec"])) for j in mid_indices if j != i]
                if max(sims) < 0.86:
                    labels[i] = "Bridge"
                    break

    sections: list[dict[str, Any]] = []
    for i, sec in enumerate(raw_secs):
        b0, b1 = sec["b0"], sec["b1"]
        start_t = float(beat_times[b0 * 4])
        end_t = float(beat_times[b1 * 4]) if b1 * 4 < len(beat_times) else duration
        sections.append(
            {
                "label": labels[i],
                "bar_start": b0 + 1,
                "bar_end": b1,
                "start": round(start_t, 3),
                "end": round(max(end_t, start_t), 3),
                "estimated": True,
            }
        )

    return sections


def analyze_audio(
    file_path: str | Path,
    use_phase2: bool = True,
    use_cache: bool = True,
    mode: str = "accurate",
    progress_cb=None,
) -> dict[str, Any]:
    """Analyze audio using Fast (full-mix BTC) or Accurate (Demucs + beat_this + BTC) mode."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    clean_mode = "fast" if mode == "fast" else "accurate"
    file_hash = _file_sha256(path)
    mode_tag = f"{clean_mode}_{CACHE_VERSION}" if use_phase2 else "v1"
    cache_path = CACHE_DIR / f"{file_hash}_{mode_tag}.json"
    if use_cache and cache_path.exists():
        if progress_cb:
            progress_cb("Loaded cached analysis.")
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached["cached"] = True
        return cached

    if not use_phase2:
        sr = 22050
        y, sr = librosa.load(str(path), sr=sr, mono=True)
        duration = float(librosa.get_duration(y=y, sr=sr))
        if duration < 0.5 or np.max(np.abs(y)) < 1e-6:
            raise ValueError("The audio file appears to be empty or silent.")
        y_harm, y_perc = librosa.effects.hpss(y)
        beat_source = y_perc if np.max(np.abs(y_perc)) > 1e-4 else y
        tempo, beat_times, downbeats, time_sig, beats_estimated = _track_beats_librosa(
            beat_source, sr, duration
        )
        beat_chords, chords, key = _analyze_chords_phase1(y_harm, sr, beat_times, duration)
        sections = detect_sections(y_harm, sr, beat_times, duration)
        result = {
            "duration": round(duration, 3),
            "tempo": round(tempo, 1),
            "key": key,
            "time_signature": time_sig,
            "beats": [round(float(t), 3) for t in beat_times],
            "downbeats": downbeats,
            "beats_estimated": beats_estimated,
            "beat_engine": "librosa-fallback",
            "beat_engine_note": "Phase 1 librosa beat tracking",
            "chords": chords,
            "beat_chords": beat_chords,
            "sections": sections,
            "pipeline": "phase1-librosa",
            "cached": False,
        }
        return result

    # --- Phase 2 pipeline ---
    pipeline_parts = []

    # 1. Audio loading & optional Demucs stem separation
    if clean_mode == "fast":
        if progress_cb:
            progress_cb("Loading audio (Fast mode)...")
        stem_sr = 22050
        y, stem_sr = librosa.load(str(path), sr=stem_sr, mono=True)
        duration = float(librosa.get_duration(y=y, sr=stem_sr))
        if duration < 0.5 or np.max(np.abs(y)) < 1e-6:
            raise ValueError("The audio file appears to be empty or silent.")
        harm_mix_mono = y
        drums_mono = y
        pipeline_parts.append("fullmix")
    else:
        if progress_cb:
            progress_cb("Separating stems with Demucs (Accurate mode)...")
        try:
            from backend.separate import separate_stems

            drums_mono, harm_mix_mono, stem_sr = separate_stems(path)
            duration = float(len(harm_mix_mono) / stem_sr)
            if duration < 0.5 or (np.max(np.abs(harm_mix_mono)) < 1e-6 and np.max(np.abs(drums_mono)) < 1e-6):
                raise ValueError("The audio file appears to be empty or silent.")
            pipeline_parts.append("demucs")
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("Demucs failed (%s); falling back to librosa HPSS.", exc)
            stem_sr = 22050
            y, stem_sr = librosa.load(str(path), sr=stem_sr, mono=True)
            duration = float(librosa.get_duration(y=y, sr=stem_sr))
            if duration < 0.5 or np.max(np.abs(y)) < 1e-6:
                raise ValueError("The audio file appears to be empty or silent.")
            harm_mix_mono, drums_mono = librosa.effects.hpss(y)
            pipeline_parts.append("hpss")

    # 2. Beat & downbeat tracking (beat_this, fallback to librosa)
    if progress_cb:
        progress_cb("Tracking beats and downbeats...")
    beat_source = drums_mono if np.max(np.abs(drums_mono)) > 1e-4 else harm_mix_mono
    beats_estimated = 0
    beat_engine = "beat_this"
    beat_engine_note = ""
    try:
        tempo, beat_times, downbeats, time_sig = _track_beats_beat_this(
            beat_source, stem_sr, duration, progress_cb=progress_cb
        )
        pipeline_parts.append("beat_this")
    except Exception as exc:
        logger.warning("beat_this failed (%s); falling back to librosa beat_track.", exc)
        beat_engine = "librosa-fallback"
        beat_engine_note = str(exc)
        sr_bt = 22050
        bt_22k = librosa.resample(beat_source, orig_sr=stem_sr, target_sr=sr_bt) if stem_sr != sr_bt else beat_source
        tempo, beat_times, downbeats, time_sig, beats_estimated = _track_beats_librosa(
            bt_22k, sr_bt, duration
        )
        pipeline_parts.append("librosa-beats")

    # 3. Chord recognition (BTC, fallback to Phase 1)
    if progress_cb:
        progress_cb("Recognising chords with BTC...")
    try:
        from backend.btc_chord import predict_chords_btc

        beat_chords, chords = predict_chords_btc(harm_mix_mono, stem_sr, beat_times, duration)
        pipeline_parts.append("btc")
    except Exception as exc:
        logger.warning("BTC chord recognition failed (%s); falling back to Phase 1.", exc)
        beat_chords, chords, _ = _analyze_chords_phase1(harm_mix_mono, stem_sr, beat_times, duration)
        pipeline_parts.append("librosa-chords")

    # 4. Key detection via Krumhansl on harmonic mix
    if progress_cb:
        progress_cb("Estimating song key...")
    harm_22k = librosa.resample(harm_mix_mono, orig_sr=stem_sr, target_sr=22050) if stem_sr != 22050 else harm_mix_mono
    tuning = float(librosa.estimate_tuning(y=harm_22k, sr=22050))
    chroma_for_key = librosa.feature.chroma_cqt(y=harm_22k, sr=22050, tuning=tuning, bins_per_octave=36)
    key = detect_key_krumhansl(np.mean(chroma_for_key, axis=1))

    if progress_cb:
        progress_cb("Estimating song sections...")
    sections = detect_sections(harm_22k, 22050, beat_times, duration)

    result = {
        "duration": round(duration, 3),
        "tempo": round(tempo, 1),
        "key": key,
        "time_signature": time_sig,
        "beats": [round(float(t), 3) for t in beat_times],
        "downbeats": downbeats,
        "beats_estimated": beats_estimated,
        "beat_engine": beat_engine,
        "beat_engine_note": beat_engine_note,
        "chords": chords,
        "beat_chords": beat_chords,
        "sections": sections,
        "pipeline": "+".join(pipeline_parts),
        "mode": clean_mode,
        "cached": False,
    }

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result), encoding="utf-8")

    return result
