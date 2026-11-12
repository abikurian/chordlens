const brandHomeBtn = document.getElementById("brand-home-btn");
const settingsBtn = document.getElementById("settings-btn");
const settingsDot = document.getElementById("settings-dot");
const exportBtn = document.getElementById("export-btn");
const exportMenu = document.getElementById("export-menu");
const exportTxtBtn = document.getElementById("export-txt-btn");
const exportJsonBtn = document.getElementById("export-json-btn");
const songSummaryEl = document.getElementById("song-summary");

const inputView = document.getElementById("input-view");
const uploadForm = document.getElementById("upload-form");
const urlForm = document.getElementById("url-form");
const audioFileInput = document.getElementById("audio-file");
const youtubeUrlInput = document.getElementById("youtube-url");
const uploadBtn = document.getElementById("upload-btn");
const urlBtn = document.getElementById("url-btn");
const inputOptionsBtn = document.getElementById("input-options-btn");
const inputOptionsPanel = document.getElementById("input-options-panel");
const statusBanner = document.getElementById("status-banner");

const resultsView = document.getElementById("results-view");
const audioPlayer = document.getElementById("audio-player");
const nowPlayingStrip = document.getElementById("now-playing-strip");
const npCurrentBtn = document.getElementById("np-current-btn");
const nowPlayingChordEl = document.getElementById("now-playing-chord");
const npSimplifiedTag = document.getElementById("np-simplified-tag");
const npCurrentDiagram = document.getElementById("np-current-diagram");
const npNextBtn = document.getElementById("np-next-btn");
const nowPlayingNextChordEl = document.getElementById("now-playing-next-chord");
const nowPlayingCountdownEl = document.getElementById("now-playing-countdown");
const npBeatDots = Array.from(document.querySelectorAll("#np-beat-dots .beat-dot"));
const npBarProgress = document.getElementById("np-bar-progress");
const npTimeReadout = document.getElementById("np-time-readout");
const npPlayBtn = document.getElementById("np-play-btn");
const npSeekSlider = document.getElementById("np-seek-slider");
const jumpToBarBtn = document.getElementById("jump-to-bar-btn");

const chordPopover = document.getElementById("chord-popover");
const popoverTitle = document.getElementById("popover-title");
const popoverNotes = document.getElementById("popover-notes");
const popoverShapes = document.getElementById("popover-shapes");
const popoverCloseBtn = document.getElementById("popover-close-btn");
const followTeleprompter = document.getElementById("follow-teleprompter");
const sectionStripEl = document.getElementById("section-strip");
const leadSheetEl = document.getElementById("lead-sheet");

const settingsBackdrop = document.getElementById("settings-backdrop");
const settingsDrawer = document.getElementById("settings-drawer");
const settingsCloseBtn = document.getElementById("settings-close-btn");
const chordDetailBtn = document.getElementById("chord-detail-btn");
const guitarShapesBtn = document.getElementById("guitar-shapes-btn");
const viewShapesBtn = document.getElementById("view-shapes-btn");
const transposeDownBtn = document.getElementById("transpose-down-btn");
const transposeUpBtn = document.getElementById("transpose-up-btn");
const transposeValEl = document.getElementById("transpose-val");
const transposeResetBtn = document.getElementById("transpose-reset-btn");
const resultingKeyEl = document.getElementById("resulting-key");
const capoSelect = document.getElementById("capo-select");
const suggestCapoBtn = document.getElementById("suggest-capo-btn");
const capoSuggestionBox = document.getElementById("capo-suggestion");
const capoSuggestionText = document.getElementById("capo-suggestion-text");
const applyCapoBtn = document.getElementById("apply-capo-btn");
const speedBtns = Array.from(document.querySelectorAll(".speed-btn"));
const npLoopBtn = document.getElementById("np-loop-btn");
const followModeBtn = document.getElementById("follow-mode-btn");
const moreDetailBtn = document.getElementById("more-detail-btn");
const editModeBtn = document.getElementById("edit-mode-btn");
const newSongBtn = document.getElementById("new-song-btn");

window.addEventListener("error", (event) => {
  console.error("ChordLens UI error:", event.error || event.message);
  if (statusBanner) {
    statusBanner.textContent = `UI error: ${event.message || "Unexpected error. Reload the page."}`;
    statusBanner.className = "status-line error";
    statusBanner.hidden = false;
  }
});

window.addEventListener("unhandledrejection", (event) => {
  console.error("ChordLens unhandled promise error:", event.reason);
  if (statusBanner) {
    statusBanner.textContent = `UI error: ${(event.reason && event.reason.message) || event.reason || "Unexpected error."}`;
    statusBanner.className = "status-line error";
    statusBanner.hidden = false;
  }
});

let currentAnalysis = null;
let beatNodes = [];
let barNodes = [];
let sectionNodes = [];
let rafId = null;
let isEditMode = false;
let chordDetailMode = "simple"; // "simple" | "full"
let showMoreDetail = false;
let autoScrollEnabled = true;
let isProgrammaticScroll = false;
let lastActiveBarIdx = -1;
let transposeSemitones = 0; // -11 .. +11
let capoFret = 0; // 0 .. 12
let showShapesMode = true; // true = shapes to play, false = sounding chords
let suggestedCapoFret = null;
let showGuitarShapes = true;
let followMode = false;
let preferredShapeIndex = {}; // chordName -> index in alternatives
let loopRange = null; // { start, end, label } | null
let nextChordJumpTime = null;
let lastDisplayedCurrentChord = null;
let isSeekingSlider = false;
let playbackRate = 1;

// Key-aware spelling tables (never produce E#, B#, Fb, or Cb)
const NOTE_TO_PC = {
  C: 0, "B#": 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, Fb: 4,
  F: 5, "E#": 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11, Cb: 11,
};
const SHARP_SPELLING = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const FLAT_SPELLING = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
const GUITAR_NEUTRAL_SPELLING = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const OPEN_GUITAR_CHORDS = new Set(["C", "G", "D", "A", "E", "Am", "Em", "Dm"]);
const FLAT_MAJOR_PCS = new Set([5, 10, 3, 8, 1, 6]);
const SHARP_MAJOR_PCS = new Set([7, 2, 9, 4, 11]);

function parseKey(keyStr) {
  if (!keyStr || keyStr === "Unknown") return null;
  const parts = keyStr.trim().split(/\s+/);
  if (parts.length < 2 || NOTE_TO_PC[parts[0]] === undefined) return null;
  return { pc: NOTE_TO_PC[parts[0]], mode: parts[1].toLowerCase() === "minor" ? "minor" : "major" };
}

function getRelativeMajorPc(keyInfo) {
  if (!keyInfo) return 0;
  return keyInfo.mode === "minor" ? (keyInfo.pc + 3) % 12 : keyInfo.pc;
}

function getSpellingForKey(keyStr) {
  const info = parseKey(keyStr);
  if (!info) return GUITAR_NEUTRAL_SPELLING;
  const relMaj = getRelativeMajorPc(info);
  if (FLAT_MAJOR_PCS.has(relMaj)) return FLAT_SPELLING;
  if (SHARP_MAJOR_PCS.has(relMaj)) return SHARP_SPELLING;
  return GUITAR_NEUTRAL_SPELLING;
}

function transposeKey(keyStr, semitones) {
  const info = parseKey(keyStr);
  if (!info) return keyStr || "Unknown";
  const newPc = ((info.pc + semitones) % 12 + 12) % 12;
  const relMaj = info.mode === "minor" ? (newPc + 3) % 12 : newPc;
  const table = FLAT_MAJOR_PCS.has(relMaj)
    ? FLAT_SPELLING
    : SHARP_MAJOR_PCS.has(relMaj)
      ? SHARP_SPELLING
      : GUITAR_NEUTRAL_SPELLING;
  return `${table[newPc]} ${info.mode}`;
}

function transposeSingleToken(token, semitones, spellingTable) {
  const m = token.match(/^([A-G][#b]?)(.*)$/);
  if (!m || NOTE_TO_PC[m[1]] === undefined) return token;
  const pc = ((NOTE_TO_PC[m[1]] + semitones) % 12 + 12) % 12;
  return `${spellingTable[pc]}${m[2]}`;
}

function transposeChord(chord, semitones, targetKeyStr) {
  if (!chord || chord === "N") return chord || "N";
  const table = getSpellingForKey(targetKeyStr);
  if (chord.includes("/")) {
    const [main, bass] = chord.split("/", 2);
    return `${transposeSingleToken(main, semitones, table)}/${transposeSingleToken(bass, semitones, table)}`;
  }
  return transposeSingleToken(chord, semitones, table);
}

function simplifyChord(chord) {
  if (!chord || chord === "N") return chord || "N";
  const match = chord.match(/^([A-G][#b]?)(m(?!aj)|dim|aug)?/);
  if (!match) return chord;
  return `${match[1]}${match[2] || ""}`;
}

function getSoundingChord(rawChord) {
  const origKey = currentAnalysis ? currentAnalysis.key : "C major";
  const soundingKey = transposeKey(origKey, transposeSemitones);
  const full = transposeChord(rawChord, transposeSemitones, soundingKey);
  return chordDetailMode === "simple" ? simplifyChord(full) : full;
}

function getShapeChord(rawChord) {
  const origKey = currentAnalysis ? currentAnalysis.key : "C major";
  const soundingKey = transposeKey(origKey, transposeSemitones);
  const shapeKey = transposeKey(soundingKey, -capoFret);
  const full = transposeChord(rawChord, transposeSemitones - capoFret, shapeKey);
  return chordDetailMode === "simple" ? simplifyChord(full) : full;
}

function getDisplayedChord(rawChord) {
  return showShapesMode && capoFret > 0 ? getShapeChord(rawChord) : getSoundingChord(rawChord);
}

function formatTime(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function setStatus(message, kind = "info") {
  statusBanner.textContent = message;
  statusBanner.className = kind === "error" ? "status-line error" : "status-line";
  statusBanner.hidden = false;
}

function clearStatus() {
  statusBanner.hidden = true;
  statusBanner.textContent = "";
}

function setLoading(isLoading, message = "") {
  uploadBtn.disabled = isLoading;
  urlBtn.disabled = isLoading;
  uploadForm.setAttribute("aria-busy", String(isLoading));
  urlForm.setAttribute("aria-busy", String(isLoading));
  if (isLoading && message) {
    setStatus(message, "info");
  }
}

function updateSettingsDot() {
  const nonDefault =
    chordDetailMode !== "simple" ||
    !showGuitarShapes ||
    !showShapesMode ||
    transposeSemitones !== 0 ||
    capoFret !== 0 ||
    playbackRate !== 1 ||
    loopRange !== null ||
    followMode ||
    showMoreDetail ||
    isEditMode;
  settingsDot.hidden = !nonDefault;
}

function openSettingsDrawer() {
  settingsDrawer.hidden = false;
  settingsBackdrop.hidden = false;
  settingsBtn.setAttribute("aria-expanded", "true");
  settingsCloseBtn.focus();
}

function closeSettingsDrawer() {
  settingsDrawer.hidden = true;
  settingsBackdrop.hidden = true;
  settingsBtn.setAttribute("aria-expanded", "false");
}

function closeExportMenu() {
  exportMenu.hidden = true;
  exportBtn.setAttribute("aria-expanded", "false");
}

function showInputView() {
  audioPlayer.pause();
  closeSettingsDrawer();
  closeExportMenu();
  chordPopover.hidden = true;
  resultsView.hidden = true;
  songSummaryEl.hidden = true;
  inputView.hidden = false;
  newSongBtn.hidden = true;
  exportBtn.disabled = true;
  clearStatus();
}

function updateSongSummary() {
  if (!currentAnalysis) {
    songSummaryEl.hidden = true;
    return;
  }
  const title = currentAnalysis.title || "Analyzed track";
  const soundingKey = transposeKey(currentAnalysis.key || "Unknown", transposeSemitones);
  const tempoText = currentAnalysis.tempo ? `${Math.round(currentAnalysis.tempo)} BPM` : "—";
  const capoSuffix = capoFret > 0 ? ` - Capo ${capoFret}` : "";
  songSummaryEl.textContent = `${title} - ${soundingKey} - ${tempoText}${capoSuffix}`;
  songSummaryEl.hidden = false;
}

function setPlayAlongEnabled(enabled) {
  transposeDownBtn.disabled = !enabled;
  transposeUpBtn.disabled = !enabled;
  transposeResetBtn.disabled = !enabled;
  capoSelect.disabled = !enabled;
  suggestCapoBtn.disabled = !enabled;
  viewShapesBtn.disabled = !enabled;
  editModeBtn.disabled = !enabled;
}

function updatePlayAlongUI() {
  if (!currentAnalysis) {
    setPlayAlongEnabled(false);
    transposeValEl.textContent = "0";
    resultingKeyEl.textContent = "—";
    transposeResetBtn.hidden = true;
    updateSettingsDot();
    return;
  }
  setPlayAlongEnabled(true);
  const origKey = currentAnalysis.key || "Unknown";
  const soundingKey = transposeKey(origKey, transposeSemitones);
  transposeValEl.textContent = transposeSemitones > 0 ? `+${transposeSemitones}` : String(transposeSemitones);
  resultingKeyEl.textContent = soundingKey;
  capoSelect.value = String(capoFret);
  transposeResetBtn.hidden = transposeSemitones === 0 && capoFret === 0;
  viewShapesBtn.setAttribute("aria-pressed", String(showShapesMode));
  viewShapesBtn.textContent = showShapesMode ? "Show: Shapes to play" : "Show: Sounding chords";
  updateSongSummary();
  updateSettingsDot();
}

function renderAnalysis(data) {
  currentAnalysis = data;
  inputView.hidden = true;
  resultsView.hidden = false;
  exportBtn.disabled = false;
  newSongBtn.hidden = false;

  if (audioPlayer.src !== new URL(data.audio_url, window.location.origin).href) {
    audioPlayer.src = data.audio_url;
  }
  audioPlayer.playbackRate = playbackRate;
  audioPlayer.preservesPitch = true;

  const beatChords = data.beat_chords || [];
  const beatsPerBar = 4;
  const totalBars = Math.ceil(beatChords.length / beatsPerBar);

  nowPlayingStrip.hidden = beatChords.length === 0;
  leadSheetEl.hidden = followMode;
  leadSheetEl.classList.toggle("show-details", showMoreDetail);
  followTeleprompter.hidden = !followMode;
  lastActiveBarIdx = -1;
  lastDisplayedCurrentChord = null;

  updatePlayAlongUI();
  renderFollowTeleprompter(0);

  beatNodes = [];
  barNodes = [];
  sectionNodes = [];
  leadSheetEl.innerHTML = "";

  const sections = data.sections || [];
  sectionStripEl.innerHTML = "";
  if (sections.length > 0 && showMoreDetail) {
    sectionStripEl.hidden = false;
    for (const sec of sections) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "section-pill";
      btn.textContent = `${sec.label} (est. · Bars ${sec.bar_start}–${sec.bar_end})`;
      btn.addEventListener("click", () => {
        audioPlayer.currentTime = sec.start;
        if (audioPlayer.paused) {
          audioPlayer.play().catch(() => {});
        }
        updatePlayhead();
      });
      sectionNodes.push({ btn, sec });
      sectionStripEl.appendChild(btn);
    }
  } else {
    sectionStripEl.hidden = true;
  }

  for (let barIdx = 0; barIdx < totalBars; barIdx += 1) {
    const startBeatIdx = barIdx * beatsPerBar;
    const barBeats = beatChords.slice(startBeatIdx, startBeatIdx + beatsPerBar);
    const barStartTime = barBeats[0] ? barBeats[0].start : 0;

    const barCard = document.createElement("div");
    barCard.className = "bar-card";
    barCard.dataset.barIndex = String(barIdx);

    const barHead = document.createElement("div");
    barHead.className = "bar-head";
    barHead.innerHTML = `<span>Bar ${barIdx + 1}</span><span>${formatTime(barStartTime)}</span>`;
    barCard.appendChild(barHead);

    const beatsRow = document.createElement("div");
    beatsRow.className = "bar-beats";

    for (let offset = 0; offset < beatsPerBar; offset += 1) {
      const beat = barBeats[offset];
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "beat-cell";

      if (!beat) {
        cell.disabled = true;
        cell.innerHTML = `<span>—</span>`;
        beatsRow.appendChild(cell);
        continue;
      }

      const prevBeat = beat.beat_index > 0 ? beatChords[beat.beat_index - 1] : null;
      const shownChord = getDisplayedChord(beat.chord);
      const prevShownChord = prevBeat ? getDisplayedChord(prevBeat.chord) : null;
      const isLastBeat = beat.beat_index === beatChords.length - 1;
      const isRepeat = prevShownChord && prevShownChord === shownChord && offset > 0 && !isLastBeat;
      const confPct = Math.round((beat.confidence || 0) * 100);

      cell.setAttribute(
        "aria-label",
        `Bar ${barIdx + 1} beat ${offset + 1}, chord ${shownChord}, confidence ${confPct}%`
      );
      const detailHtml = `<span class="beat-meta">b${offset + 1} · ${beat.edited ? "edited" : `${confPct}%`}</span>`;
      cell.innerHTML = `<span>${isRepeat ? "/" : shownChord}</span>${detailHtml}`;

      cell.addEventListener("click", () => {
        if (isEditMode) {
          openBeatEditor(cell, beat);
          return;
        }
        audioPlayer.currentTime = beat.start;
        if (audioPlayer.paused) {
          audioPlayer.play().catch(() => {});
        }
        updatePlayhead();
      });

      beatNodes[beat.beat_index] = { cell, barIdx, beat };
      beatsRow.appendChild(cell);
    }

    barCard.appendChild(beatsRow);
    barNodes[barIdx] = barCard;
    leadSheetEl.appendChild(barCard);
  }
}

function rebuildChordsFromBeats() {
  if (!currentAnalysis || !currentAnalysis.beat_chords) return;
  const merged = [];
  for (const item of currentAnalysis.beat_chords) {
    const prev = merged[merged.length - 1];
    if (prev && prev.chord === item.chord) {
      prev.end = item.end;
      prev.beat_end = item.beat_index;
      prev._confs.push(item.confidence);
      const avg = prev._confs.reduce((a, b) => a + b, 0) / prev._confs.length;
      prev.confidence = Number(avg.toFixed(3));
      prev.low_confidence = prev.confidence < 0.55;
    } else {
      merged.push({
        start: item.start,
        end: item.end,
        beat_start: item.beat_index,
        beat_end: item.beat_index,
        chord: item.chord,
        confidence: item.confidence,
        low_confidence: item.low_confidence,
        _confs: [item.confidence],
      });
    }
  }
  for (const seg of merged) {
    delete seg._confs;
  }
  currentAnalysis.chords = merged;
}

function openBeatEditor(cell, beat) {
  if (cell.querySelector("input")) return;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "beat-edit-input";
  input.value = beat.chord;
  input.setAttribute("aria-label", `Edit chord for beat ${beat.beat_index + 1}`);

  cell.innerHTML = "";
  cell.appendChild(input);
  input.focus();
  input.select();

  const commit = () => {
    const next = input.value.trim();
    if (next && next !== beat.chord) {
      beat.chord = next;
      beat.confidence = 1.0;
      beat.low_confidence = false;
      beat.edited = true;
      rebuildChordsFromBeats();
    }
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  };

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      renderAnalysis(currentAnalysis);
      updatePlayhead();
    }
  });
  input.addEventListener("blur", commit, { once: true });
}

function downloadTextFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function formatChordSheetText(data) {
  const origKey = data.key || "Unknown";
  const soundingKey = transposeKey(origKey, transposeSemitones);
  const viewDesc = capoFret > 0 && showShapesMode
    ? `Capo ${capoFret} shapes (sounding in ${soundingKey})`
    : `Sounding in ${soundingKey}`;
  const lines = [
    `${data.title || "Untitled"}`,
    `Key: ${soundingKey} | Tempo: ${data.tempo || "—"} BPM | Time: ${data.time_signature || "4/4"} | Transpose: ${transposeSemitones > 0 ? `+${transposeSemitones}` : transposeSemitones} | ${viewDesc}`,
    "",
  ];
  const beats = data.beat_chords || [];
  const sections = data.sections || [];
  const sectionByStartBar = new Map();
  for (const sec of sections) {
    sectionByStartBar.set(sec.bar_start - 1, `${sec.label} (estimated)`);
  }

  const beatsPerBar = 4;
  const totalBars = Math.ceil(beats.length / beatsPerBar);
  let row = [];

  for (let b = 0; b < totalBars; b += 1) {
    if (sectionByStartBar.has(b)) {
      if (row.length > 0) {
        lines.push(row.join("") + "|");
        row = [];
      }
      if (lines[lines.length - 1] !== "") lines.push("");
      lines.push(`[${sectionByStartBar.get(b)}]`);
    }
    const barBeats = beats.slice(b * beatsPerBar, (b + 1) * beatsPerBar);
    const tokens = barBeats.map((item, idx) => {
      const prev = item.beat_index > 0 ? beats[item.beat_index - 1] : null;
      const shown = getDisplayedChord(item.chord);
      const prevShown = prev ? getDisplayedChord(prev.chord) : null;
      return prevShown && prevShown === shown && idx > 0 ? "/" : shown;
    });
    row.push(`| ${tokens.join(" ")} `);
    if (row.length === 4 || b === totalBars - 1) {
      lines.push(row.join("") + "|");
      row = [];
    }
  }
  return lines.join("\n");
}

function getActiveShapeForChord(chordName) {
  if (!window.ChordShapes || !chordName || chordName === "N") {
    return { shape: null, alternatives: [], simplified: false, notes: [] };
  }
  const opts = window.ChordShapes.getChordShapeOptions(chordName);
  const idx = preferredShapeIndex[chordName] || 0;
  const shape = opts.alternatives[idx] || opts.primary;
  return { shape, alternatives: opts.alternatives, simplified: opts.simplified, notes: opts.notes };
}

function renderDiagramInto(container, chordName, compact) {
  if (!container) return;
  if (!showGuitarShapes || !window.ChordShapes || !chordName || chordName === "N") {
    container.innerHTML = "";
    container.hidden = true;
    return;
  }
  const { shape } = getActiveShapeForChord(chordName);
  if (!shape) {
    container.innerHTML = "";
    container.hidden = true;
    return;
  }
  const activeCapo = showShapesMode ? capoFret : 0;
  container.innerHTML = window.ChordShapes.renderChordDiagramSvg(chordName, shape, {
    capoFret: activeCapo,
    compact,
  });
  container.hidden = false;
}

function openChordPopover(chordName) {
  if (!chordName || chordName === "N" || !window.ChordShapes) return;
  const { alternatives, simplified, notes } = getActiveShapeForChord(chordName);
  popoverTitle.textContent = simplified ? `${chordName} (simplified shape)` : chordName;
  popoverNotes.textContent = notes.length ? `Notes: ${notes.join(" · ")}` : "";
  popoverShapes.innerHTML = "";

  const currentIdx = preferredShapeIndex[chordName] || 0;
  const activeCapo = showShapesMode ? capoFret : 0;

  alternatives.forEach((shape, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-secondary popover-shape-card";
    btn.setAttribute("aria-pressed", String(idx === currentIdx));
    btn.innerHTML = `
      ${window.ChordShapes.renderChordDiagramSvg(chordName, shape, { capoFret: activeCapo, compact: true })}
      <span>${shape.label || `Shape ${idx + 1}`}</span>
    `;
    btn.addEventListener("click", () => {
      preferredShapeIndex[chordName] = idx;
      lastDisplayedCurrentChord = null;
      updatePlayhead();
      openChordPopover(chordName);
    });
    popoverShapes.appendChild(btn);
  });

  chordPopover.hidden = false;
}

function renderFollowTeleprompter(currentBarIdx) {
  if (!followMode || !currentAnalysis || !currentAnalysis.beat_chords) return;
  const beats = currentAnalysis.beat_chords;
  const totalBars = Math.ceil(beats.length / 4);
  followTeleprompter.innerHTML = "";

  const startBar = Math.max(0, currentBarIdx - 1);
  const row = document.createElement("div");
  row.className = "follow-row";

  for (let offset = 0; offset < 4; offset += 1) {
    const bIdx = startBar + offset;
    if (bIdx >= totalBars) break;
    const barBeats = beats.slice(bIdx * 4, bIdx * 4 + 4);
    const tokens = barBeats.map((item, idx) => {
      const prev = item.beat_index > 0 ? beats[item.beat_index - 1] : null;
      const shown = getDisplayedChord(item.chord);
      const prevShown = prev ? getDisplayedChord(prev.chord) : null;
      return prevShown && prevShown === shown && idx > 0 ? "/" : shown;
    });

    const card = document.createElement("div");
    card.className = `bar-card ${bIdx < currentBarIdx ? "played" : ""} ${bIdx === currentBarIdx ? "active" : ""}`;
    card.innerHTML = `<div class="bar-beats"><span class="beat-cell">${tokens.join(" · ")}</span></div>`;
    row.appendChild(card);
  }
  followTeleprompter.appendChild(row);
}

function scrollBarIntoView(barEl) {
  if (!barEl) return;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  isProgrammaticScroll = true;
  barEl.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
  window.setTimeout(() => {
    isProgrammaticScroll = false;
  }, 400);
}

function jumpByBars(delta) {
  if (!currentAnalysis || !currentAnalysis.beat_chords || !currentAnalysis.beat_chords.length) return;
  const totalBars = Math.ceil(currentAnalysis.beat_chords.length / 4);
  const curBar = lastActiveBarIdx < 0 ? 0 : lastActiveBarIdx;
  const targetBar = Math.max(0, Math.min(totalBars - 1, curBar + delta));
  const targetBeat = currentAnalysis.beat_chords[targetBar * 4];
  if (targetBeat) {
    audioPlayer.currentTime = targetBeat.start;
    updatePlayhead();
    if (!followMode && barNodes[targetBar]) {
      scrollBarIntoView(barNodes[targetBar]);
    }
  }
}

function updatePlayhead() {
  if (!currentAnalysis || !currentAnalysis.beat_chords) return;
  const t = audioPlayer.currentTime;
  if (loopRange && !audioPlayer.paused && t >= loopRange.end) {
    audioPlayer.currentTime = loopRange.start;
  }

  const curT = audioPlayer.currentTime;
  const dur = audioPlayer.duration || currentAnalysis.duration || 0;
  npTimeReadout.textContent = `${formatTime(curT)} / ${formatTime(dur)}`;
  npPlayBtn.textContent = audioPlayer.paused ? "Play" : "Pause";
  if (!isSeekingSlider && dur > 0) {
    npSeekSlider.value = String(Math.round((curT / dur) * 1000));
  }

  const beats = currentAnalysis.beat_chords;
  let activeBeatIdx = -1;
  for (let i = 0; i < beats.length; i += 1) {
    if (curT >= beats[i].start && curT < beats[i].end) {
      activeBeatIdx = i;
      break;
    }
  }
  if (activeBeatIdx === -1 && beats.length > 0 && curT >= beats[beats.length - 1].start) {
    activeBeatIdx = beats.length - 1;
  }

  for (const node of beatNodes) {
    if (node) node.cell.classList.remove("active");
  }
  for (let bIdx = 0; bIdx < barNodes.length; bIdx += 1) {
    if (barNodes[bIdx]) {
      barNodes[bIdx].classList.remove("active", "played");
    }
  }

  if (activeBeatIdx >= 0 && beatNodes[activeBeatIdx]) {
    const { cell, barIdx, beat } = beatNodes[activeBeatIdx];
    cell.classList.add("active");
    if (barNodes[barIdx]) {
      barNodes[barIdx].classList.add("active");
    }
    for (let bIdx = 0; bIdx < barIdx; bIdx += 1) {
      if (barNodes[bIdx]) barNodes[bIdx].classList.add("played");
    }

    const beatInBar = activeBeatIdx % 4;
    npBeatDots.forEach((dot, idx) => dot.classList.toggle("active", idx === beatInBar));
    const barStartBeat = beats[barIdx * 4];
    const barEndBeat = beats[Math.min(beats.length - 1, barIdx * 4 + 3)];
    const barStart = barStartBeat ? barStartBeat.start : 0;
    const barEnd = barEndBeat ? barEndBeat.end : curT + 1;
    const pct = Math.max(0, Math.min(100, ((curT - barStart) / Math.max(0.1, barEnd - barStart)) * 100));
    npBarProgress.style.width = `${pct.toFixed(1)}%`;

    const curShown = getDisplayedChord(beat.chord);
    nowPlayingChordEl.textContent = curShown;
    if (curShown !== lastDisplayedCurrentChord) {
      lastDisplayedCurrentChord = curShown;
      const shapeInfo = getActiveShapeForChord(curShown);
      npSimplifiedTag.hidden = !shapeInfo.simplified;
      renderDiagramInto(npCurrentDiagram, curShown, false);
    }

    let nextChord = null;
    let beatsUntil = 0;
    nextChordJumpTime = null;
    for (let j = activeBeatIdx + 1; j < beats.length; j += 1) {
      const cand = getDisplayedChord(beats[j].chord);
      if (cand !== curShown) {
        nextChord = cand;
        beatsUntil = j - activeBeatIdx;
        nextChordJumpTime = beats[j].start;
        break;
      }
    }

    if (nextChord) {
      nowPlayingNextChordEl.textContent = nextChord;
      nowPlayingCountdownEl.textContent = `in ${beatsUntil} beat${beatsUntil === 1 ? "" : "s"}`;
    } else {
      nowPlayingNextChordEl.textContent = "End";
      nowPlayingCountdownEl.textContent = "";
    }

    if (barIdx !== lastActiveBarIdx) {
      lastActiveBarIdx = barIdx;
      renderFollowTeleprompter(barIdx);
      if (!followMode && autoScrollEnabled && !audioPlayer.paused && barNodes[barIdx]) {
        scrollBarIntoView(barNodes[barIdx]);
      }
    }
  } else if (beats.length > 0) {
    const firstChord = getDisplayedChord(beats[0].chord);
    nowPlayingChordEl.textContent = firstChord;
    nowPlayingNextChordEl.textContent = "—";
    nowPlayingCountdownEl.textContent = "";
    npBeatDots.forEach((dot) => dot.classList.remove("active"));
    npBarProgress.style.width = "0%";
    if (firstChord !== lastDisplayedCurrentChord) {
      lastDisplayedCurrentChord = firstChord;
      const shapeInfo = getActiveShapeForChord(firstChord);
      npSimplifiedTag.hidden = !shapeInfo.simplified;
      renderDiagramInto(npCurrentDiagram, firstChord, false);
    }
  }

  for (const node of sectionNodes) {
    const active = curT >= node.sec.start && curT < node.sec.end;
    node.btn.classList.toggle("active", active);
  }
}

// Top bar & menus
brandHomeBtn.addEventListener("click", (event) => {
  event.preventDefault();
  if (currentAnalysis) {
    showInputView();
  }
});

newSongBtn.addEventListener("click", showInputView);

settingsBtn.addEventListener("click", () => {
  closeExportMenu();
  if (settingsDrawer.hidden) {
    openSettingsDrawer();
  } else {
    closeSettingsDrawer();
  }
});

settingsCloseBtn.addEventListener("click", closeSettingsDrawer);
settingsBackdrop.addEventListener("click", closeSettingsDrawer);

exportBtn.addEventListener("click", () => {
  if (exportBtn.disabled) return;
  const willOpen = exportMenu.hidden;
  exportMenu.hidden = !willOpen;
  exportBtn.setAttribute("aria-expanded", String(willOpen));
});

document.addEventListener("click", (event) => {
  if (!exportMenu.hidden && !event.target.closest(".export-menu-wrap")) {
    closeExportMenu();
  }
});

exportTxtBtn.addEventListener("click", () => {
  closeExportMenu();
  if (!currentAnalysis) return;
  const slug = (currentAnalysis.title || "chordlens").replace(/[^a-z0-9-_]+/gi, "-").toLowerCase();
  downloadTextFile(`${slug}-chord-sheet.txt`, formatChordSheetText(currentAnalysis), "text/plain");
});

exportJsonBtn.addEventListener("click", () => {
  closeExportMenu();
  if (!currentAnalysis) return;
  const origKey = currentAnalysis.key || "Unknown";
  const payload = {
    ...currentAnalysis,
    transpose_semitones: transposeSemitones,
    capo_fret: capoFret,
    sounding_key: transposeKey(origKey, transposeSemitones),
    beat_chords: (currentAnalysis.beat_chords || []).map((b) => ({
      ...b,
      sounding_chord: getSoundingChord(b.chord),
      shape_chord: getShapeChord(b.chord),
    })),
  };
  const slug = (currentAnalysis.title || "chordlens").replace(/[^a-z0-9-_]+/gi, "-").toLowerCase();
  downloadTextFile(`${slug}-chords.json`, JSON.stringify(payload, null, 2), "application/json");
});

// Input options toggle
inputOptionsBtn.addEventListener("click", () => {
  const willOpen = inputOptionsPanel.hidden;
  inputOptionsPanel.hidden = !willOpen;
  inputOptionsBtn.setAttribute("aria-expanded", String(willOpen));
});

// Settings controls
chordDetailBtn.addEventListener("click", () => {
  chordDetailMode = chordDetailMode === "simple" ? "full" : "simple";
  const isFull = chordDetailMode === "full";
  chordDetailBtn.setAttribute("aria-pressed", String(isFull));
  chordDetailBtn.textContent = isFull ? "Chords: Full" : "Chords: Simple";
  updateSettingsDot();
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  }
});

guitarShapesBtn.addEventListener("click", () => {
  showGuitarShapes = !showGuitarShapes;
  guitarShapesBtn.setAttribute("aria-pressed", String(showGuitarShapes));
  guitarShapesBtn.textContent = showGuitarShapes ? "Guitar shapes: On" : "Guitar shapes: Off";
  lastDisplayedCurrentChord = null;
  updateSettingsDot();
  updatePlayhead();
});

viewShapesBtn.addEventListener("click", () => {
  showShapesMode = !showShapesMode;
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  } else {
    updatePlayAlongUI();
  }
});

transposeDownBtn.addEventListener("click", () => {
  if (transposeSemitones > -11) {
    transposeSemitones -= 1;
    capoSuggestionBox.hidden = true;
    if (currentAnalysis) {
      renderAnalysis(currentAnalysis);
      updatePlayhead();
    }
  }
});

transposeUpBtn.addEventListener("click", () => {
  if (transposeSemitones < 11) {
    transposeSemitones += 1;
    capoSuggestionBox.hidden = true;
    if (currentAnalysis) {
      renderAnalysis(currentAnalysis);
      updatePlayhead();
    }
  }
});

transposeResetBtn.addEventListener("click", () => {
  transposeSemitones = 0;
  capoFret = 0;
  capoSuggestionBox.hidden = true;
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  }
});

capoSelect.addEventListener("change", () => {
  capoFret = Number(capoSelect.value) || 0;
  capoSuggestionBox.hidden = true;
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  }
});

suggestCapoBtn.addEventListener("click", () => {
  if (!currentAnalysis || !currentAnalysis.beat_chords) return;
  const origKey = currentAnalysis.key || "C major";
  const soundingKey = transposeKey(origKey, transposeSemitones);
  const beats = currentAnalysis.beat_chords;

  let bestFret = 0;
  let bestScore = -1;
  let bestPreview = [];

  for (let fret = 0; fret <= 7; fret += 1) {
    const shapeKey = transposeKey(soundingKey, -fret);
    let openCount = 0;
    const uniqueShapes = [];
    for (const b of beats) {
      const shape = simplifyChord(transposeChord(b.chord, transposeSemitones - fret, shapeKey));
      if (OPEN_GUITAR_CHORDS.has(shape)) {
        openCount += 1;
      }
      if (shape !== "N" && !uniqueShapes.includes(shape) && uniqueShapes.length < 4) {
        uniqueShapes.push(shape);
      }
    }
    if (openCount > bestScore) {
      bestScore = openCount;
      bestFret = fret;
      bestPreview = uniqueShapes;
    }
  }

  suggestedCapoFret = bestFret;
  const pct = beats.length > 0 ? Math.round((bestScore / beats.length) * 100) : 0;
  const label = bestFret === 0 ? "No capo" : `Capo ${bestFret}`;
  capoSuggestionText.textContent = `${label}: ${bestPreview.join(", ")} (${pct}% open)`;
  applyCapoBtn.textContent = `Apply ${label}`;
  capoSuggestionBox.hidden = false;
});

applyCapoBtn.addEventListener("click", () => {
  if (suggestedCapoFret === null) return;
  capoFret = suggestedCapoFret;
  showShapesMode = true;
  capoSuggestionBox.hidden = true;
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  }
});

speedBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    playbackRate = Number(btn.dataset.speed) || 1;
    audioPlayer.playbackRate = playbackRate;
    audioPlayer.preservesPitch = true;
    speedBtns.forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
    updateSettingsDot();
  });
});

npLoopBtn.addEventListener("click", () => {
  if (loopRange) {
    loopRange = null;
    npLoopBtn.setAttribute("aria-pressed", "false");
    npLoopBtn.textContent = "Loop 4 bars";
    updateSettingsDot();
    return;
  }
  if (!currentAnalysis || !currentAnalysis.beat_chords || !currentAnalysis.beat_chords.length) return;
  const beats = currentAnalysis.beat_chords;
  const curBar = lastActiveBarIdx < 0 ? 0 : lastActiveBarIdx;
  const startBar = Math.floor(curBar / 4) * 4;
  const startBeatIdx = startBar * 4;
  const endBeatIdx = Math.min(beats.length - 1, startBeatIdx + 15);
  loopRange = {
    start: beats[startBeatIdx].start,
    end: beats[endBeatIdx].end,
    label: `Bars ${startBar + 1}–${Math.min(Math.ceil(beats.length / 4), startBar + 4)}`,
  };
  npLoopBtn.textContent = `Loop off (${loopRange.label})`;
  npLoopBtn.setAttribute("aria-pressed", "true");
  updateSettingsDot();
});

followModeBtn.addEventListener("click", () => {
  followMode = !followMode;
  followModeBtn.setAttribute("aria-pressed", String(followMode));
  leadSheetEl.hidden = followMode;
  followTeleprompter.hidden = !followMode;
  renderFollowTeleprompter(lastActiveBarIdx < 0 ? 0 : lastActiveBarIdx);
  updateSettingsDot();
});

moreDetailBtn.addEventListener("click", () => {
  showMoreDetail = !showMoreDetail;
  moreDetailBtn.setAttribute("aria-pressed", String(showMoreDetail));
  updateSettingsDot();
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  }
});

editModeBtn.addEventListener("click", () => {
  isEditMode = !isEditMode;
  editModeBtn.setAttribute("aria-pressed", String(isEditMode));
  updateSettingsDot();
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  }
});

// Now playing & chart interactions
npCurrentBtn.addEventListener("click", () => {
  if (lastDisplayedCurrentChord) {
    openChordPopover(lastDisplayedCurrentChord);
  }
});

npNextBtn.addEventListener("click", () => {
  if (nextChordJumpTime !== null) {
    audioPlayer.currentTime = nextChordJumpTime;
    if (audioPlayer.paused) audioPlayer.play().catch(() => {});
    updatePlayhead();
  }
});

popoverCloseBtn.addEventListener("click", () => {
  chordPopover.hidden = true;
});

npPlayBtn.addEventListener("click", () => {
  if (audioPlayer.paused) {
    audioPlayer.play().catch(() => {});
  } else {
    audioPlayer.pause();
  }
});

npSeekSlider.addEventListener("input", () => {
  isSeekingSlider = true;
  if (audioPlayer.duration && !Number.isNaN(audioPlayer.duration)) {
    audioPlayer.currentTime = (Number(npSeekSlider.value) / 1000) * audioPlayer.duration;
    updatePlayhead();
  }
});

npSeekSlider.addEventListener("change", () => {
  isSeekingSlider = false;
});

jumpToBarBtn.addEventListener("click", () => {
  autoScrollEnabled = true;
  jumpToBarBtn.hidden = true;
  if (lastActiveBarIdx >= 0 && barNodes[lastActiveBarIdx]) {
    scrollBarIntoView(barNodes[lastActiveBarIdx]);
  }
});

window.addEventListener("scroll", () => {
  if (!isProgrammaticScroll && !audioPlayer.paused && currentAnalysis && !resultsView.hidden) {
    autoScrollEnabled = false;
    jumpToBarBtn.hidden = false;
  }
}, { passive: true });

document.addEventListener("keydown", (event) => {
  if (event.code === "Escape") {
    if (!exportMenu.hidden) {
      closeExportMenu();
      return;
    }
    if (!settingsDrawer.hidden) {
      closeSettingsDrawer();
      return;
    }
    if (!chordPopover.hidden) {
      chordPopover.hidden = true;
      return;
    }
  }
  const tag = (event.target && event.target.tagName) ? event.target.tagName.toLowerCase() : "";
  if (tag === "input" || tag === "textarea" || tag === "select") return;
  if (!currentAnalysis || !currentAnalysis.beat_chords || currentAnalysis.beat_chords.length === 0) return;

  if (event.code === "Space" && tag !== "button") {
    event.preventDefault();
    if (audioPlayer.paused) {
      audioPlayer.play().catch(() => {});
    } else {
      audioPlayer.pause();
    }
  } else if (event.code === "ArrowLeft" || event.code === "ArrowRight") {
    event.preventDefault();
    jumpByBars(event.code === "ArrowRight" ? 1 : -1);
  }
});

function startPlayheadLoop() {
  if (rafId !== null) return;
  const tick = () => {
    updatePlayhead();
    if (!audioPlayer.paused && !audioPlayer.ended) {
      rafId = requestAnimationFrame(tick);
    } else {
      rafId = null;
    }
  };
  rafId = requestAnimationFrame(tick);
}

audioPlayer.addEventListener("play", startPlayheadLoop);
audioPlayer.addEventListener("pause", updatePlayhead);
audioPlayer.addEventListener("timeupdate", updatePlayhead);
audioPlayer.addEventListener("seeked", updatePlayhead);

function getSelectedMode() {
  const checked = document.querySelector('input[name="analysis-mode"]:checked');
  return checked ? checked.value : "fast";
}

async function pollJobUntilDone(jobId) {
  while (true) {
    const res = await fetch(`/api/jobs/${jobId}`);
    const job = await res.json();
    if (!res.ok) {
      throw new Error(job.detail || "Lost track of analysis job.");
    }
    if (job.status === "done") {
      return job.result;
    }
    if (job.status === "error") {
      throw new Error(job.error || "Analysis failed.");
    }
    if (job.stage) {
      setStatus(job.stage, "info");
    }
    await new Promise((resolve) => setTimeout(resolve, 750));
  }
}

function handleAnalysisResult(data) {
  renderAnalysis(data);
  const lastEnd = data.chords && data.chords.length ? data.chords[data.chords.length - 1].end : 0;
  if (data.duration > 5 && lastEnd < data.duration - 3.0) {
    setStatus(
      `Analysis stopped early at ${formatTime(lastEnd)} of ${formatTime(data.duration)}. Try converting the file to WAV and re-uploading.`,
      "error"
    );
  } else {
    clearStatus();
  }
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = audioFileInput.files[0];
  if (!file) {
    setStatus("Choose an MP3, WAV, M4A, or FLAC file first.", "error");
    return;
  }

  const mode = getSelectedMode();
  clearStatus();
  setLoading(
    true,
    mode === "accurate"
      ? `Analyzing "${file.name}" (Accurate mode)...`
      : `Analyzing "${file.name}"...`
  );

  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("mode", mode);
    const res = await fetch("/api/jobs/analyze", { method: "POST", body: formData });
    const startData = await res.json();
    if (!res.ok) {
      throw new Error(startData.detail || "Could not start analysis.");
    }
    const data = await pollJobUntilDone(startData.job_id);
    handleAnalysisResult(data);
  } catch (err) {
    setStatus(err.message || "Upload failed. Check the file and try again.", "error");
  } finally {
    setLoading(false);
  }
});

urlForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = youtubeUrlInput.value.trim();
  if (!url) {
    setStatus("Paste a YouTube link first.", "error");
    return;
  }

  const mode = getSelectedMode();
  clearStatus();
  setLoading(true, `Analyzing YouTube link (${mode} mode)...`);

  try {
    const res = await fetch("/api/jobs/analyze-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, mode }),
    });
    const startData = await res.json();
    if (!res.ok) {
      throw new Error(startData.detail || "Could not start YouTube analysis.");
    }
    const data = await pollJobUntilDone(startData.job_id);
    handleAnalysisResult(data);
  } catch (err) {
    setStatus(err.message || "YouTube analysis failed. Check the link and try again.", "error");
  } finally {
    setLoading(false);
  }
});
