# ChordLens

ChordLens analyses an audio file (MP3, WAV, M4A, FLAC) or a YouTube link and generates an interactive 4-beat-per-bar lead sheet with chords, model confidence scores, tempo (BPM), beats/downbeats, time signature, and song key.

## Features

- **Audio & YouTube input:** Upload local audio files or paste a YouTube URL (`yt-dlp` + `ffmpeg`).
- **Fast & Accurate modes:**
  - **Fast (default):** Runs `beat_this` (or `librosa` fallback) and pretrained **BTC** (`puar-playground/btc-chord`, 170-chord vocabulary) directly on the full mix.
  - **Accurate:** Runs Demucs (`htdemucs`) stem separation first (`drums` for beats, `other + bass` for harmony), then `beat_this` + BTC + Krumhansl key estimation.
- **Background progress & caching:** Analyses run as background jobs with stage progress (`/api/jobs/{job_id}`), and results are cached by file SHA-256 + mode in `cache/`.
- **Interactive lead sheet:**
  - Audio player synced to the active bar and beat; click any beat to jump playback.
  - Low model confidence beats (`< 55%`) are visibly marked.
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
3. **Optional manual `beat_this` checkpoint:** On first run, ChordLens downloads `final0.ckpt` (~77 MB) with resume support to `models/beat_this/final0.ckpt`. If your network blocks the download, download it manually from `https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt` and place it at `models/beat_this/final0.ckpt`.

## Running the App

```bash
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

## Honest Reporting on Accuracy & Confidence

- **Model confidence is not accuracy:** The percentage shown on each beat is the model's own probability (BTC softmax probability or Phase 1 margin score), not a verified accuracy measurement.
- **What has been checked so far:** Accuracy has only been checked against synthetic audio tests and one real song (`Post Malone - Circles.m4a`) with no ground-truth chart file.
- **Measured synthetic results:**
  - Synthetic 180s track (`108 BPM`, 81 bars with drums + 7ths, Phase 1 `librosa`): `107.7 BPM`, full `180.0s` coverage, per-bar accuracy **77.8%** (first third), **74.1%** (middle), **74.1%** (last).
  - Synthetic 106.7s track (`108 BPM`, 48 bars with drums + 7ths): passes `>= 65%` accuracy across all thirds.
- **Real song observation (`Post Malone - Circles.m4a`, `215.282s`):**
  - Phase 1 (`librosa`): `20.84s`, average model confidence `0.441 / 0.449 / 0.473` (`275/426` low-confidence beats).
  - Phase 2 (`demucs + librosa-beats + btc`): `676.07s` first run on CPU (`0.023s` cached), average model confidence `0.780 / 0.717 / 0.709` (`84/388` low-confidence beats).

## How to Verify

1. **Automated unit & synthetic tests:**
   ```bash
   .\.venv\Scripts\python.exe -m pytest -v
   ```
2. **Verify in the browser:**
   - Start `uvicorn` and open `http://127.0.0.1:8000`.
   - Upload a song in **Fast** mode first, check the **Beat engine** readout (`beat_this` vs `librosa-fallback`), and confirm the last bar reaches the end of the track.
   - Re-run in **Accurate** mode if you want Demucs stem separation, and compare bars against your ear or a reference chart.
3. **Add real ground-truth charts:**
   - Copy `backend/tests/ground_truth/template.json` to add bar-by-bar ground-truth chord charts (`bar`, `chord`) for real songs you own.

## Notice

YouTube downloading via `yt-dlp` is intended strictly for personal use with audio you have the right to analyze.
