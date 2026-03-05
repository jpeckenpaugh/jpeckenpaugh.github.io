#!/usr/bin/env python3

import math
import os
import struct
import subprocess
import sys
import tempfile
import wave


# -----------------------
# Note → frequency
# -----------------------

NOTE_OFFSETS = {
    "C": -9, "C#": -8, "Db": -8,
    "D": -7, "D#": -6, "Eb": -6,
    "E": -5,
    "F": -4, "F#": -3, "Gb": -3,
    "G": -2, "G#": -1, "Ab": -1,
    "A": 0,  "A#": 1,  "Bb": 1,
    "B": 2,
}


def note_to_freq(note: str) -> float:
    note = note.strip()
    if len(note) < 2:
        raise ValueError(f"Invalid note: {note!r}")

    if len(note) >= 3 and note[1] in "#b":
        name = note[:2]
        octave_str = note[2:]
    else:
        name = note[0]
        octave_str = note[1:]

    if name not in NOTE_OFFSETS:
        raise ValueError(f"Invalid note name: {note!r}")

    try:
        octave = int(octave_str)
    except ValueError:
        raise ValueError(f"Invalid octave in note: {note!r}")

    semitones = NOTE_OFFSETS[name] + (octave - 4) * 12
    return 440.0 * (2.0 ** (semitones / 12.0))


# -----------------------
# Synthesis
# -----------------------

def synth_piano(freq: float, duration: float, sr: int) -> list[float]:
    n_samples = int(duration * sr)

    # crude piano-ish harmonic spectrum
    harmonics = [
        (1, 1.00),
        (2, 0.60),
        (3, 0.40),
        (4, 0.25),
        (5, 0.15),
        (6, 0.08),
    ]

    samples = []
    for i in range(n_samples):
        t = i / sr

        # envelope: fast attack + exponential decay
        attack = 1.0 - math.exp(-t * 60.0)
        decay = math.exp(-t * 3.0)
        env = attack * decay

        s = 0.0
        for n, amp in harmonics:
            s += amp * math.sin(2.0 * math.pi * (freq * n) * t)

        samples.append(s * env)

    # normalize
    peak = max(abs(x) for x in samples) or 1.0
    return [x / peak for x in samples]


def synth_silence(duration: float, sr: int) -> list[float]:
    return [0.0] * int(duration * sr)


def write_wav(samples: list[float], sr: int, path: str) -> None:
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sr)

        for s in samples:
            s = max(-1.0, min(1.0, s))
            wf.writeframes(struct.pack("<h", int(s * 32767)))


# -----------------------
# Main
# -----------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: play_notes.py <comma-separated-notes> [bpm]")
        print('Example: play_notes.py "C4,D4,E4,F4,G4" 120')
        sys.exit(1)

    notes_arg = sys.argv[1]
    bpm = float(sys.argv[2]) if len(sys.argv) >= 3 else 120.0

    # quarter-note duration
    note_dur = 60.0 / bpm
    gap_dur = note_dur * 0.08  # small separation between notes

    notes = [n.strip() for n in notes_arg.split(",") if n.strip()]
    if not notes:
        raise SystemExit("No notes provided.")

    sr = 44100
    song = []

    for note in notes:
        freq = note_to_freq(note)
        song.extend(synth_piano(freq, duration=note_dur - gap_dur, sr=sr))
        song.extend(synth_silence(gap_dur, sr=sr))

    # write temp WAV and play with afplay
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        wav_path = f.name

    try:
        write_wav(song, sr=sr, path=wav_path)
        subprocess.run(["afplay", wav_path], check=False)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()

