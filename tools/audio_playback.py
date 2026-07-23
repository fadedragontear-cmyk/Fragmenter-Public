#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import wave
from pathlib import Path


class AudioPlaybackEngine:
    """Small non-blocking WAV playback facade for Fragmenter previews.

    The engine uses an already-installed Python backend only. It never downloads
    binaries and never launches an external media player.
    """

    def __init__(self) -> None:
        self.path: Path | None = None
        self._duration = 0.0
        self._loop = False
        self._gain = 1.0
        self._backend = "unavailable"
        self._capabilities = {
            "play": False,
            "stop": False,
            "pause": False,
            "resume": False,
            "gain": False,
            "position": False,
            "seek": False,
            "duration": True,
            "loop": False,
        }
        self._pygame = None
        self._pygame_sound = None
        self._simpleaudio = None
        self._simpleaudio_wave = None
        self._simpleaudio_play_obj = None
        self._winsound = None
        self._select_backend()

    @property
    def backend_name(self) -> str:
        return self._backend

    @property
    def capabilities(self) -> dict[str, bool]:
        return dict(self._capabilities)

    @property
    def supports_pause(self) -> bool:
        return self._capabilities.get("pause", False) and self._capabilities.get("resume", False)

    @property
    def is_playing(self) -> bool:
        if self._backend == "pygame" and self._pygame is not None:
            return bool(self._pygame.mixer.get_busy())
        if self._backend == "simpleaudio" and self._simpleaudio_play_obj is not None:
            return bool(self._simpleaudio_play_obj.is_playing())
        # winsound exposes no playback state API.
        return False

    def _select_backend(self) -> None:
        if importlib.util.find_spec("simpleaudio") is not None:
            import simpleaudio  # type: ignore

            self._simpleaudio = simpleaudio
            self._backend = "simpleaudio"
            self._capabilities.update({"play": True, "stop": True, "loop": False})
            return
        if importlib.util.find_spec("pygame") is not None:
            import pygame  # type: ignore

            self._pygame = pygame
            self._backend = "pygame"
            self._capabilities.update({
                "play": True,
                "stop": True,
                "pause": True,
                "resume": True,
                "gain": True,
                "position": False,
                "loop": True,
            })
            return
        if sys.platform.startswith("win"):
            import winsound

            self._winsound = winsound
            self._backend = "winsound"
            self._capabilities.update({"play": True, "stop": True})

    def load(self, path: str | Path) -> None:
        self.stop()
        wav_path = Path(path).expanduser()
        if not wav_path.is_file():
            raise FileNotFoundError(wav_path)
        if wav_path.suffix.lower() != ".wav":
            raise ValueError(f"AudioPlaybackEngine only supports WAV files: {wav_path}")
        self.path = wav_path
        self._duration = self._read_wav_duration(wav_path)
        if self._backend == "simpleaudio":
            self._simpleaudio_wave = self._simpleaudio.WaveObject.from_wave_file(str(wav_path))
        elif self._backend == "pygame":
            if not self._pygame.mixer.get_init():
                self._pygame.mixer.init()
            self._pygame_sound = self._pygame.mixer.Sound(str(wav_path))
            self._pygame_sound.set_volume(self._gain)

    def play(self) -> None:
        if self.path is None:
            raise RuntimeError("No audio file loaded")
        if not self._capabilities.get("play"):
            raise RuntimeError("No supported in-process audio playback backend is available")
        self.stop()
        if self._backend == "simpleaudio":
            self._simpleaudio_play_obj = self._simpleaudio_wave.play()
        elif self._backend == "pygame":
            loops = -1 if self._loop else 0
            self._pygame_sound.play(loops=loops)
        elif self._backend == "winsound":
            flags = self._winsound.SND_FILENAME | self._winsound.SND_ASYNC
            if self._loop:
                flags |= self._winsound.SND_LOOP
            self._winsound.PlaySound(str(self.path), flags)

    def pause(self) -> None:
        if not self.supports_pause:
            raise NotImplementedError(f"Pause is unavailable for playback backend: {self._backend}")
        self._pygame.mixer.pause()

    def resume(self) -> None:
        if not self.supports_pause:
            raise NotImplementedError(f"Resume is unavailable for playback backend: {self._backend}")
        self._pygame.mixer.unpause()

    def stop(self) -> None:
        if self._backend == "simpleaudio" and self._simpleaudio_play_obj is not None:
            self._simpleaudio_play_obj.stop()
            self._simpleaudio_play_obj = None
        elif self._backend == "pygame" and self._pygame is not None:
            try:
                self._pygame.mixer.stop()
            except Exception:
                pass
        elif self._backend == "winsound" and self._winsound is not None:
            self._winsound.PlaySound(None, self._winsound.SND_PURGE)

    def set_loop(self, enabled: bool) -> None:
        self._loop = bool(enabled)

    def set_gain(self, gain: float) -> None:
        self._gain = max(0.0, min(float(gain), 1.0))
        if self._backend == "pygame" and self._pygame_sound is not None:
            self._pygame_sound.set_volume(self._gain)

    def position_seconds(self) -> float | None:
        return None

    def duration_seconds(self) -> float:
        return self._duration

    @staticmethod
    def _read_wav_duration(path: Path) -> float:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            return frames / float(rate) if rate else 0.0
