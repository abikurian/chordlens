# ChordLens

ChordLens analyses an audio file (MP3, WAV, M4A, FLAC) or a YouTube link and generates an interactive 4-beat-per-bar lead sheet with chords, confidence scores, tempo (BPM), beats/downbeats, time signature, and song key.

## Features

- **Audio & YouTube input:** Upload local audio files or paste a YouTube URL (`yt-dlp` + `ffmpeg`).
- **Two-tier CPU analysis pipeline:**
  - **Phase 2 (default):** Demucs (`htdemucs`) stem separation (`drums` for beat tracking, `other + bass` for harmony), `beat_this` for beats/downbeats/time signature (with `librosa` fallback), pretrained **BTC** (`puar-playground/btc-chord`, 170-chord vocabulary) for chord recognition (with `librosa` fallback), and Krumhansl-Schmuckler key estimation.
  - **SHA-256 caching:** Analyzed files are cached by content hash in `cache/` so repeat runs return immediately.
- **Interactive lead sheet:**
  - Audio player synced to the active bar and beat.
  - Click any beat to jump playback to that timestamp.
  - Low-confidence beats (`< 55%`) are visibly marked.
  - Inline manual chord editing (`Edit chords`) plus **JSON** and **text chord sheet** export.

## Installation

1. **Install Python 3.11** and **`ffmpeg`** (required for `yt-dlp` and `.m4a`/`.mp3` decoding). Verify `ffmpeg` is on your `PATH`:
   ```bash
   ffmpeg -version
   ```
2. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   # macOS / Linux:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

## Running the App

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

## Running Tests

```bash
pytest -v
```

## Measured Accuracy & Performance

All numbers below were measured directly on CPU (no GPU):

- **Synthetic 180s track (108 BPM, 81 bars with kick/snare/hi-hat + 7th chords, Phase 1 `librosa`):**
  - Tempo: `107.7 BPM` (true `108.0 BPM`), full `180.000s` coverage (`325` beats).
  - Per-bar chord accuracy by third: **77.8%** (first), **74.1%** (middle), **74.1%** (last).
  - Average confidence by third: `0.701` (bars 1–4), `0.638–0.642` (middle/last).
- **Synthetic 106.7s track (108 BPM, 48 bars with drums + 7ths, `pytest` suite):**
  - Passes `>= 65%` accuracy threshold across first, middle, and last thirds (`7/7` tests passing).
- **Real track (`Post Malone - Circles.m4a`, `215.282s`):**
  - Phase 1 (`librosa`): `20.84s`, average confidence `0.441 / 0.449 / 0.473` (`275/426` low-confidence beats), missed `G` and borrowed `Fm` chords.
  - Phase 2 (`demucs + librosa-beats + btc`): `676.07s` first run on CPU (`0.023s` cached), average confidence `0.780 / 0.717 / 0.709` (`84/388` low-confidence beats), cleanly recovering the `C -> G -> F -> Fm` progression.

## Notice

YouTube downloading via `yt-dlp` is intended strictly for personal use with audio you have the right to analyze.
