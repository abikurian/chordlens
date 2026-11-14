"""BTC (Bi-directional Transformer for Chord Recognition) wrapper for Phase 2."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import torch

BASE_DIR = Path(__file__).resolve().parent.parent
LOW_CONFIDENCE_THRESHOLD = 0.55


def get_btc_model_dir() -> Path:
    """Return the bundled or cached btc-chord directory containing weights and code."""
    from backend.paths import get_bundled_models_dir, MODELS_DIR

    candidates = [
        get_bundled_models_dir() / "btc-chord",
        MODELS_DIR / "btc-chord",
        BASE_DIR / "models" / "btc-chord",
    ]
    for c in candidates:
        if (c / "btc_model_large_voca.pt").is_file():
            return c
    return candidates[0]

_BTC_CACHE: dict[str, Any] = {}

_MODEL_CFG = dict(
    feature_size=144,
    timestep=108,
    input_dropout=0.2,
    layer_dropout=0.2,
    attention_dropout=0.2,
    relu_dropout=0.2,
    num_layers=8,
    num_heads=4,
    hidden_size=128,
    total_key_depth=128,
    total_value_depth=128,
    filter_size=128,
    loss="ce",
    probs_out=True,
    num_chords=170,
)
_FEATURE_CFG = dict(
    song_hz=22050,
    inst_len=10.0,
    n_bins=144,
    bins_per_octave=24,
    hop_length=2048,
)
_TIMESTEP = 108


def format_mirex_chord(label: str) -> str:
    """Convert BTC MIREX chord label (e.g. 'C:maj', 'A:min7') to lead-sheet notation."""
    if not label or label in {"N", "X"}:
        return "N"
    if ":" not in label:
        return label
    root, quality = label.split(":", 1)
    # Strip bass inversion if present for clean chord symbol or keep readable
    quality = quality.split("/")[0]
    mapping = {
        "maj": "",
        "min": "m",
        "7": "7",
        "maj7": "maj7",
        "min7": "m7",
        "sus2": "sus2",
        "sus4": "sus4",
        "dim": "dim",
        "dim7": "dim7",
        "hdim7": "m7b5",
        "aug": "aug",
        "maj6": "6",
        "min6": "m6",
        "9": "9",
        "maj9": "maj9",
        "min9": "m9",
    }
    suffix = mapping.get(quality, quality)
    return f"{root}{suffix}"


def _load_btc() -> tuple[Any, np.ndarray, np.ndarray, list[str]]:
    if "model" in _BTC_CACHE:
        return (
            _BTC_CACHE["model"],
            _BTC_CACHE["mean"],
            _BTC_CACHE["std"],
            _BTC_CACHE["idx_to_chord"],
        )

    model_dir = get_btc_model_dir()
    pt_file = model_dir / "btc_model_large_voca.pt"

    if not pt_file.is_file():
        from huggingface_hub import snapshot_download
        from backend.paths import MODELS_DIR

        target = MODELS_DIR / "btc-chord"
        target.mkdir(parents=True, exist_ok=True)
        snapshot_download("puar-playground/btc-chord", local_dir=str(target))
        model_dir = target
        pt_file = model_dir / "btc_model_large_voca.pt"

    if str(model_dir) not in sys.path:
        sys.path.insert(0, str(model_dir))

    BTC_model = importlib.import_module("btc_src.btc_model").BTC_model
    features = importlib.import_module("btc_src.features")

    model = BTC_model(config=_MODEL_CFG).to("cpu")
    ckpt = torch.load(
        str(pt_file),
        map_location="cpu",
        weights_only=False,
    )
    model.load_state_dict(ckpt["model"])
    model.eval()

    idx_to_chord = features.idx2voca_chord()
    _BTC_CACHE["model"] = model
    _BTC_CACHE["mean"] = ckpt["mean"]
    _BTC_CACHE["std"] = ckpt["std"]
    _BTC_CACHE["idx_to_chord"] = idx_to_chord
    return model, ckpt["mean"], ckpt["std"], idx_to_chord


@torch.inference_mode()
def predict_chords_btc(
    audio_mono: np.ndarray,
    sr: int,
    beat_times: list[float],
    duration: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run BTC chord recognition with batched inference and align probabilities to beat intervals."""
    import os
    torch.set_num_threads(os.cpu_count() or 4)

    model, mean, std, idx_to_chord = _load_btc()
    features = importlib.import_module("btc_src.features")

    if sr != _FEATURE_CFG["song_hz"]:
        audio_22k = librosa.resample(audio_mono, orig_sr=sr, target_sr=_FEATURE_CFG["song_hz"])
    else:
        audio_22k = audio_mono

    feat = features.audio_to_features(
        audio_22k,
        sr_target=_FEATURE_CFG["song_hz"],
        inst_len=_FEATURE_CFG["inst_len"],
        n_bins=_FEATURE_CFG["n_bins"],
        bins_per_octave=_FEATURE_CFG["bins_per_octave"],
        hop_length=_FEATURE_CFG["hop_length"],
    )
    feat = feat.T  # [T, 144]
    n_orig_frames = feat.shape[0]
    feat = (feat - mean) / std

    n = _TIMESTEP
    rem = n_orig_frames % n
    num_pad = (n - rem) if rem != 0 else 0
    if num_pad > 0:
        feat = np.pad(feat, ((0, num_pad), (0, 0)), mode="constant", constant_values=0)
    num_instance = feat.shape[0] // n

    # Vectorized batched inference across all time segments
    x_batched = torch.tensor(feat, dtype=torch.float32).reshape(num_instance, n, -1)
    prob_chunks: list[np.ndarray] = []
    batch_size = 16
    for b_start in range(0, num_instance, batch_size):
        b_end = min(b_start + batch_size, num_instance)
        attn_out, _ = model.self_attn_layers(x_batched[b_start:b_end])
        logits = model.output_layer(attn_out)  # [B, 108, 170]
        probs = torch.softmax(logits, dim=-1).cpu().numpy()
        prob_chunks.extend(probs)

    frame_probs = np.vstack(prob_chunks)[:n_orig_frames]  # [T_orig, 170]
    time_unit = _FEATURE_CFG["inst_len"] / _TIMESTEP  # ~0.09259s per frame
    frame_times = np.arange(n_orig_frames) * time_unit

    beat_chords: list[dict[str, Any]] = []
    n_beats = len(beat_times)
    for idx in range(n_beats):
        start_t = float(beat_times[idx])
        end_t = float(beat_times[idx + 1]) if idx + 1 < n_beats else duration
        mask = (frame_times >= start_t) & (frame_times < max(end_t, start_t + time_unit))
        if not np.any(mask):
            nearest = int(np.clip(np.argmin(np.abs(frame_times - start_t)), 0, n_orig_frames - 1))
            beat_prob = frame_probs[nearest]
        else:
            beat_prob = np.mean(frame_probs[mask], axis=0)

        best_idx = int(np.argmax(beat_prob))
        conf = float(np.clip(beat_prob[best_idx], 0.0, 1.0))
        raw_label = idx_to_chord[best_idx]
        chord_label = format_mirex_chord(raw_label)

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

    # Merge consecutive identical chords
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

    return beat_chords, chords

