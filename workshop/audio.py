"""In-process Windows audio preview using the system MCI driver, without extra packages."""
from __future__ import annotations

import ctypes
import uuid
from pathlib import Path


class AudioPreview:
    def __init__(self):
        self.alias = "workshop" + uuid.uuid4().hex
        self.loaded, self.duration, self.volume = False, 0, 20
        self.winmm = ctypes.WinDLL("winmm")
        self.winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        self.winmm.mciSendStringW.restype = ctypes.c_uint
        self.winmm.mciGetErrorStringW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
        self.winmm.mciGetErrorStringW.restype = ctypes.c_int

    def _command(self, command):
        result = ctypes.create_unicode_buffer(512)
        error = self.winmm.mciSendStringW(command, result, len(result), None)
        if error:
            self.winmm.mciGetErrorStringW(error, result, len(result))
            raise OSError(result.value or f"音频播放错误 {error}")
        return result.value

    def load(self, path: Path):
        self.close()
        path = path.resolve()
        if not path.is_file() or '"' in str(path):
            raise ValueError("试听音频文件不存在或文件名无效。")
        self._command(f'open "{path}" type mpegvideo alias {self.alias}')
        self.loaded = True
        try:
            self._command(f"set {self.alias} time format milliseconds")
            self.duration = int(self._command(f"status {self.alias} length"))
            self.set_volume(self.volume)
        except (OSError, ValueError):
            self.close()
            raise

    def position(self):
        return int(self._command(f"status {self.alias} position")) if self.loaded else 0

    def playing(self):
        return self.loaded and self._command(f"status {self.alias} mode") == "playing"

    def play(self):
        if not self.loaded:
            return
        if self.duration > 0 and self.position() >= self.duration:
            self._command(f"seek {self.alias} to start")
        self._command(f"play {self.alias}")

    def pause(self):
        if self.loaded:
            self._command(f"pause {self.alias}")

    def seek(self, position):
        if not self.loaded:
            return
        position = max(0, min(int(position), self.duration))
        playing = self.playing()
        self._command(f"seek {self.alias} to {position}")
        if playing and position < self.duration:
            self._command(f"play {self.alias}")

    def set_volume(self, value):
        self.volume = max(0, min(int(value), 100))
        if self.loaded:
            self._command(f"setaudio {self.alias} volume to {self.volume * 10}")

    def close(self):
        if self.loaded:
            try:
                self._command(f"close {self.alias}")
            except OSError:
                pass  # A device already closed by Windows needs no further cleanup.
            finally:
                self.loaded, self.duration = False, 0
