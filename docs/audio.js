const SCALE_MAPS = {
  major: [0, 2, 4, 5, 7, 9, 11],
  minor: [0, 2, 3, 5, 7, 8, 10],
  diminished: [0, 1, 3, 5, 6, 8, 10],
};

const NOTE_BASE = {
  C: 0,
  D: 2,
  E: 4,
  F: 5,
  G: 7,
  A: 9,
  B: 11,
};

const DEFAULT_WAVE = "square";

class LokartaAudio {
  constructor() {
    this._ctx = null;
    this._dataPromise = null;
    this._musicNodes = [];
    this._sfxNodes = [];
    this._mode = "on";
    this._attachResumeHandlers();
  }

  _attachResumeHandlers() {
    const resume = () => {
      this._ensureContext().catch(() => {});
    };
    window.addEventListener("pointerdown", resume, { passive: true });
    window.addEventListener("keydown", resume, { passive: true });
  }

  async _ensureContext() {
    if (!this._ctx) {
      this._ctx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (this._ctx.state === "suspended") {
      await this._ctx.resume();
    }
    return this._ctx;
  }

  async _loadData() {
    if (!this._dataPromise) {
      const url = new URL("data/music.json", window.location.href);
      this._dataPromise = fetch(url)
        .then((res) => (res.ok ? res.json() : {}))
        .catch(() => ({}));
    }
    return this._dataPromise;
  }

  setMode(mode) {
    const next = ["on", "off", "music", "sfx"].includes(mode) ? mode : "on";
    if (next === this._mode) return;
    this._mode = next;
    if (next === "off" || next === "sfx") {
      this.stopMusic();
    }
    if (next === "off" || next === "music") {
      this.stopSfx();
    }
  }

  stopAll() {
    this.stopMusic();
    this.stopSfx();
  }

  stopMusic() {
    this._stopNodes(this._musicNodes);
    this._musicNodes = [];
  }

  stopSfx() {
    this._stopNodes(this._sfxNodes);
    this._sfxNodes = [];
  }

  _stopNodes(nodes) {
    for (const node of nodes) {
      try {
        node.stop();
      } catch (err) {
        // Ignore.
      }
    }
  }

  _parseRoot(note) {
    if (!note) return null;
    const upper = String(note).trim().toUpperCase();
    if (upper.length < 2) return null;
    const letter = upper[0];
    if (!(letter in NOTE_BASE)) return null;
    let idx = 1;
    let accidental = 0;
    if (upper[idx] === "#" || upper[idx] === "B") {
      accidental = upper[idx] === "#" ? 1 : -1;
      idx += 1;
    }
    const octaveStr = upper.slice(idx);
    if (!/^[-]?\d+$/.test(octaveStr)) return null;
    const octave = parseInt(octaveStr, 10);
    const semitone = NOTE_BASE[letter] + accidental;
    return (octave + 1) * 12 + semitone;
  }

  _midiToFreq(midi) {
    return 440 * Math.pow(2, (midi - 69) / 12);
  }

  _normalizeNote(entry) {
    const degree = Number(entry[0]);
    const beats = entry.length > 1 ? Number(entry[1]) : 1.0;
    const octaveShift = entry.length > 2 ? Number(entry[2]) : 0;
    const accidental = entry.length > 3 ? Number(entry[3]) : 0;
    return { degree, beats, octaveShift, accidental };
  }

  _degreeToMidi(rootMidi, degree, scale, octaveShift, accidental) {
    if (degree === 0) return null;
    const map = SCALE_MAPS[scale] || SCALE_MAPS.major;
    const base = map[degree - 1] ?? 0;
    const semitone = base + accidental + octaveShift * 12;
    return rootMidi + semitone;
  }

  _resolveNotes(sequence, data) {
    if (Array.isArray(sequence.notes) && sequence.notes.length) {
      return sequence.notes;
    }
    if (sequence.pattern && data.patterns && Array.isArray(data.patterns[sequence.pattern])) {
      return data.patterns[sequence.pattern];
    }
    return [];
  }

  _scheduleSequence({ sequence, rootMidi, startTime, data, kind, scaleOverride, staccato }) {
    const tempo = Number(sequence.tempo || 120);
    const scale = scaleOverride || sequence.scale || "major";
    const wave = sequence.wave || DEFAULT_WAVE;
    const notes = this._resolveNotes(sequence, data);
    const secondsPerBeat = 60 / tempo;
    const useStaccato = Boolean(staccato || sequence.staccato);
    let t = startTime;
    const ctx = this._ctx;

    for (const entry of notes) {
      const { degree, beats, octaveShift, accidental } = this._normalizeNote(entry);
      const duration = Math.max(0, beats * secondsPerBeat);
      if (degree === 0) {
        t += duration;
        continue;
      }
      const toneDuration = useStaccato ? duration * 0.5 : duration;
      const midi = this._degreeToMidi(rootMidi, degree, scale, octaveShift, accidental);
      if (midi === null) {
        t += duration;
        continue;
      }
      const freq = this._midiToFreq(midi);
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = wave;
      osc.frequency.setValueAtTime(freq, t);
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.2, t + 0.01);
      const releaseStart = Math.max(t, t + toneDuration - 0.03);
      gain.gain.linearRampToValueAtTime(0, releaseStart + 0.03);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t);
      osc.stop(t + toneDuration + 0.05);
      if (kind === "music") {
        this._musicNodes.push(osc);
      } else {
        this._sfxNodes.push(osc);
      }
      t += duration;
    }
    return t - startTime;
  }

  async playSong(name, scaleOverride = "") {
    if (this._mode === "off" || this._mode === "sfx") {
      console.log("Audio: song blocked by mode", this._mode, name);
      return;
    }
    const ctx = await this._ensureContext();
    const data = await this._loadData();
    const song = (data.songs || {})[name];
    if (!Array.isArray(song) || !song.length) {
      console.log("Audio: missing song", name);
      return;
    }
    this.stopMusic();
    let startTime = ctx.currentTime + 0.02;
    for (const step of song) {
      const sequenceName = step.sequence;
      const root = step.root;
      if (!sequenceName || !root) continue;
      const sequence = (data.sequences || {})[sequenceName];
      if (!sequence) continue;
      const rootMidi = this._parseRoot(root);
      if (rootMidi == null) continue;
      const duration = this._scheduleSequence({
        sequence,
        rootMidi,
        startTime,
        data,
        kind: "music",
        scaleOverride: step.scale || scaleOverride || "",
        staccato: step.staccato,
      });
      startTime += duration;
    }
  }

  async playSequence(name, rootNote, scaleOverride = "") {
    if (this._mode === "off" || this._mode === "sfx") {
      console.log("Audio: sequence blocked by mode", this._mode, name);
      return;
    }
    const ctx = await this._ensureContext();
    const data = await this._loadData();
    const sequence = (data.sequences || {})[name];
    if (!sequence) {
      console.log("Audio: missing sequence", name);
      return;
    }
    const rootMidi = this._parseRoot(rootNote);
    if (rootMidi == null) {
      console.log("Audio: invalid root", rootNote);
      return;
    }
    this.stopMusic();
    this._scheduleSequence({
      sequence,
      rootMidi,
      startTime: ctx.currentTime + 0.02,
      data,
      kind: "music",
      scaleOverride: scaleOverride || "",
      staccato: sequence.staccato,
    });
  }

  async playSfx(name, rootNote, scaleOverride = "") {
    if (this._mode === "off" || this._mode === "music") {
      console.log("Audio: sfx blocked by mode", this._mode, name);
      return;
    }
    const ctx = await this._ensureContext();
    const data = await this._loadData();
    const sequence = (data.sequences || {})[name];
    if (!sequence) {
      console.log("Audio: missing sfx sequence", name);
      return;
    }
    const rootMidi = this._parseRoot(rootNote);
    if (rootMidi == null) {
      console.log("Audio: invalid root", rootNote);
      return;
    }
    this.stopSfx();
    this._scheduleSequence({
      sequence,
      rootMidi,
      startTime: ctx.currentTime + 0.01,
      data,
      kind: "sfx",
      scaleOverride: scaleOverride || "",
      staccato: sequence.staccato,
    });
  }
}

window.lokartaAudio = new LokartaAudio();
