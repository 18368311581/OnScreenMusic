"""Single QSettings-compatible INI and cross-process write guard."""
from __future__ import annotations

import configparser
import ctypes
import hashlib
import io
import os
import re
from contextlib import contextmanager
from pathlib import Path


def settings_file(base: Path) -> Path:
    base = base.resolve()
    deployed = base / "release-v1.0"
    if not (base / "OnScreenMusic.exe").exists() and (deployed / "OnScreenMusic.exe").exists():
        base = deployed
    return base / "OnScreenMusic.ini"


@contextmanager
def settings_guard(path: Path):
    if os.name != "nt":
        yield
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    token = hashlib.sha256(path.resolve().as_posix().casefold().encode("utf-8")).hexdigest()[:20]
    handle = kernel.CreateMutexW(None, False, "Local\\OnScreenMusic.Settings." + token)
    if not handle:
        raise OSError("无法锁定统一配置文件。")
    acquired = False
    try:
        result = kernel.WaitForSingleObject(handle, 10000)
        if result not in (0, 0x80):
            raise OSError("配置文件正在被其他操作使用，请稍后重试。")
        acquired = True
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, delimiters=("=",), default_section="__NoDefaults__")
    parser.optionxform = str
    if path.exists():
        parser.read_string(path.read_text(encoding="utf-8-sig"))
    return parser


def ini_text(parser: configparser.ConfigParser) -> str:
    stream = io.StringIO()
    parser.write(stream)
    return stream.getvalue()


def qt_encode(value: str) -> str:
    # QSettings treats @Variant/@ByteArray specially even inside quotes.
    if value.startswith("@"):
        value = "@" + value
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return '"' + value + '"'


def qt_decode(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    escapes = {'n': '\n', 'r': '\r', 't': '\t', '\\': '\\', '"': '"'}
    def decode(match):
        code = match.group(1)
        return chr(int(code[1:], 16)) if code.startswith("x") else escapes.get(code, code)
    value = re.sub(r"\\(x[0-9a-fA-F]{1,4}|.)", decode, value)
    return value[1:] if value.startswith("@@") else value


WORKSHOP_KEYS = {"work": "Work", "ffmpeg": "FFmpeg", "whisper": "Whisper", "model": "Model", "api_key": "ApiKey"}
