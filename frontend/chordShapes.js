/* Guitar chord shapes table & inline SVG renderer (standard tuning EADGBe). */
(function (global) {
  "use strict";

  const STRING_NAMES = ["low E", "A", "D", "G", "B", "high e"];
  const NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
  const ROOT_TO_PC = {
    C: 0, "B#": 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, Fb: 4,
    F: 5, "E#": 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11, Cb: 11,
  };

  const QUALITY_INTERVALS = {
    "": [0, 4, 7],
    m: [0, 3, 7],
    "7": [0, 4, 7, 10],
    maj7: [0, 4, 7, 11],
    m7: [0, 3, 7, 10],
    sus2: [0, 2, 7],
    sus4: [0, 5, 7],
    dim: [0, 3, 6],
    aug: [0, 4, 8],
    "6": [0, 4, 7, 9],
    m6: [0, 3, 7, 9],
  };

  // Standard-tuning open shapes: [E, A, D, G, B, e], -1 = muted, 0 = open
  const OPEN_SHAPES = {
    C: { frets: [-1, 3, 2, 0, 1, 0], label: "Open C" },
    D: { frets: [-1, -1, 0, 2, 3, 2], label: "Open D" },
    E: { frets: [0, 2, 2, 1, 0, 0], label: "Open E" },
    G: { frets: [3, 2, 0, 0, 0, 3], label: "Open G" },
    A: { frets: [-1, 0, 2, 2, 2, 0], label: "Open A" },
    F: { frets: [-1, -1, 3, 2, 1, 1], label: "Easy F (4-string)", barre: { fret: 1, from: 4, to: 5 } },
    Am: { frets: [-1, 0, 2, 2, 1, 0], label: "Open Am" },
    Dm: { frets: [-1, -1, 0, 2, 3, 1], label: "Open Dm" },
    Em: { frets: [0, 2, 2, 0, 0, 0], label: "Open Em" },
    C7: { frets: [-1, 3, 2, 3, 1, 0], label: "Open C7" },
    D7: { frets: [-1, -1, 0, 2, 1, 2], label: "Open D7" },
    E7: { frets: [0, 2, 0, 1, 0, 0], label: "Open E7" },
    G7: { frets: [3, 2, 0, 0, 0, 1], label: "Open G7" },
    A7: { frets: [-1, 0, 2, 0, 2, 0], label: "Open A7" },
    B7: { frets: [-1, 2, 1, 2, 0, 2], label: "Open B7" },
    Am7: { frets: [-1, 0, 2, 0, 1, 0], label: "Open Am7" },
    Dm7: { frets: [-1, -1, 0, 2, 1, 1], label: "Open Dm7", barre: { fret: 1, from: 4, to: 5 } },
    Em7: { frets: [0, 2, 0, 0, 0, 0], label: "Open Em7" },
    Cmaj7: { frets: [-1, 3, 2, 0, 0, 0], label: "Open Cmaj7" },
    Fmaj7: { frets: [-1, -1, 3, 2, 1, 0], label: "Open Fmaj7" },
    Gmaj7: { frets: [3, 2, 0, 0, 0, 2], label: "Open Gmaj7" },
    Amaj7: { frets: [-1, 0, 2, 1, 2, 0], label: "Open Amaj7" },
    Dmaj7: { frets: [-1, -1, 0, 2, 2, 2], label: "Open Dmaj7" },
    Asus2: { frets: [-1, 0, 2, 2, 0, 0], label: "Open Asus2" },
    Asus4: { frets: [-1, 0, 2, 2, 3, 0], label: "Open Asus4" },
    Dsus2: { frets: [-1, -1, 0, 2, 3, 0], label: "Open Dsus2" },
    Dsus4: { frets: [-1, -1, 0, 2, 3, 3], label: "Open Dsus4" },
    Esus4: { frets: [0, 2, 2, 2, 0, 0], label: "Open Esus4" },
  };

  function parseChordName(chordName) {
    if (!chordName || chordName === "N") return null;
    const base = chordName.split("/")[0].trim();
    const match = base.match(/^([A-G][#b]?)(.*)$/);
    if (!match || ROOT_TO_PC[match[1]] === undefined) return null;
    return {
      root: match[1],
      pc: ROOT_TO_PC[match[1]],
      quality: match[2] || "",
    };
  }

  function buildBarreShapes(pc, quality) {
    const shapes = [];
    const eFret = (pc - 4 + 12) % 12 || 12;
    const aFret = (pc - 9 + 12) % 12 || 12;

    if (quality === "") {
      shapes.push({
        frets: [eFret, eFret + 2, eFret + 2, eFret + 1, eFret, eFret],
        barre: { fret: eFret, from: 0, to: 5 },
        label: `E-shape barre (fret ${eFret})`,
        rootFret: eFret,
      });
      shapes.push({
        frets: [-1, aFret, aFret + 2, aFret + 2, aFret + 2, aFret],
        barre: { fret: aFret, from: 1, to: 5 },
        label: `A-shape barre (fret ${aFret})`,
        rootFret: aFret,
      });
    } else if (quality === "m") {
      shapes.push({
        frets: [eFret, eFret + 2, eFret + 2, eFret, eFret, eFret],
        barre: { fret: eFret, from: 0, to: 5 },
        label: `Em-shape barre (fret ${eFret})`,
        rootFret: eFret,
      });
      shapes.push({
        frets: [-1, aFret, aFret + 2, aFret + 2, aFret + 1, aFret],
        barre: { fret: aFret, from: 1, to: 5 },
        label: `Am-shape barre (fret ${aFret})`,
        rootFret: aFret,
      });
    } else if (quality === "7") {
      shapes.push({
        frets: [eFret, eFret + 2, eFret, eFret + 1, eFret, eFret],
        barre: { fret: eFret, from: 0, to: 5 },
        label: `E7-shape barre (fret ${eFret})`,
        rootFret: eFret,
      });
      shapes.push({
        frets: [-1, aFret, aFret + 2, aFret, aFret + 2, aFret],
        barre: { fret: aFret, from: 1, to: 5 },
        label: `A7-shape barre (fret ${aFret})`,
        rootFret: aFret,
      });
    } else if (quality === "m7") {
      shapes.push({
        frets: [eFret, eFret + 2, eFret, eFret, eFret, eFret],
        barre: { fret: eFret, from: 0, to: 5 },
        label: `Em7-shape barre (fret ${eFret})`,
        rootFret: eFret,
      });
      shapes.push({
        frets: [-1, aFret, aFret + 2, aFret, aFret + 1, aFret],
        barre: { fret: aFret, from: 1, to: 5 },
        label: `Am7-shape barre (fret ${aFret})`,
        rootFret: aFret,
      });
    } else if (quality === "maj7") {
      shapes.push({
        frets: [-1, aFret, aFret + 2, aFret + 1, aFret + 2, aFret],
        barre: { fret: aFret, from: 1, to: 5 },
        label: `Amaj7-shape barre (fret ${aFret})`,
        rootFret: aFret,
      });
    }

    shapes.sort((x, y) => x.rootFret - y.rootFret);
    return shapes;
  }

  function getChordNotes(parsed) {
    if (!parsed) return [];
    const intervals = QUALITY_INTERVALS[parsed.quality] || (parsed.quality.startsWith("m") ? QUALITY_INTERVALS.m : QUALITY_INTERVALS[""]);
    return intervals.map((iv) => NOTE_NAMES[(parsed.pc + iv) % 12]);
  }

  function getChordShapeOptions(chordName) {
    const parsed = parseChordName(chordName);
    if (!parsed) {
      return { primary: null, alternatives: [], simplified: false, notes: [] };
    }

    const canonicalRoot = NOTE_NAMES[parsed.pc];
    const openKey = `${canonicalRoot}${parsed.quality}`;
    const rawOpenKey = `${parsed.root}${parsed.quality}`;
    const openShape = OPEN_SHAPES[rawOpenKey] || OPEN_SHAPES[openKey] || null;
    const barres = buildBarreShapes(parsed.pc, parsed.quality);

    const candidates = [];
    if (openShape) candidates.push(openShape);
    for (const b of barres) candidates.push(b);

    let simplified = false;
    if (candidates.length === 0) {
      simplified = true;
      const triadQuality = parsed.quality.startsWith("m") && !parsed.quality.startsWith("maj") ? "m" : "";
      const triadOpen = OPEN_SHAPES[`${canonicalRoot}${triadQuality}`] || null;
      const triadBarres = buildBarreShapes(parsed.pc, triadQuality);
      if (triadOpen) candidates.push(triadOpen);
      for (const b of triadBarres) candidates.push(b);
    }

    return {
      primary: candidates[0] || null,
      alternatives: candidates,
      simplified,
      notes: getChordNotes(parsed),
    };
  }

  function buildAriaLabel(chordName, shape, capoFret) {
    if (!shape) return `${chordName}, no diagram available`;
    const parts = shape.frets.map((fret, idx) => {
      const sName = STRING_NAMES[idx];
      if (fret < 0) return `muted ${sName}`;
      if (fret === 0) return `open ${sName}`;
      return `fret ${fret} ${sName}`;
    });
    const capoText = capoFret > 0 ? `, with capo ${capoFret}` : "";
    return `${chordName}${capoText}: ${parts.join(", ")}`;
  }

  function renderChordDiagramSvg(chordName, shape, options) {
    const opts = options || {};
    const capoFret = opts.capoFret || 0;
    const compact = Boolean(opts.compact);

    if (!shape) return "";

    const fretted = shape.frets.filter((f) => f > 0);
    const minFret = fretted.length ? Math.min(...fretted) : 1;
    const maxFret = fretted.length ? Math.max(...fretted) : 4;
    const baseFret = maxFret <= 4 ? 1 : minFret;
    const numFrets = 4;

    const w = compact ? 76 : 104;
    const h = compact ? 90 : 120;
    const left = compact ? 16 : 22;
    const top = capoFret > 0 ? (compact ? 22 : 28) : (compact ? 14 : 18);
    const gridW = compact ? 48 : 64;
    const gridH = compact ? 52 : 72;
    const strStep = gridW / 5;
    const fretStep = gridH / numFrets;

    const parts = [];
    const aria = buildAriaLabel(chordName, shape, capoFret);
    parts.push(`<svg class="chord-svg ${compact ? "chord-svg-sm" : "chord-svg-lg"}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${aria.replace(/"/g, "&quot;")}">`);

    // Capo bar at top if active
    if (capoFret > 0) {
      const capoY = compact ? 8 : 10;
      parts.push(`<rect x="${left - 4}" y="${capoY}" width="${gridW + 8}" height="${compact ? 5 : 6}" rx="2" fill="#0F766E" />`);
      parts.push(`<text x="${left + gridW / 2}" y="${capoY - 2}" text-anchor="middle" font-size="${compact ? 7 : 8}" font-weight="700" fill="#0F766E">Capo ${capoFret}</text>`);
    }

    // Nut or base fret label
    if (baseFret === 1) {
      parts.push(`<rect x="${left}" y="${top - 2}" width="${gridW}" height="3" fill="#111815" />`);
    } else {
      parts.push(`<text x="${left - 5}" y="${top + fretStep * 0.72}" text-anchor="end" font-size="${compact ? 8 : 10}" font-weight="600" fill="#4A5752">${baseFret}fr</text>`);
    }

    // Fret lines
    for (let f = 0; f <= numFrets; f += 1) {
      const y = top + f * fretStep;
      parts.push(`<line x1="${left}" y1="${y}" x2="${left + gridW}" y2="${y}" stroke="#CFD8D4" stroke-width="1" />`);
    }

    // String lines
    for (let s = 0; s < 6; s += 1) {
      const x = left + s * strStep;
      parts.push(`<line x1="${x}" y1="${top}" x2="${x}" y2="${top + gridH}" stroke="#4A5752" stroke-width="1" />`);
    }

    // Barre bar
    if (shape.barre) {
      const relFret = shape.barre.fret - baseFret + 1;
      if (relFret >= 1 && relFret <= numFrets) {
        const y = top + (relFret - 0.5) * fretStep;
        const x1 = left + shape.barre.from * strStep;
        const x2 = left + shape.barre.to * strStep;
        const r = compact ? 4 : 5;
        parts.push(`<rect x="${x1 - r}" y="${y - r}" width="${(x2 - x1) + r * 2}" height="${r * 2}" rx="${r}" fill="#111815" />`);
      }
    }

    // Finger dots, X, O
    const dotR = compact ? 3.5 : 4.8;
    const markerY = top - (compact ? 6 : 8);
    for (let s = 0; s < 6; s += 1) {
      const fret = shape.frets[s];
      const x = left + s * strStep;
      if (fret < 0) {
        const d = compact ? 2.2 : 2.8;
        parts.push(`<line x1="${x - d}" y1="${markerY - d}" x2="${x + d}" y2="${markerY + d}" stroke="#4A5752" stroke-width="1.3" />`);
        parts.push(`<line x1="${x + d}" y1="${markerY - d}" x2="${x - d}" y2="${markerY + d}" stroke="#4A5752" stroke-width="1.3" />`);
      } else if (fret === 0) {
        parts.push(`<circle cx="${x}" cy="${markerY}" r="${compact ? 2.4 : 3}" fill="none" stroke="#111815" stroke-width="1.3" />`);
      } else {
        const relFret = fret - baseFret + 1;
        if (relFret >= 1 && relFret <= numFrets) {
          const y = top + (relFret - 0.5) * fretStep;
          parts.push(`<circle cx="${x}" cy="${y}" r="${dotR}" fill="#111815" />`);
        }
      }
    }

    parts.push("</svg>");
    return parts.join("");
  }

  global.ChordShapes = {
    getChordShapeOptions,
    renderChordDiagramSvg,
  };
})(window);
