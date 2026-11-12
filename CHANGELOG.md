# Changelog

All notable changes to ChordLens are documented in this file.

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
