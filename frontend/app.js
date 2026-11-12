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

const chartSubtitle = document.getElementById("chart-subtitle");
const chartEmpty = document.getElementById("chart-empty");
const leadSheetEl = document.getElementById("lead-sheet");

let currentAnalysis = null;
let beatNodes = [];
let barNodes = [];
let rafId = null;

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

  audioPlayer.src = data.audio_url;
  playerPanel.hidden = false;

  const beatChords = data.beat_chords || [];
  const chords = data.chords || [];
  const beatsPerBar = 4;
  const totalBars = Math.ceil(beatChords.length / beatsPerBar);
  const lastChord = chords.length > 0 ? chords[chords.length - 1] : null;
  const endsSummary = lastChord ? ` · Ends on ${lastChord.chord} (${formatTime(lastChord.end)})` : "";

  chartSubtitle.textContent = `${totalBars} bars · ${beatChords.length} beats${endsSummary} · Click any beat to jump`;
  chartEmpty.hidden = true;
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

      cell.setAttribute(
        "aria-label",
        `Bar ${barIdx + 1} beat ${offset + 1}, chord ${beat.chord}, confidence ${confPct}%${beat.low_confidence ? ", low confidence" : ""}`
      );
      cell.innerHTML = `
        <span class="beat-chord ${isRepeat ? "is-repeat" : ""}">${isRepeat ? "·" : beat.chord}</span>
        <span class="beat-conf">${confPct}%${beat.low_confidence ? " ?" : ""}</span>
      `;

      cell.addEventListener("click", () => {
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

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = audioFileInput.files[0];
  if (!file) {
    setStatus("Choose an MP3, WAV, M4A, or FLAC file first.", "error");
    return;
  }

  clearStatus();
  setLoading(true, `Analyzing "${file.name}"...`);

  try {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/api/analyze", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Could not analyze this audio file.");
    }
    renderAnalysis(data);
    const lastEnd = data.chords && data.chords.length ? data.chords[data.chords.length - 1].end : 0;
    if (data.duration > 5 && lastEnd < data.duration - 3.0) {
      setStatus(
        `Analysis stopped early at ${formatTime(lastEnd)} of ${formatTime(data.duration)}. Try converting the file to WAV and re-uploading.`,
        "error"
      );
    } else {
      setStatus(`Analyzed "${data.title}" (${data.key}, ${data.tempo} BPM).`, "success");
    }
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

  clearStatus();
  setLoading(true, "Downloading audio from YouTube and analyzing...");

  try {
    const res = await fetch("/api/analyze-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Could not analyze this YouTube link.");
    }
    renderAnalysis(data);
    const lastEnd = data.chords && data.chords.length ? data.chords[data.chords.length - 1].end : 0;
    if (data.duration > 5 && lastEnd < data.duration - 3.0) {
      setStatus(
        `Analysis stopped early at ${formatTime(lastEnd)} of ${formatTime(data.duration)}. Try converting the file to WAV and re-uploading.`,
        "error"
      );
    } else {
      setStatus(`Analyzed "${data.title}" (${data.key}, ${data.tempo} BPM).`, "success");
    }
  } catch (err) {
    setStatus(err.message || "YouTube analysis failed. Check the link and try again.", "error");
  } finally {
    setLoading(false);
  }
});

