"""Minimal music sequence player for JSON-defined tone sequences."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import tempfile
import wave
from array import array
from pathlib import Path


SCALE_MAPS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "diminished": [0, 1, 3, 5, 6, 8, 10],
}

NOTE_BASE = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

SAMPLE_RATE = 44100
DEFAULT_WAVE = "square"


class MusicError(RuntimeError):
    pass


def load_music_data(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise MusicError(f"Unable to load music data: {path}") from exc


def parse_root(note: str) -> int:
    note = note.strip().upper()
    if len(note) < 2:
        raise MusicError(f"Invalid root note: {note!r}")
    letter = note[0]
    if letter not in NOTE_BASE:
        raise MusicError(f"Invalid root note: {note!r}")
    idx = 1
    accidental = 0
    if idx < len(note) and note[idx] in ("#", "B"):
        accidental = 1 if note[idx] == "#" else -1
        idx += 1
    octave_str = note[idx:]
    if not octave_str or not octave_str.lstrip("-").isdigit():
        raise MusicError(f"Invalid root note: {note!r}")
    octave = int(octave_str)
    semitone = NOTE_BASE[letter] + accidental
    midi = (octave + 1) * 12 + semitone
    return midi


def midi_to_freq(midi: int) -> float:
    return 440.0 * (2 ** ((midi - 69) / 12))


def normalize_note(entry: list | tuple) -> tuple[int, float, int, int]:
    if not entry:
        raise MusicError("Empty note entry")
    degree = int(entry[0])
    beats = float(entry[1]) if len(entry) > 1 else 1.0
    octave_shift = int(entry[2]) if len(entry) > 2 else 0
    accidental = int(entry[3]) if len(entry) > 3 else 0
    return degree, beats, octave_shift, accidental


def degree_to_midi(root_midi: int, degree: int, scale: str, octave_shift: int, accidental: int) -> int:
    if scale not in SCALE_MAPS:
        raise MusicError(f"Unknown scale: {scale}")
    if degree == 0:
        return -1
    if degree < 1 or degree > 7:
        raise MusicError(f"Degree out of range: {degree}")
    base = SCALE_MAPS[scale][degree - 1]
    semitone = base + accidental + (octave_shift * 12)
    return root_midi + semitone


def render_wave(freq: float, duration: float, wave_shape: str) -> array:
    total_samples = int(SAMPLE_RATE * duration)
    if total_samples <= 0:
        return array("h")
    data = array("h")
    fade_samples = min(int(SAMPLE_RATE * 0.005), total_samples)
    for i in range(total_samples):
        t = i / SAMPLE_RATE
        if wave_shape == "square":
            value = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        else:
            value = math.sin(2 * math.pi * freq * t)
        if fade_samples:
            if i < fade_samples:
                value *= i / fade_samples
            elif i > total_samples - fade_samples:
                value *= (total_samples - i) / fade_samples
        data.append(int(value * 12000))
    return data


def resolve_notes(sequence: dict, data: dict) -> list:
    notes = sequence.get("notes")
    if isinstance(notes, list) and notes:
        return notes
    pattern_name = sequence.get("pattern")
    if pattern_name:
        patterns = data.get("patterns", {})
        pattern = patterns.get(pattern_name)
        if isinstance(pattern, list) and pattern:
            return pattern
        raise MusicError(f"Unknown pattern: {pattern_name}")
    return []


def _resolve_octave_split(sequence: dict, override: str | None) -> str | None:
    if override:
        value = str(override).strip().lower()
    else:
        raw = sequence.get("octave_split")
        value = str(raw).strip().lower() if raw else ""
    if value in ("octave_split_up", "up"):
        return "up"
    if value in ("octave_split_down", "down"):
        return "down"
    if value in ("octave_split_random", "random"):
        return "random"
    if sequence.get("octave_split_up"):
        return "up"
    if sequence.get("octave_split_down"):
        return "down"
    if sequence.get("octave_split_random"):
        return "random"
    return None


def render_sequence(
    sequence: dict,
    root_midi: int,
    data: dict,
    *,
    staccato: bool = False,
    octave_split: str | None = None,
) -> array:
    tempo = float(sequence.get("tempo", 120))
    scale = sequence.get("scale", "major")
    wave_shape = sequence.get("wave", DEFAULT_WAVE)
    notes = resolve_notes(sequence, data)
    if not notes:
        raise MusicError("Sequence has no notes")
    buffer = array("h")
    seconds_per_beat = 60.0 / tempo
    split_mode = _resolve_octave_split(sequence, octave_split)
    staccato = bool((staccato or sequence.get("staccato")) and not split_mode)
    for entry in notes:
        degree, beats, octave_shift, accidental = normalize_note(entry)
        duration = max(0.0, beats * seconds_per_beat)
        if degree == 0:
            silence = array("h", [0] * int(SAMPLE_RATE * duration))
            buffer.extend(silence)
            continue
        if split_mode:
            tone_duration = duration * 0.5
            midi = degree_to_midi(root_midi, degree, scale, octave_shift, accidental)
            freq = midi_to_freq(midi)
            buffer.extend(render_wave(freq, tone_duration, wave_shape))
            shift = 1
            if split_mode == "down":
                shift = -1
            elif split_mode == "random":
                shift = random.choice((-1, 1))
            midi = degree_to_midi(root_midi, degree, scale, octave_shift + shift, accidental)
            freq = midi_to_freq(midi)
            buffer.extend(render_wave(freq, tone_duration, wave_shape))
        else:
            tone_duration = duration * 0.5 if staccato else duration
            midi = degree_to_midi(root_midi, degree, scale, octave_shift, accidental)
            freq = midi_to_freq(midi)
            buffer.extend(render_wave(freq, tone_duration, wave_shape))
            if staccato:
                silence = array("h", [0] * int(SAMPLE_RATE * tone_duration))
                buffer.extend(silence)
    return buffer


def play_audio(samples: array):
    if not samples:
        raise MusicError("No audio generated")
    if sys.platform == "darwin":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp_path = Path(tmp.name)
        with wave.open(str(tmp_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(samples.tobytes())
        try:
            import subprocess

            subprocess.run(["afplay", str(tmp_path)], check=False)
        finally:
            tmp_path.unlink(missing_ok=True)
        return
    try:
        import simpleaudio as sa  # type: ignore

        play_obj = sa.play_buffer(samples, 1, 2, SAMPLE_RATE)
        play_obj.wait_done()
        return
    except ImportError:
        pass

    if sys.platform == "win32":
        import winsound  # type: ignore

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp_path = Path(tmp.name)
        with wave.open(str(tmp_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(samples.tobytes())
        winsound.PlaySound(str(tmp_path), winsound.SND_FILENAME)
        tmp_path.unlink(missing_ok=True)
        return

    raise MusicError(
        "simpleaudio is required for playback on this platform. "
        "Install with: pip install simpleaudio"
    )


def play_sequence(
    data: dict,
    name: str,
    root_note: str,
    scale_override: str | None,
    tempo_override: float | None,
):
    sequences = data.get("sequences", {})
    if name not in sequences:
        raise MusicError(f"Unknown sequence: {name}")
    sequence = dict(sequences[name])
    if scale_override:
        sequence["scale"] = scale_override
    if tempo_override is not None:
        sequence["tempo"] = tempo_override
    root_midi = parse_root(root_note)
    samples = render_sequence(sequence, root_midi, data)
    play_audio(samples)


def render_song(data: dict, name: str, scale_override: str | None, tempo_override: float | None) -> array:
    songs = data.get("songs", {})
    if name not in songs:
        raise MusicError(f"Unknown song: {name}")
    song = songs[name]
    repeat = 1
    steps = song
    if isinstance(song, dict):
        repeat = int(song.get("repeat", 1) or 1)
        steps = song.get("steps", [])
    if not isinstance(steps, list):
        raise MusicError(f"Invalid song steps for: {name}")
    buffer = array("h")
    for _ in range(max(1, repeat)):
        for step in steps:
            if not isinstance(step, dict):
                raise MusicError(f"Invalid song step: {step}")
            sequence_name = step.get("sequence")
            root_note = step.get("root")
            if not sequence_name or not root_note:
                raise MusicError(f"Song step missing sequence/root: {step}")
            step_scale = step.get("scale") or scale_override
            step_tempo = step.get("tempo")
            if step_tempo is None:
                step_tempo = tempo_override
            sequences = data.get("sequences", {})
            if sequence_name not in sequences:
                raise MusicError(f"Unknown sequence: {sequence_name}")
            sequence = dict(sequences[sequence_name])
            if step_scale:
                sequence["scale"] = step_scale
            if step_tempo is not None:
                sequence["tempo"] = step_tempo
            staccato = bool(step.get("staccato") or sequence.get("staccato"))
            octave_split = step.get("octave_split")
            root_midi = parse_root(root_note)
            buffer.extend(
                render_sequence(
                    sequence,
                    root_midi,
                    data,
                    staccato=staccato,
                    octave_split=octave_split,
                )
            )
    return buffer


def play_song(data: dict, name: str, scale_override: str | None, tempo_override: float | None):
    samples = render_song(data, name, scale_override, tempo_override)
    play_audio(samples)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Play JSON-defined music sequences.")
    parser.add_argument(
        "--data",
        default="data/music.json",
        help="Path to music.json (default: data/music.json)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sequence_parser = subparsers.add_parser("sequence", help="Play a single sequence")
    sequence_parser.add_argument("name", help="Sequence name")
    sequence_parser.add_argument("root", help="Root note like C4 or F#3")

    song_parser = subparsers.add_parser("song", help="Play a song")
    song_parser.add_argument("name", help="Song name")

    for sub in (sequence_parser, song_parser):
        sub.add_argument("--scale", choices=sorted(SCALE_MAPS.keys()), help="Override scale")
        sub.add_argument("--tempo", type=float, help="Override tempo (BPM)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    data_path = Path(args.data)
    data = load_music_data(data_path)

    try:
        if args.command == "sequence":
            play_sequence(data, args.name, args.root, args.scale, args.tempo)
        else:
            play_song(data, args.name, args.scale, args.tempo)
    except MusicError as exc:
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
