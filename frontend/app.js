const uploadForm = document.getElementById("upload-form");
const urlForm = document.getElementById("url-form");
const audioFileInput = document.getElementById("audio-file");
const youtubeUrlInput = document.getElementById("youtube-url");
const uploadBtn = document.getElementById("upload-btn");
const urlBtn = document.getElementById("url-btn");
const statusBanner = document.getElementById("status-banner");

const playerPanel = document.getElementById("player-panel");
const trackTitleEl = document.getElementById("track-title");
const pipelineBadgeEl = document.getElementById("pipeline-badge");
const audioPlayer = document.getElementById("audio-player");
const metaKeyEl = document.getElementById("meta-key");
const metaTempoEl = document.getElementById("meta-tempo");
const metaTimeEl = document.getElementById("meta-time");
const metaDurationEl = document.getElementById("meta-duration");
const metaBeatEngineEl = document.getElementById("meta-beat-engine");

const chartSubtitle = document.getElementById("chart-subtitle");
const chartEmpty = document.getElementById("chart-empty");
const sectionStripEl = document.getElementById("section-strip");
const leadSheetEl = document.getElementById("lead-sheet");
const chartToolbar = document.getElementById("chart-toolbar");
const chordDetailBtn = document.getElementById("chord-detail-btn");
const moreDetailBtn = document.getElementById("more-detail-btn");
const editModeBtn = document.getElementById("edit-mode-btn");
const exportJsonBtn = document.getElementById("export-json-btn");
const exportTxtBtn = document.getElementById("export-txt-btn");

const nowPlayingStrip = document.getElementById("now-playing-strip");
const nowPlayingChordEl = document.getElementById("now-playing-chord");
const nowPlayingNextChordEl = document.getElementById("now-playing-next-chord");
const nowPlayingCountdownEl = document.getElementById("now-playing-countdown");
const jumpToBarBtn = document.getElementById("jump-to-bar-btn");

const playAlongPanel = document.getElementById("play-along-panel");
const transposeDownBtn = document.getElementById("transpose-down-btn");
const transposeUpBtn = document.getElementById("transpose-up-btn");
const transposeValEl = document.getElementById("transpose-val");
const transposeResetBtn = document.getElementById("transpose-reset-btn");
const resultingKeyEl = document.getElementById("resulting-key");
const capoSelect = document.getElementById("capo-select");
const suggestCapoBtn = document.getElementById("suggest-capo-btn");
const viewShapesBtn = document.getElementById("view-shapes-btn");
const capoSuggestionBox = document.getElementById("capo-suggestion");
const capoSuggestionText = document.getElementById("capo-suggestion-text");
const applyCapoBtn = document.getElementById("apply-capo-btn");
const playAlongSummaryEl = document.getElementById("play-along-summary");

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

// Key-aware spelling tables (never produce E#, B#, Fb, or Cb)
const NOTE_TO_PC = {
  C: 0, "B#": 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, Fb: 4,
  F: 5, "E#": 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11, Cb: 11,
};
const SHARP_SPELLING = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const FLAT_SPELLING = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
const GUITAR_NEUTRAL_SPELLING = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const OPEN_GUITAR_CHORDS = new Set(["C", "G", "D", "A", "E", "Am", "Em", "Dm"]);

// Relative major pitch classes for flat keys: F(5), Bb(10), Eb(3), Ab(8), Db(1), Gb(6)
const FLAT_MAJOR_PCS = new Set([5, 10, 3, 8, 1, 6]);
const SHARP_MAJOR_PCS = new Set([7, 2, 9, 4, 11]); // G, D, A, E, B

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
  statusBanner.className = "status-banner";
  if (kind === "error") statusBanner.classList.add("is-error");
  if (kind === "success") statusBanner.classList.add("is-success");
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

function renderAnalysis(data) {
  currentAnalysis = data;

  trackTitleEl.textContent = data.title || "Analyzed track";
  pipelineBadgeEl.textContent = data.pipeline || "phase1";
  metaKeyEl.textContent = data.key || "Unknown";
  metaTempoEl.textContent = data.tempo ? `${data.tempo} BPM` : "—";
  metaTimeEl.textContent = data.time_signature || "4/4";
  metaDurationEl.textContent = formatTime(data.duration || 0);
  const estCount = data.beats_estimated || 0;
  const engineLabel = data.beat_engine || "beat_this";
  metaBeatEngineEl.textContent = estCount > 0 ? `${engineLabel} (+${estCount} filled)` : engineLabel;

  audioPlayer.src = data.audio_url;
  playerPanel.hidden = false;

  const beatChords = data.beat_chords || [];
  const chords = data.chords || [];
  const beatsPerBar = 4;
  const totalBars = Math.ceil(beatChords.length / beatsPerBar);
  const lastChord = chords.length > 0 ? chords[chords.length - 1] : null;
  const endsSummary = lastChord ? ` · Ends on ${lastChord.chord} (${formatTime(lastChord.end)})` : "";

  chartSubtitle.textContent = `${totalBars} bars · ${beatChords.length} beats${endsSummary} · Click any beat to ${isEditMode ? "edit" : "jump"}`;
  chartEmpty.hidden = true;
  chartToolbar.hidden = false;
  playAlongPanel.hidden = beatChords.length === 0;
  nowPlayingStrip.hidden = beatChords.length === 0;
  leadSheetEl.hidden = false;
  leadSheetEl.innerHTML = "";
  lastActiveBarIdx = -1;
  updatePlayAlongUI();

  beatNodes = [];
  barNodes = [];
  sectionNodes = [];

  const sections = data.sections || [];
  sectionStripEl.innerHTML = "";
  if (sections.length > 0 && showMoreDetail) {
    sectionStripEl.hidden = false;
    for (const sec of sections) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "section-band";
      btn.innerHTML = `
        <span class="section-band-title">${sec.label} (estimated)</span>
        <span class="section-band-meta">Bars ${sec.bar_start}–${sec.bar_end} · ${formatTime(sec.start)}</span>
      `;
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
        cell.innerHTML = `<span class="beat-chord is-repeat">—</span>`;
        beatsRow.appendChild(cell);
        continue;
      }

      const prevBeat = beat.beat_index > 0 ? beatChords[beat.beat_index - 1] : null;
      const shownChord = getDisplayedChord(beat.chord);
      const prevShownChord = prevBeat ? getDisplayedChord(prevBeat.chord) : null;
      const isLastBeat = beat.beat_index === beatChords.length - 1;
      const isRepeat = prevShownChord && prevShownChord === shownChord && offset > 0 && !isLastBeat;
      const confPct = Math.round((beat.confidence || 0) * 100);

      if (beat.low_confidence) {
        cell.classList.add("is-low");
      }
      if (beat.edited) {
        cell.classList.add("is-edited");
      }

      cell.setAttribute(
        "aria-label",
        `Bar ${barIdx + 1} beat ${offset + 1}, chord ${shownChord}, model confidence ${confPct}%${beat.low_confidence ? ", low model confidence" : ""}`
      );
      cell.title = `Model confidence: ${confPct}%`;
      const detailHtml = showMoreDetail
        ? `<span class="beat-conf">b${offset + 1} · ${beat.edited ? "edited" : `${confPct}%${beat.low_confidence ? " ?" : ""}`}</span>`
        : "";
      cell.innerHTML = `
        <span class="beat-chord ${isRepeat ? "is-repeat" : ""}">${isRepeat ? "/" : shownChord}</span>
        ${detailHtml}
      `;

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
  };

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      renderAnalysis(currentAnalysis);
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

chordDetailBtn.addEventListener("click", () => {
  chordDetailMode = chordDetailMode === "simple" ? "full" : "simple";
  const isFull = chordDetailMode === "full";
  chordDetailBtn.setAttribute("aria-pressed", String(isFull));
  chordDetailBtn.textContent = isFull ? "Chords: Full" : "Chords: Simple";
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  }
});

moreDetailBtn.addEventListener("click", () => {
  showMoreDetail = !showMoreDetail;
  moreDetailBtn.setAttribute("aria-pressed", String(showMoreDetail));
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
    updatePlayhead();
  }
});

jumpToBarBtn.addEventListener("click", () => {
  autoScrollEnabled = true;
  jumpToBarBtn.hidden = true;
  if (lastActiveBarIdx >= 0 && barNodes[lastActiveBarIdx]) {
    scrollBarIntoView(barNodes[lastActiveBarIdx]);
  }
});

editModeBtn.addEventListener("click", () => {
  isEditMode = !isEditMode;
  editModeBtn.setAttribute("aria-pressed", String(isEditMode));
  editModeBtn.textContent = isEditMode ? "Done editing" : "Edit chords";
  if (currentAnalysis) {
    renderAnalysis(currentAnalysis);
  }
});

exportJsonBtn.addEventListener("click", () => {
  if (!currentAnalysis) return;
  const origKey = currentAnalysis.key || "C major";
  const soundingKey = transposeKey(origKey, transposeSemitones);
  const shapeKey = transposeKey(soundingKey, -capoFret);
  const payload = {
    ...currentAnalysis,
    transpose: transposeSemitones,
    capo: capoFret,
    show_mode: showShapesMode ? "shapes" : "sounding",
    chord_detail: chordDetailMode,
    sounding_key: soundingKey,
    shape_key: shapeKey,
    beat_chords: (currentAnalysis.beat_chords || []).map((b) => ({
      ...b,
      sounding_chord: getSoundingChord(b.chord),
      shape_chord: getShapeChord(b.chord),
    })),
  };
  const slug = (currentAnalysis.title || "chordlens").replace(/[^a-z0-9-_]+/gi, "-").toLowerCase();
  downloadTextFile(`${slug}-chords.json`, JSON.stringify(payload, null, 2), "application/json");
});

function updatePlayAlongUI() {
  const origKey = currentAnalysis ? currentAnalysis.key : "Unknown";
  const soundingKey = transposeKey(origKey, transposeSemitones);
  transposeValEl.textContent = transposeSemitones > 0 ? `+${transposeSemitones}` : String(transposeSemitones);
  resultingKeyEl.textContent = `Key: ${soundingKey}`;
  capoSelect.value = String(capoFret);
  viewShapesBtn.setAttribute("aria-pressed", String(showShapesMode));
  viewShapesBtn.textContent = showShapesMode ? "Show: Shapes to play" : "Show: Sounding chords";

  if (capoFret > 0 && showShapesMode) {
    playAlongSummaryEl.textContent = `Capo ${capoFret}: play these shapes. They sound in ${soundingKey}.`;
  } else if (capoFret > 0) {
    playAlongSummaryEl.textContent = `Capo ${capoFret} active, showing sounding chords in ${soundingKey}.`;
  } else {
    playAlongSummaryEl.textContent = `No capo: showing chords in ${soundingKey}.`;
  }
}

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

viewShapesBtn.addEventListener("click", () => {
  showShapesMode = !showShapesMode;
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
  capoSuggestionText.textContent = `${label} gives ${bestPreview.join(", ")} (${pct}% open chords).`;
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

exportTxtBtn.addEventListener("click", () => {
  if (!currentAnalysis) return;
  const slug = (currentAnalysis.title || "chordlens").replace(/[^a-z0-9-_]+/gi, "-").toLowerCase();
  downloadTextFile(`${slug}-chord-sheet.txt`, formatChordSheetText(currentAnalysis), "text/plain");
});

function scrollBarIntoView(barEl) {
  if (!barEl) return;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  isProgrammaticScroll = true;
  barEl.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
  window.setTimeout(() => {
    isProgrammaticScroll = false;
  }, 400);
}

window.addEventListener("scroll", () => {
  if (!isProgrammaticScroll && !audioPlayer.paused && currentAnalysis) {
    autoScrollEnabled = false;
    jumpToBarBtn.hidden = false;
  }
}, { passive: true });

function updatePlayhead() {
  if (!currentAnalysis || !currentAnalysis.beat_chords) return;
  const t = audioPlayer.currentTime;
  const beats = currentAnalysis.beat_chords;

  let activeBeatIdx = -1;
  for (let i = 0; i < beats.length; i += 1) {
    if (t >= beats[i].start && t < beats[i].end) {
      activeBeatIdx = i;
      break;
    }
  }
  if (activeBeatIdx === -1 && beats.length > 0 && t >= beats[beats.length - 1].start) {
    activeBeatIdx = beats.length - 1;
  }

  for (const node of beatNodes) {
    if (node) node.cell.classList.remove("is-active");
  }
  for (let bIdx = 0; bIdx < barNodes.length; bIdx += 1) {
    if (barNodes[bIdx]) {
      barNodes[bIdx].classList.remove("is-active", "is-played");
    }
  }

  if (activeBeatIdx >= 0 && beatNodes[activeBeatIdx]) {
    const { cell, barIdx, beat } = beatNodes[activeBeatIdx];
    cell.classList.add("is-active");
    if (barNodes[barIdx]) {
      barNodes[barIdx].classList.add("is-active");
    }
    for (let bIdx = 0; bIdx < barIdx; bIdx += 1) {
      if (barNodes[bIdx]) barNodes[bIdx].classList.add("is-played");
    }

    // Update "Now playing" strip
    const curShown = getDisplayedChord(beat.chord);
    nowPlayingChordEl.textContent = curShown;

    let nextChord = null;
    let beatsUntil = 0;
    for (let j = activeBeatIdx + 1; j < beats.length; j += 1) {
      const cand = getDisplayedChord(beats[j].chord);
      if (cand !== curShown) {
        nextChord = cand;
        beatsUntil = j - activeBeatIdx;
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
      if (autoScrollEnabled && !audioPlayer.paused && barNodes[barIdx]) {
        scrollBarIntoView(barNodes[barIdx]);
      }
    }
  } else if (beats.length > 0) {
    nowPlayingChordEl.textContent = getDisplayedChord(beats[0].chord);
    nowPlayingNextChordEl.textContent = "—";
    nowPlayingCountdownEl.textContent = "";
  }

  for (const node of sectionNodes) {
    const active = t >= node.sec.start && t < node.sec.end;
    node.btn.classList.toggle("is-active", active);
  }
}

document.addEventListener("keydown", (event) => {
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
    const step = event.code === "ArrowRight" ? 1 : -1;
    const totalBars = barNodes.length;
    const targetBar = Math.max(0, Math.min(totalBars - 1, (lastActiveBarIdx < 0 ? 0 : lastActiveBarIdx) + step));
    const targetBeat = currentAnalysis.beat_chords[targetBar * 4];
    if (targetBeat) {
      audioPlayer.currentTime = targetBeat.start;
      updatePlayhead();
      scrollBarIntoView(barNodes[targetBar]);
    }
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
  } else if (data.beat_engine === "librosa-fallback" && data.beat_engine_note) {
    setStatus(
      `Analyzed "${data.title}" (${data.key}, ${data.tempo} BPM) using librosa beat fallback. ${data.beat_engine_note}`,
      "info"
    );
  } else {
    setStatus(`Analyzed "${data.title}" (${data.key}, ${data.tempo} BPM).`, "success");
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
      ? `Uploading "${file.name}" for Accurate analysis (~5–11 min on CPU)...`
      : `Uploading "${file.name}" for Fast analysis...`
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
  setLoading(true, `Starting YouTube download (${mode} mode)...`);

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

