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
const leadSheetEl = document.getElementById("lead-sheet");
const chartToolbar = document.getElementById("chart-toolbar");
const editModeBtn = document.getElementById("edit-mode-btn");
const exportJsonBtn = document.getElementById("export-json-btn");
const exportTxtBtn = document.getElementById("export-txt-btn");

let currentAnalysis = null;
let beatNodes = [];
let barNodes = [];
let rafId = null;
let isEditMode = false;

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
  leadSheetEl.hidden = false;
  leadSheetEl.innerHTML = "";

  beatNodes = [];
  barNodes = [];

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
      const isLastBeat = beat.beat_index === beatChords.length - 1;
      const isRepeat = prevBeat && prevBeat.chord === beat.chord && offset > 0 && !isLastBeat;
      const confPct = Math.round((beat.confidence || 0) * 100);

      if (beat.low_confidence) {
        cell.classList.add("is-low");
      }
      if (beat.edited) {
        cell.classList.add("is-edited");
      }

      cell.setAttribute(
        "aria-label",
        `Bar ${barIdx + 1} beat ${offset + 1}, chord ${beat.chord}, model confidence ${confPct}%${beat.low_confidence ? ", low model confidence" : ""}`
      );
      cell.title = `Model confidence: ${confPct}%`;
      cell.innerHTML = `
        <span class="beat-chord ${isRepeat ? "is-repeat" : ""}">${isRepeat ? "·" : beat.chord}</span>
        <span class="beat-conf">${beat.edited ? "edited" : `${confPct}%${beat.low_confidence ? " ?" : ""}`}</span>
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
  const lines = [
    `${data.title || "Untitled"}`,
    `Key: ${data.key || "Unknown"} | Tempo: ${data.tempo || "—"} BPM | Time: ${data.time_signature || "4/4"}`,
    "",
  ];
  const beats = data.beat_chords || [];
  const beatsPerBar = 4;
  const totalBars = Math.ceil(beats.length / beatsPerBar);
  let row = [];

  for (let b = 0; b < totalBars; b += 1) {
    const barBeats = beats.slice(b * beatsPerBar, (b + 1) * beatsPerBar);
    const tokens = barBeats.map((item, idx) => {
      const prev = item.beat_index > 0 ? beats[item.beat_index - 1] : null;
      return prev && prev.chord === item.chord && idx > 0 ? "/" : item.chord;
    });
    row.push(`| ${tokens.join(" ")} `);
    if (row.length === 4 || b === totalBars - 1) {
      lines.push(row.join("") + "|");
      row = [];
    }
  }
  return lines.join("\n");
}

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
  const slug = (currentAnalysis.title || "chordlens").replace(/[^a-z0-9-_]+/gi, "-").toLowerCase();
  downloadTextFile(`${slug}-chords.json`, JSON.stringify(currentAnalysis, null, 2), "application/json");
});

exportTxtBtn.addEventListener("click", () => {
  if (!currentAnalysis) return;
  const slug = (currentAnalysis.title || "chordlens").replace(/[^a-z0-9-_]+/gi, "-").toLowerCase();
  downloadTextFile(`${slug}-chord-sheet.txt`, formatChordSheetText(currentAnalysis), "text/plain");
});

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
  for (const bar of barNodes) {
    if (bar) bar.classList.remove("is-active");
  }

  if (activeBeatIdx >= 0 && beatNodes[activeBeatIdx]) {
    const { cell, barIdx } = beatNodes[activeBeatIdx];
    cell.classList.add("is-active");
    if (barNodes[barIdx]) {
      barNodes[barIdx].classList.add("is-active");
    }
  }
}

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

