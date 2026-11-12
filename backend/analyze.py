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
CACHE_VERSION = "v2"

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


def _track_beats_librosa(y_beat: np.ndarray, sr: int, duration: float) -> tuple[float, list[float], list[float], str]:
    """Track beats with librosa and assume 4/4 downbeats."""
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

    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    if len(beat_times) < 2:
        step = 60.0 / tempo
        beat_times = np.arange(0.0, max(duration, step), step).tolist()

    downbeats = [round(float(beat_times[i]), 3) for i in range(0, len(beat_times), 4)]
    return tempo, [float(t) for t in beat_times], downbeats, "4/4"


def _track_beats_beat_this(
    y_beat: np.ndarray, sr: int, duration: float
) -> tuple[float, list[float], list[float], str]:
    """Track beats and downbeats using CPJKU beat_this on CPU."""
    global _BEAT_THIS_MODEL
    if _BEAT_THIS_MODEL is None:
        from beat_this.inference import Audio2Beats

        _BEAT_THIS_MODEL = Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)

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


def analyze_audio(
    file_path: str | Path,
    use_phase2: bool = True,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Analyze audio using Phase 2 (Demucs + beat_this + BTC) with Phase 1 fallback and SHA-256 caching."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    file_hash = _file_sha256(path)
    mode_tag = CACHE_VERSION if use_phase2 else "v1"
    cache_path = CACHE_DIR / f"{file_hash}_{mode_tag}.json"
    if use_cache and cache_path.exists():
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
        tempo, beat_times, downbeats, time_sig = _track_beats_librosa(beat_source, sr, duration)
        beat_chords, chords, key = _analyze_chords_phase1(y_harm, sr, beat_times, duration)
        result = {
            "duration": round(duration, 3),
            "tempo": round(tempo, 1),
            "key": key,
            "time_signature": time_sig,
            "beats": [round(float(t), 3) for t in beat_times],
            "downbeats": downbeats,
            "chords": chords,
            "beat_chords": beat_chords,
            "pipeline": "phase1-librosa",
            "cached": False,
        }
        return result

    # --- Phase 2 pipeline ---
    pipeline_parts = []

    # 1. Demucs stem separation on CPU
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

    # 2. Beat & downbeat tracking (beat_this on drums, fallback to librosa)
    beat_source = drums_mono if np.max(np.abs(drums_mono)) > 1e-4 else harm_mix_mono
    try:
        tempo, beat_times, downbeats, time_sig = _track_beats_beat_this(beat_source, stem_sr, duration)
        pipeline_parts.append("beat_this")
    except Exception as exc:
        logger.warning("beat_this failed (%s); falling back to librosa beat_track.", exc)
        sr_bt = 22050
        bt_22k = librosa.resample(beat_source, orig_sr=stem_sr, target_sr=sr_bt) if stem_sr != sr_bt else beat_source
        tempo, beat_times, downbeats, time_sig = _track_beats_librosa(bt_22k, sr_bt, duration)
        pipeline_parts.append("librosa-beats")

    # 3. Chord recognition (BTC on other+bass, fallback to Phase 1)
    try:
        from backend.btc_chord import predict_chords_btc

        beat_chords, chords = predict_chords_btc(harm_mix_mono, stem_sr, beat_times, duration)
        pipeline_parts.append("btc")
    except Exception as exc:
        logger.warning("BTC chord recognition failed (%s); falling back to Phase 1.", exc)
        beat_chords, chords, _ = _analyze_chords_phase1(harm_mix_mono, stem_sr, beat_times, duration)
        pipeline_parts.append("librosa-chords")

    # 4. Key detection via Krumhansl on other+bass harmonic mix
    harm_22k = librosa.resample(harm_mix_mono, orig_sr=stem_sr, target_sr=22050) if stem_sr != 22050 else harm_mix_mono
    tuning = float(librosa.estimate_tuning(y=harm_22k, sr=22050))
    chroma_for_key = librosa.feature.chroma_cqt(y=harm_22k, sr=22050, tuning=tuning, bins_per_octave=36)
    key = detect_key_krumhansl(np.mean(chroma_for_key, axis=1))

    result = {
        "duration": round(duration, 3),
        "tempo": round(tempo, 1),
        "key": key,
        "time_signature": time_sig,
        "beats": [round(float(t), 3) for t in beat_times],
        "downbeats": downbeats,
        "chords": chords,
        "beat_chords": beat_chords,
        "pipeline": "+".join(pipeline_parts),
        "cached": False,
    }

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result), encoding="utf-8")

    return result
