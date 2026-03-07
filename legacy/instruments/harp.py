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
# Note → frequency (12-TET, A4 = 440)
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

    octave = int(octave_str)
    semitones = NOTE_OFFSETS[name] + (octave - 4) * 12
    return 440.0 * (2.0 ** (semitones / 12.0))


# -----------------------
# Harp-ish synthesis
#   - Karplus–Strong pluck (but cleaner + longer decay than "guitar")
#   - Gentle soundboard resonance (two simple resonators)
# -----------------------

def karplus_strong_harp(freq: float, duration: float, sr: int,
                        decay: float = 0.9985, damping: float = 0.45) -> list[float]:
    """
    decay: how long it rings (closer to 1.0 => longer)
    damping: low-pass amount in the loop (0..1). higher => darker/smoother
    """
    # Delay length
    N = max(2, int(sr / freq))

    # "Pluck" excitation: slightly shaped noise (less harsh than pure white noise)
    # Using triangular noise reduces buzzy high end.
    buf = [(random.random() - random.random()) for _ in range(N)]

    samples = []
    prev = 0.0
    total = int(duration * sr)

    for _ in range(total):
        x0 = buf[0]
        x1 = buf[1]

        # Averaging filter in feedback loop + extra one-pole damping
        avg = 0.5 * (x0 + x1)
        y = decay * ((1.0 - damping) * avg + damping * prev)
        prev = y

        samples.append(x0)
        buf.append(y)
        buf.pop(0)

    # normalize
    peak = max(abs(s) for s in samples) or 1.0
    return [s / peak for s in samples]


def resonator(samples: list[float], sr: int, f0: float, q: float, gain: float) -> list[float]:
    """
    Very small 2-pole resonator (biquad) to emulate soundboard resonance.
    f0: center frequency
    q: quality factor
    gain: linear gain applied to the resonated signal
    """
    w0 = 2.0 * math.pi * f0 / sr
    alpha = math.sin(w0) / (2.0 * q)

    # Bandpass (constant skirt gain)
    b0 = alpha
    b1 = 0.0
    b2 = -alpha
    a0 = 1.0 + alpha
    a1 = -2.0 * math.cos(w0)
    a2 = 1.0 - alpha

    # normalize coefficients
    b0 /= a0; b1 /= a0; b2 /= a0
    a1 /= a0; a2 /= a0

    y = [0.0] * len(samples)
    x1 = x2 = 0.0
    y1 = y2 = 0.0
    for i, x0 in enumerate(samples):
        y0 = b0*x0 + b1*x1 + b2*x2 - a1*y1 - a2*y2
        y[i] = gain * y0
        x2, x1 = x1, x0
        y2, y1 = y1, y0

    return y


def mix(a: list[float], b: list[float], scale_a: float = 1.0, scale_b: float = 1.0) -> list[float]:
    n = min(len(a), len(b))
    out = [(scale_a * a[i] + scale_b * b[i]) for i in range(n)]
    # normalize to avoid clipping
    peak = max(abs(s) for s in out) or 1.0
    if peak > 1.0:
        out = [s / peak for s in out]
    return out


def silence(duration: float, sr: int) -> list[float]:
    return [0.0] * int(duration * sr)


# -----------------------
# WAV + afplay
# -----------------------

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
        print("Usage: harp.py <comma-separated-notes> [bpm]")
        print('Example: harp.py "C4,D4,E4,F4,G4" 120')
        sys.exit(1)

    notes = [n.strip() for n in sys.argv[1].split(",") if n.strip()]
    bpm = float(sys.argv[2]) if len(sys.argv) >= 3 else 110.0

    sr = 44100
    note_dur = 60.0 / bpm  # quarter-note
    gap = note_dur * 0.06  # small separation between plucks

    song: list[float] = []

    for note in notes:
        f = note_to_freq(note)

        # core pluck (harp rings longer and cleaner)
        core = karplus_strong_harp(
            f, duration=max(0.25, note_dur - gap), sr=sr,
            decay=0.9988, damping=0.35
        )

        # soundboard bloom: resonances (tweak these for taste)
        r1 = resonator(core, sr, f0=220.0, q=2.2, gain=0.25)
        r2 = resonator(core, sr, f0=520.0, q=2.0, gain=0.18)

        note_out = mix(core, mix(r1, r2, 1.0, 1.0), scale_a=0.88, scale_b=0.55)

        song.extend(note_out)
        song.extend(silence(gap, sr))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        path = f.name

    try:
        write_wav(song, sr, path)
        subprocess.run(["afplay", path], check=False)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


if __name__ == "__main__":
    main()

