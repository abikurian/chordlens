# Changelog

All notable changes to ChordLens are documented in this file.

## [0.2.1] - 2026-11-14

### Fixed
- Resolved duplicate `copyDiagnosticsBtn` identifier in `frontend/app.js` that caused a syntax error and prevented file upload and YouTube click handlers from initializing; separated error box diagnostics from Settings self-check details.
- Added build-time frontend JavaScript syntax verification (`node --check`) to fail builds immediately on syntax errors.

## [0.2.0] - 2026-11-13

### Added
- Fully self-contained Windows application bundle:
  - Bundled LGPL build of `ffmpeg.exe` and `ffprobe.exe` (BtbN Windows x64 build, verified without `--enable-gpl` or `--enable-nonfree`).
  - Bundled standalone Deno JavaScript runtime (`bin/deno.exe`, MIT) powering `yt-dlp` YouTube extraction without requiring external Node or Deno installations.
  - Bundled Fast-mode pre-trained models (`beat_this/final0.ckpt` and `btc-chord/btc_model_large_voca.pt`), eliminating first-run model downloads.
- Comprehensive system self-check (`backend/self_check.py`):
  - CLI mode via `ChordLens.exe --self-check` for unattended headless verification (returns exit code 0 on success, 1 on failure).
  - In-app interactive self-check accessible under **Settings &rarr; About &rarr; Run self-check**, featuring plain-language status, technical breakdown, and a "Copy details" action.
  - Automatic background verification on first application launch.
- `THIRD_PARTY_LICENSES.md` detailing licenses, sources, and compliance verification for all bundled third-party binaries and neural network checkpoints.
- Synthetic 10-second C-G-Am-F audio fixture (`backend/fixtures/self_check_test.wav`) and generation script (`scripts/generate_test_clip.py`) for deterministic pipeline verification.

### Changed
- `backend/paths.py`, `backend/ffmpeg_utils.py`, `backend/analyze.py`, and `backend/btc_chord.py` prioritize bundled binaries and models from the application folder before checking local app data or system PATH.
- Removed external WinGet/Chocolatey installation prompts; missing dependency errors now clearly prompt reinstalling the application.
- Made build scripts and path resolvers machine-agnostic, stripping all user-specific or drive-specific paths.

## [0.1.2] - 2026-11-13

### Fixed
- Intermittent JSON parsing failure when extracting metadata from YouTube URLs wrapped in resilient recovery logic with diagnostic failure logging.
- Prevented raw Python exception messages and stack traces from leaking into the user interface; all errors now map to concise, plain-language guidance with actionable next steps.
- Safe frontend fetch handling for non-JSON backend responses (HTML error pages or empty bodies) to prevent uncaught `SyntaxError` throws.

### Added
- "Copy diagnostics" action on error banners to easily copy app version, error message, and recent log lines for troubleshooting.
- Dedicated `/api/system/diagnostics` endpoint for accessing recent log lines.

### Changed
- Polished start screen layout: aligned content left edge and max-width with top-bar logo, eliminating empty desktop margin.
- Styled drag-and-drop file upload zone with visible focus rings, selected file indicators, and 44px+ accessible hit targets.

## [0.1.0] - 2026-11-12

### Added
- Audio file and YouTube chord/beat analysis with Fast (`librosa`) and Accurate (`demucs` + `beat_this` + `btc`) modes.
- Horizontal scrolling chord lane with frame-accurate `requestAnimationFrame` playhead, beat-dot countdown, timing nudge, and early-warning settings.
- Lead-sheet chord typesetting, auto-fit sizing, reliable vs. estimated bar lines and beat dividers, guitar chord shape diagrams, transpose, and capo suggestions.
- Windows desktop app (`ChordLens.exe`), per-user Inno Setup installer, and portable zip build.
