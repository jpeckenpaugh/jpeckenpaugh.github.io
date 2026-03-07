#!/usr/bin/env python3

import math
import os
import random
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

    if len(note) >= 3 and note[1] in "#b":
        name = note[:2]
        octave = int(note[2:])
    else:
        name = note[0]
        octave = int(note[1:])

    semitones = NOTE_OFFSETS[name] + (octave - 4) * 12
    return 440.0 * (2.0 ** (semitones / 12.0))


# -----------------------
# Karplus–Strong guitar
# -----------------------

def karplus_strong(freq, duration=1.8, sr=44100, decay=0.996):
    N = int(sr / freq)
    buffer = [random.uniform(-1.0, 1.0) for _ in range(N)]

    samples = []
    for _ in range(int(duration * sr)):
        avg = decay * 0.5 * (buffer[0] + buffer[1])
        samples.append(buffer[0])
        buffer.append(avg)
        buffer.pop(0)

    # normalize
    peak = max(abs(x) for x in samples) or 1.0
    return [x / peak for x in samples]


def silence(duration, sr):
    return [0.0] * int(duration * sr)


# -----------------------
# WAV + afplay
# -----------------------

def write_wav(samples, sr, path):
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)

        for s in samples:
            wf.writeframes(struct.pack("<h", int(max(-1, min(1, s)) * 32767)))


# -----------------------
# Main
# -----------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: guitar.py <comma-separated-notes>")
        print('Example: guitar.py "E2,A2,D3,G3,B3,E4"')
        sys.exit(1)

    notes = [n.strip() for n in sys.argv[1].split(",") if n.strip()]
    sr = 44100

    song = []
    note_dur = 0.9
    gap = 0.05

    for note in notes:
        freq = note_to_freq(note)
        song.extend(karplus_strong(freq, duration=note_dur, sr=sr))
        song.extend(silence(gap, sr))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        path = f.name

    try:
        write_wav(song, sr, path)
        subprocess.run(["afplay", path])
    finally:
        os.unlink(path)


if __name__ == "__main__":
    main()

