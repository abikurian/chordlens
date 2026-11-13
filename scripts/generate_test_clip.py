"""Generate a synthetic 10-second C-G-Am-F test audio clip for ChordLens self-check."""

from pathlib import Path
import numpy as np
import soundfile as sf


def generate_self_check_wav(output_path: Path | str) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    sr = 22050
    duration = 10.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = np.zeros_like(t)

    # Chords: C (0-2.5s), G (2.5-5.0s), Am (5.0-7.5s), F (7.5-10.0s)
    chords_info = [
        (0.0, 2.5, [261.63, 329.63, 392.00, 523.25]),      # C major: C4, E4, G4, C5
        (2.5, 5.0, [196.00, 246.94, 293.66, 392.00]),      # G major: G3, B3, D4, G4
        (5.0, 7.5, [220.00, 261.63, 329.63, 440.00]),      # A minor: A3, C4, E4, A4
        (7.5, 10.0, [174.61, 220.00, 261.63, 349.23]),     # F major: F3, A3, C4, F4
    ]

    for start, end, freqs in chords_info:
        mask = (t >= start) & (t < end)
        chord_t = t[mask]
        wave = np.zeros_like(chord_t)
        for f in freqs:
            wave += 0.25 * np.sin(2 * np.pi * f * chord_t)
            wave += 0.10 * np.sin(2 * np.pi * 2 * f * chord_t)
        audio[mask] += wave

    # Add click track at 120 bpm (every 0.5s)
    click_period = 0.5
    click_len = int(sr * 0.02)
    click_env = np.linspace(1, 0, click_len)
    click_wave = np.sin(2 * np.pi * 1000.0 * np.arange(click_len) / sr) * click_env * 0.3
    for beat_t in np.arange(0, duration, click_period):
        idx = int(beat_t * sr)
        end_idx = min(idx + click_len, len(audio))
        audio[idx:end_idx] += click_wave[:end_idx - idx]

    audio = audio / (np.max(np.abs(audio)) + 1e-6) * 0.8
    sf.write(str(out), audio, sr)
    return out


if __name__ == "__main__":
    dest = Path(__file__).resolve().parent.parent / "backend" / "fixtures" / "self_check_test.wav"
    generate_self_check_wav(dest)
    print(f"Generated {dest} ({dest.stat().st_size} bytes)")

