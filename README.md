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
3. **`beat_this` checkpoint:** Place `final0.ckpt` in `models/beat_this/final0.ckpt` (download manually from `https://cloud.cp.jku.at/index.php/s/7ik4RrBKTS273gp` if not already present; ChordLens will not auto-download it).
4. **JavaScript runtime for YouTube:** Install **Node.js** or **Deno** on `PATH` so `yt-dlp` can solve YouTube player extraction. If YouTube asks you to sign in or verify you are not a bot, you can optionally select your browser under **Options → YouTube cookies (personal use)** (off by default).

### Update downloader

YouTube changes its player format frequently. If YouTube downloads start failing, update `yt-dlp`:

```bash
.\.venv\Scripts\python.exe -m pip install -U yt-dlp
```

## Running the App

```bash
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

## Use on your phone

1. Find your PC's local IPv4 address on the same Wi-Fi network:
   ```powershell
   ipconfig
   ```
   Look for **IPv4 Address** under your Wi-Fi adapter (for example `192.168.1.42`).
2. Start the server bound to all interfaces:
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
3. If Windows Defender Firewall prompts, allow access on your **Private** network.
4. On your phone (connected to the same Wi-Fi), open `http://<your-pc-ip>:8000` (for example `http://192.168.1.42:8000`). You can also use **Add to Home Screen** (`frontend/manifest.json`).

> **Note:** Only bind to `0.0.0.0` on a trusted home or rehearsal Wi-Fi network, not on public Wi-Fi.

## Transpose and Capo

A slim **Key** strip directly below **Now playing** lets you transpose chords (`-11` to `+11` semitones) and pick a guitar capo (`0` to `12` frets) without altering the audio playback pitch:

- **Maths:** `sounding chord = original chord + transpose`, and `shape to play = sounding chord - capo`.
  - Example: a `C` chord transposed `+2` semitones sounds as `D`.
  - Example: a `G` shape played with **Capo 3** sounds as `Bb` (`G + 3 semitones = Bb`; conversely, a song sounding in `Bb` uses `G` shapes with Capo 3).
- **Key-aware spelling:** Sharp keys spell accidentals with sharps (`F#`, `C#`), flat keys spell them with flats (`Bb`, `Eb`), and minor keys follow their relative major — avoiding awkward spellings like `E#` or `Cb`.
- **Suggest capo:** Scans frets `0–7` to find the capo position with the highest share of open guitar chords (`C`, `G`, `D`, `A`, `E`, `Am`, `Em`, `Dm`) and lets you apply it with one click.

## Guitar Shapes, Follow Mode, Speed, and Loop

- **Guitar chord shapes (`frontend/chordShapes.js`):** Displays standard-tuning (`EADGBe`) open chords and movable E/A-shape barre chords as inline SVG diagrams in the **Now playing** area (toggleable via **Settings → Guitar shapes**). When a capo is active, diagrams show the fret shapes to play with a **Capo N** bar at the top. Rare chords fall back to a simple triad marked `simplified`. Tap the current chord to view its notes and switch between open and barre shapes.
- **Sticky Now playing & Follow mode:** The **Now playing** strip stays pinned above the chart with the current chord, next chord countdown, beat dots (`1–4`), bar progress, and Play/Pause + seek bar. **Follow mode** (in **Settings → Practice**) swaps the full chart for a 4-bar teleprompter.
- **Practice controls:** Slow down playback to `0.5x` or `0.75x` (with pitch preservation) and use **Loop 4 bars** in **Settings → Practice** to repeat difficult passages.
- **Branding:** The header mark and browser tab favicon share `frontend/logo.svg`.

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

## Credits and Licences

| Component | Source | Code Licence | Weights / Data Notes | Personal & Public Use |
| --- | --- | --- | --- | --- |
| **BTC Chord Model** | [puar-playground/btc-chord](https://huggingface.co/puar-playground/btc-chord) (packaging [jayg996/BTC-ISMIR19](https://github.com/jayg996/BTC-ISMIR19)) | MIT | Weights (`btc_model_large_voca.pt`) released under MIT; trained on MIR datasets (Isophonics, Billboard, Robbie Williams) | Personal and public/commercial code & weights allowed under MIT; check dataset terms if redistributing derived benchmarks |
| **Demucs (`htdemucs`)** | [facebookresearch/demucs](https://github.com/facebookresearch/demucs) | MIT | Pretrained `htdemucs` weights were trained on MUSDB18-HQ (non-commercial / research audio) | Personal use OK; **public/commercial use of pretrained `htdemucs` weights is restricted** by MUSDB18-HQ terms |
| **beat_this** | [CPJKU/beat_this](https://github.com/CPJKU/beat_this) | MIT | Published `final0.ckpt` weights released under MIT; authors note training files include copyrighted/CC audio | Personal and public use allowed under MIT; review authors' dataset notice for commercial deployments |
| **librosa** | [librosa/librosa](https://github.com/librosa/librosa) | ISC | N/A | Personal and public/commercial use allowed |
| **yt-dlp** | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense (Public Domain) | N/A | Personal and public use allowed; subject to YouTube Terms of Service and local copyright law |
| **PyTorch & torchaudio** | [pytorch/pytorch](https://github.com/pytorch/pytorch) | BSD-3-Clause | N/A | Personal and public/commercial use allowed |
| **FastAPI / pytest** | [fastapi/fastapi](https://github.com/fastapi/fastapi), [pytest-dev/pytest](https://github.com/pytest-dev/pytest) | MIT | N/A | Personal and public/commercial use allowed |
| **uvicorn / numpy / scipy / soundfile / httpx** | PyPI | BSD-3-Clause | N/A | Personal and public/commercial use allowed |
| **python-multipart / huggingface-hub** | PyPI | Apache-2.0 | N/A | Personal and public/commercial use allowed |
| **Guitar Chord Shapes** | `frontend/chordShapes.js` (own table, standard tuning) | MIT (this repo) | N/A | Personal and public/commercial use allowed |
| **ffmpeg** *(external binary)* | [ffmpeg.org](https://ffmpeg.org/) | LGPL v2.1+ or GPL v2+/v3+ | Windows `gyan.dev` `full_build` is GPL v3 | Personal use OK; if bundling `ffmpeg` in a public release, verify LGPL vs GPL build terms |

## Notice

YouTube downloading via `yt-dlp` is intended strictly for personal use with audio you have the right to analyze.
