"""Audio playback helpers for local (macOS) runs and Pyodide."""

from __future__ import annotations

import os
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path
from threading import RLock

import sys

import music


class AudioManager:
    def __init__(self, data_path: str):
        self._data_path = Path(data_path)
        self._data = None
        self._music_process: subprocess.Popen | None = None
        self._music_temp_path: Path | None = None
        self._sfx_process: subprocess.Popen | None = None
        self._sfx_temp_path: Path | None = None
        self._lock = RLock()
        self._mode = "on"
        self._music_volume = 1.0
        self._sfx_volume = 1.0
        self._default_wave = None
        self._web = None
        self._web_warned = False
        if os.environ.get("LOKARTA_WEB") == "1":
            try:
                import js  # type: ignore

                self._web = getattr(js, "lokartaAudio", None)
            except Exception:
                self._web = None
        if self._web is not None:
            try:
                self._web.setDefaults(self._music_volume, self._sfx_volume, self._default_wave or "")
            except Exception:
                pass

    def load(self) -> None:
        if self._data is not None:
            return
        if not self._data_path.exists():
            self._data = {}
            return
        self._data = music.load_music_data(self._data_path)

    def _write_wav(self, samples: array) -> Path:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp_path = Path(tmp.name)
        with wave.open(str(tmp_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(music.SAMPLE_RATE)
            wav.writeframes(samples.tobytes())
        return tmp_path

    def _cleanup_process(self, kind: str) -> None:
        process = self._music_process if kind == "music" else self._sfx_process
        temp_path = self._music_temp_path if kind == "music" else self._sfx_temp_path
        if process and process.poll() is None:
            return
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if kind == "music":
            self._music_process = None
            self._music_temp_path = None
        else:
            self._sfx_process = None
            self._sfx_temp_path = None

    def _stop_kind(self, kind: str) -> None:
        process = self._music_process if kind == "music" else self._sfx_process
        temp_path = self._music_temp_path if kind == "music" else self._sfx_temp_path
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if kind == "music":
            self._music_process = None
            self._music_temp_path = None
        else:
            self._sfx_process = None
            self._sfx_temp_path = None

    def _play_samples(self, samples: array, *, kind: str) -> None:
        if sys.platform != "darwin":
            return
        self._cleanup_process(kind)
        if kind == "music":
            if self._music_process and self._music_process.poll() is None:
                self._stop_kind("music")
        else:
            if self._sfx_process and self._sfx_process.poll() is None:
                self._stop_kind("sfx")
        tmp_path = self._write_wav(samples)
        proc = subprocess.Popen(["afplay", str(tmp_path)])
        if kind == "music":
            self._music_temp_path = tmp_path
            self._music_process = proc
        else:
            self._sfx_temp_path = tmp_path
            self._sfx_process = proc

    def stop(self) -> None:
        if self._web is not None:
            try:
                self._web.stopAll()
            except Exception:
                pass
            return
        if os.environ.get("LOKARTA_WEB") == "1" and not self._web_warned:
            print("Audio: web bridge unavailable.")
            self._web_warned = True
        with self._lock:
            self._stop_kind("music")
            self._stop_kind("sfx")

    def set_mode(self, mode: str | None) -> None:
        mode = str(mode or "on")
        if mode not in ("on", "off", "music", "sfx"):
            mode = "on"
        if mode == self._mode:
            return
        self._mode = mode
        if self._web is not None:
            try:
                self._web.setMode(mode)
            except Exception:
                pass
            return
        if os.environ.get("LOKARTA_WEB") == "1" and not self._web_warned:
            print("Audio: web bridge unavailable.")
            self._web_warned = True
        if mode in ("off", "sfx"):
            self._stop_kind("music")
        if mode in ("off", "music"):
            self._stop_kind("sfx")

    def set_defaults(self, music_volume: float, sfx_volume: float, wave: str | None = None) -> None:
        self._music_volume = max(0.0, min(1.0, float(music_volume)))
        self._sfx_volume = max(0.0, min(1.0, float(sfx_volume)))
        self._default_wave = str(wave) if wave else None
        if self._web is not None:
            try:
                self._web.setDefaults(self._music_volume, self._sfx_volume, self._default_wave or "")
            except Exception:
                pass

    def _apply_volume(self, samples: array, volume: float) -> array:
        if volume >= 0.99:
            return samples
        scaled = array("h")
        for sample in samples:
            value = int(sample * volume)
            if value > 32767:
                value = 32767
            elif value < -32768:
                value = -32768
            scaled.append(value)
        return scaled

    def play_sequence_once(self, name: str, root_note: str, scale: str | None = None, wave: str | None = None) -> None:
        if self._web is not None:
            try:
                self._web.playSequence(name, root_note, scale or "", wave or "")
            except Exception:
                pass
            return
        if os.environ.get("LOKARTA_WEB") == "1" and not self._web_warned:
            print("Audio: web bridge unavailable.")
            self._web_warned = True
            return
        if sys.platform != "darwin":
            return
        if self._mode in ("off", "sfx"):
            return
        self.load()
        if not self._data:
            return
        sequences = self._data.get("sequences", {})
        if name not in sequences:
            return
        sequence = dict(sequences[name])
        if scale:
            sequence["scale"] = scale
        if wave or self._default_wave:
            sequence["wave"] = wave or self._default_wave
        root_midi = music.parse_root(root_note)
        samples = music.render_sequence(sequence, root_midi, self._data)
        samples = self._apply_volume(samples, self._music_volume)
        self._stop_kind("music")
        with self._lock:
            self._play_samples(samples, kind="music")

    def play_song_once(self, name: str, scale: str | None = None, wave: str | None = None) -> None:
        if self._web is not None:
            try:
                self._web.playSong(name, scale or "", wave or "")
            except Exception:
                pass
            return
        if os.environ.get("LOKARTA_WEB") == "1" and not self._web_warned:
            print("Audio: web bridge unavailable.")
            self._web_warned = True
            return
        if sys.platform != "darwin":
            return
        if self._mode in ("off", "sfx"):
            return
        self.load()
        if not self._data:
            return
        if name not in self._data.get("songs", {}):
            return
        wave_override = wave or self._default_wave
        samples = music.render_song(self._data, name, scale, None, wave_override)
        samples = self._apply_volume(samples, self._music_volume)
        self._stop_kind("music")
        with self._lock:
            self._play_samples(samples, kind="music")

    def play_sfx_once(self, name: str, root_note: str, scale: str | None = None, wave: str | None = None) -> None:
        if self._web is not None:
            try:
                self._web.playSfx(name, root_note, scale or "", wave or "")
            except Exception:
                pass
            return
        if os.environ.get("LOKARTA_WEB") == "1" and not self._web_warned:
            print("Audio: web bridge unavailable.")
            self._web_warned = True
            return
        if sys.platform != "darwin":
            return
        if self._mode in ("off", "music"):
            return
        self.load()
        if not self._data:
            return
        sequences = self._data.get("sequences", {})
        if name in sequences:
            sequence = dict(sequences[name])
            if scale:
                sequence["scale"] = scale
            if wave or self._default_wave:
                sequence["wave"] = wave or self._default_wave
            root_midi = music.parse_root(root_note)
            samples = music.render_sequence(sequence, root_midi, self._data)
        else:
            songs = self._data.get("songs", {})
            if name not in songs:
                return
            song = songs[name]
            if not (isinstance(song, dict) and song.get("sfx")):
                return
            wave_override = wave or self._default_wave
            samples = music.render_song(self._data, name, scale, None, wave_override)
        samples = self._apply_volume(samples, self._sfx_volume)
        with self._lock:
            self._play_samples(samples, kind="sfx")

    def on_location_change(self, pre_location: str | None, post_location: str | None) -> None:
        if post_location == "Title" and pre_location != "Title":
            self.play_song_once("intro_music")
        if pre_location == "Title" and post_location != "Title":
            self.stop()

    def on_battle_change(
        self,
        pre_alive: bool,
        post_alive: bool,
        in_forest: bool,
        player_alive: bool,
        was_in_forest: bool,
    ) -> None:
        if in_forest and post_alive and not pre_alive:
            self.play_song_once("battle_minor")
        if pre_alive and not post_alive and (in_forest or was_in_forest):
            if player_alive:
                self.play_song_once("battle_victory")
            else:
                self.stop()
