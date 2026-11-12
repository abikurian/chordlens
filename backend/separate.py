"""Demucs CPU stem separation for ChordLens Phase 2."""

from __future__ import annotations

import os
from pathlib import Path

import librosa
import numpy as np
import torch

_DEMUCS_MODEL = None

# Configure CPU thread count once for PyTorch inference
_CPU_THREADS = max(1, min(8, os.cpu_count() or 4))
torch.set_num_threads(_CPU_THREADS)


def _get_demucs_model():
    global _DEMUCS_MODEL
    if _DEMUCS_MODEL is None:
        from demucs.pretrained import get_model

        model = get_model("htdemucs")
        model.eval()
        model.to("cpu")
        _DEMUCS_MODEL = model
    return _DEMUCS_MODEL


def separate_stems(file_path: str | Path) -> tuple[np.ndarray, np.ndarray, int]:
    """Separate audio into (drums_mono, other_plus_bass_mono, sample_rate) on CPU."""
    from demucs.apply import apply_model

    model = _get_demucs_model()
    target_sr = int(model.samplerate)

    # Load stereo via librosa (handles mp3, wav, m4a, flac via soundfile/audioread)
    y_stereo, _ = librosa.load(str(file_path), sr=target_sr, mono=False)
    if y_stereo.ndim == 1:
        y_stereo = np.stack([y_stereo, y_stereo], axis=0)
    elif y_stereo.shape[0] > 2:
        y_stereo = y_stereo[:2]

    wav_tensor = torch.tensor(y_stereo, dtype=torch.float32).unsqueeze(0)  # [1, 2, T]

    with torch.no_grad():
        # shifts=0 and segment=8 speed up CPU inference while keeping stem quality
        sources = apply_model(
            model,
            wav_tensor,
            device="cpu",
            shifts=0,
            split=True,
            segment=8,
            overlap=0.25,
            progress=False,
        )[0]

    source_names = list(model.sources)  # ['drums', 'bass', 'other', 'vocals']
    drums_idx = source_names.index("drums")
    bass_idx = source_names.index("bass")
    other_idx = source_names.index("other")

    drums_mono = sources[drums_idx].mean(dim=0).cpu().numpy().astype(np.float32)
    harm_mix_mono = (
        (sources[other_idx] + sources[bass_idx]).mean(dim=0).cpu().numpy().astype(np.float32)
    )

    return drums_mono, harm_mix_mono, target_sr

