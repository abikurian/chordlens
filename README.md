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

## Install (for everyone)

If you just want to use ChordLens on Windows 10 or 11 (64-bit), you do **not** need Python, Git, ffmpeg, Node, or administrator rights. Everything is bundled.

1. **Download:** Grab `ChordLens-Setup-0.2.0.exe` (or the portable `.zip`) from [Releases](https://github.com/abikurian/chordlens/releases).
2. **Install:** Double-click `ChordLens-Setup-0.2.0.exe`. It installs to `%LOCALAPPDATA%\Programs\ChordLens` without requiring administrator privileges, creates a desktop and Start Menu shortcut, and sets up cleanly.
3. **SmartScreen warning:** Because ChordLens is an open-source build without an expensive commercial code-signing EV certificate, Windows Defender SmartScreen may display:
   > *"Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting."*

   Click **More info**, then click **Run anyway**.
   
   To verify file integrity before running, check the SHA-256 hash in PowerShell:
   ```powershell
   Get-FileHash .\ChordLens-Setup-0.2.0.exe -Algorithm SHA256
   ```
   Compare the output to the official hash listed in `checksums.txt` or on the release page.

4. **Where data lives:** All application data, analysis cache, downloaded models, and diagnostic logs are stored in:
   ```text
   %LOCALAPPDATA%\ChordLens
   ```
5. **How to uninstall:**
   - Open **Windows Settings &rarr; Apps &rarr; Installed apps**, search for **ChordLens**, and click **Uninstall**.
   - Or run `unins000.exe` located inside `%LOCALAPPDATA%\Programs\ChordLens`.

> [!WARNING]
> **Accurate mode (Demucs) CPU warning:**
> By default, ChordLens uses **Fast mode**, which finishes analysis in 5–15 seconds on any modern computer. If you select **Accurate mode**, it runs Demucs stem separation; on a standard laptop CPU without a dedicated NVIDIA CUDA GPU, Demucs separation can take **10+ minutes** per song. For normal practice and fast playback, keep the default Fast mode.

---

## Installation (from source for developers)

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

### Bundled toolchain & self-check

ChordLens bundles an official **LGPL** build of `ffmpeg` and `ffprobe` (built by BtbN, verified to contain no `--enable-gpl` and no `--enable-nonfree`), a **Deno** JavaScript runtime (MIT) for `yt-dlp` YouTube extraction, and the Fast-mode models (`beat_this` and `btc-chord`). The desktop build is completely self-contained and runs on a clean Windows PC without needing external tools or developer dependencies.

You can verify your installation anytime:
- From the CLI: `ChordLens.exe --self-check`
- From the UI: **Settings &rarr; About &rarr; Run self-check**

See `THIRD_PARTY_LICENSES.md` for full component sources, license texts, and LGPL verification details.

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
- **Horizontal chord lane & countdown:** Inside **Now playing**, a scrolling chord lane moves proportional chord blocks from right to left toward a fixed playhead (`30%` from the left) using `requestAnimationFrame`. Past blocks fade out while upcoming chords stay clear ahead; tap any block to seek or drag the lane to scrub. Before a chord change, the 4 beat dots switch to a countdown (`3 / 2 / 1 / now`) alongside `"Next: <chord>"`.
- **Fixed player block & Follow mode:** **Now playing** and the **Key** strip are pinned in one fixed block (under the top bar on desktop, at the bottom on phones) while only the chord chart scrolls in its own container. The chart shows each chord name only on the beat where it changes (leaving held beats blank), with tap-to-seek on every bar and beat. **Follow mode** (in **Settings → Practice**) swaps the full chart for a 4-bar teleprompter.
- **Practice & timing controls:** Slow down playback to `0.5x` or `0.75x` (with pitch preservation), use **Loop 4 bars** to repeat difficult passages, adjust **Timing nudge** (`-300 ms` to `+300 ms` in `10 ms` steps, saved per device) to offset audio latency, and set **Show changes early** (`0–3` beats, default `1` beat) in **Settings → Practice**.
- **Reliable beat grid & bar lines:** Solid bar lines and light beat dividers appear in both the chart and the chord lane only for bars where the beat grid is reliable: the beat engine is `beat_this` (not the `librosa` fallback), no beats in that bar were estimated or filled in, every beat interval in the bar stays within `15%` of the song's median beat spacing, and the downbeat comes from the model. Unreliable bars use dashed bar lines with no beat dividers and show a quiet summary note above the chart.
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

## Windows Installation & Releases

Pre-built Windows packages are available on the [Releases](https://github.com/abikurian/chordlens/releases) page:

1. **Download the installer or portable zip:**
   - **Installer:** `ChordLens-Setup-0.1.0.exe` (per-user install into `%LOCALAPPDATA%\Programs\ChordLens`, no admin rights needed, adds Start menu shortcut and optional desktop icon).
   - **Portable zip:** `ChordLens-v0.1.0-windows-x64.zip` (extract anywhere and run `ChordLens.exe`).
2. **Windows SmartScreen note:**
   - Because open-source binaries are not code-signed with an expensive EV certificate, Windows SmartScreen may show *"Windows protected your PC"*.
   - Click **More info** &rarr; **Run anyway**.
   - To verify file integrity before running, compare the SHA-256 hash against `checksums.txt` in PowerShell:
     ```powershell
     Get-FileHash -Path .\ChordLens-Setup-0.1.0.exe -Algorithm SHA256
     ```
3. **Where data is stored:**
   - All writable data (cache, downloaded audio, on-demand model weights, logs) is stored in:
     ```
     %LOCALAPPDATA%\ChordLens
     ```
   - Nothing is written to `Program Files` or next to the executable. You can click **Open data folder** or **Clear cache** in the in-app **Settings &rarr; About** panel anytime.
4. **How to uninstall:**
   - Open **Windows Settings &rarr; Apps &rarr; Installed apps**, find **ChordLens**, and click **Uninstall** (or run the uninstaller from the Start menu).
   - The uninstaller cleanly removes the application files. To also remove cached audio and model weights, delete `%LOCALAPPDATA%\ChordLens`.

## Building From Source & Releasing

### Build Requirements
- Python 3.11 x64
- PowerShell 7 or Windows PowerShell 5.1
- Inno Setup 6 (optional, needed to compile the installer; install with `winget install JRSoftware.InnoSetup`)
- Edge WebView2 Runtime (pre-installed on Windows 10/11)

### Build Steps
```powershell
# 1. Install dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller pywebview

# 2. Run build pipeline
.\build.ps1
```
This produces:
- `dist\ChordLens\` (portable folder)
- `dist\portable\ChordLens-v<version>-windows-x64.zip`
- `dist\installer\ChordLens-Setup-<version>.exe`

### Release Pipeline
To release a new version:
```powershell
# Auto-bumps version, builds, generates checksums, and creates a draft release if gh is installed
.\release.ps1 -Bump patch
```

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
| **PyInstaller** | [pyinstaller/pyinstaller](https://github.com/pyinstaller/pyinstaller) | GPL-2.0-or-later with PyInstaller exception | Built binaries are not subject to GPL terms under the PyInstaller special exception | Personal and public use allowed |
| **pywebview** | [r0x0r/pywebview](https://github.com/r0x0r/pywebview) | BSD-3-Clause | Uses system WebView2 runtime (Edge) | Personal and public/commercial use allowed |
| **Inno Setup** | [jrsoftware/issrc](https://github.com/jrsoftware/issrc) | Inno Setup Licence (BSD-style permissive) | N/A | Personal and public/commercial use allowed |
| **Playwright** *(dev-only)* | [microsoft/playwright-python](https://github.com/microsoft/playwright-python) | Apache-2.0 | Dev/testing fixture screenshot tool only, not bundled in app | Personal and public use allowed |
| **ffmpeg & ffprobe** *(bundled binary)* | [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) | LGPL v2.1+ | Official BtbN LGPL Windows x64 build, verified without `--enable-gpl` and without `--enable-nonfree`. Documented in `THIRD_PARTY_LICENSES.md`. | Personal and public/commercial use allowed under LGPL v2.1+ |
| **Deno** *(bundled binary)* | [denoland/deno](https://github.com/denoland/deno) | MIT | Standalone JavaScript runtime for `yt-dlp` YouTube extraction | Personal and public use allowed under MIT |

## Notice

YouTube downloading via `yt-dlp` is intended strictly for personal use with audio you have the right to analyze.
