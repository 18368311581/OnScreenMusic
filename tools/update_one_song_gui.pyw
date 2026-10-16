#!/usr/bin/env python3
"""Tiny Tkinter launcher for updating one song's generated LRC."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
from configparser import ConfigParser, Error as ConfigError
from dataclasses import dataclass
from pathlib import Path
from tkinter import BooleanVar, StringVar, Text, Tk, messagebox
from tkinter import ttk
from urllib import error, request


# Support direct .pyw execution and the existing file-loader tests.
_TOOL_DIRECTORY = str(Path(__file__).resolve().parent)
if _TOOL_DIRECTORY not in sys.path:
    sys.path.insert(0, _TOOL_DIRECTORY)
from ai_lyrics import (AiRepairError, build_ai_messages, request_ai_repair, normalize_ai_lrc)




LOCAL_SETTINGS_PATH = Path(__file__).with_name("update_one_song.local.ini")
GENERATOR = Path(__file__).with_name("generate_lrc.py")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-pro"
SUPPORTED_EXTENSIONS = (
    ".mp3",
    ".wav",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".wma",
)
LANGUAGE_OPTIONS = {
    "中文": "zh",
    "自动检测": "auto",
    "英语": "en",
    "日语": "ja",
    "韩语": "ko",
    "粤语": "yue",
    "法语": "fr",
    "德语": "de",
    "西班牙语": "es",
    "俄语": "ru",
    "意大利语": "it",
    "葡萄牙语": "pt",
}
DEFAULT_LANGUAGE = "中文"
PROGRESS_PATTERN = re.compile(r"识别进度：\s*(\d+)%")
TIMED_LRC_PATTERN = re.compile(r"^\[(\d+):([0-5]\d)(?:\.(\d{1,3}))?\](.*)$")
LRC_LINE_PATTERN = re.compile(r"^(?:\[[^\]\r\n]+\])+")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LocalSettingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalSettings:
    music_directory: Path
    lyrics_directory: Path
    deepseek_api_key: str


def load_local_settings(path: Path = LOCAL_SETTINGS_PATH) -> LocalSettings:
    parser = ConfigParser(interpolation=None)
    try:
        with path.open("r", encoding="utf-8") as config_file:
            parser.read_file(config_file)
    except FileNotFoundError as exc:
        raise LocalSettingsError(
            f"缺少本机配置文件：\n{path}\n\n"
            "请复制 update_one_song.local.example.ini 并按说明填写。"
        ) from exc
    except (OSError, UnicodeError, ConfigError) as exc:
        raise LocalSettingsError(f"无法读取本机配置文件：\n{path}\n\n{exc}") from exc

    required_options = (
        ("Paths", "MusicDirectory"),
        ("Paths", "LyricsDirectory"),
        ("DeepSeek", "ApiKey"),
    )
    missing = [
        f"[{section}] {option}"
        for section, option in required_options
        if not parser.has_option(section, option)
    ]
    if missing:
        raise LocalSettingsError(
            "本机配置缺少以下字段：\n" + "\n".join(missing)
        )

    def read_path(section: str, option: str) -> Path:
        raw_value = parser.get(section, option).strip().strip('"')
        if not raw_value:
            raise LocalSettingsError(f"本机配置中的 [{section}] {option} 不能为空。")
        value = Path(os.path.expandvars(raw_value)).expanduser()
        if not value.is_absolute():
            value = path.parent / value
        return value.resolve()

    return LocalSettings(
        music_directory=read_path("Paths", "MusicDirectory"),
        lyrics_directory=read_path("Paths", "LyricsDirectory"),
        deepseek_api_key=parser.get("DeepSeek", "ApiKey").strip(),
    )


def find_song(song_name: str, source_directory: Path) -> Path:
    name = song_name.strip().strip('"')
    if not name:
        raise ValueError("请输入歌曲名。")
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("只需要输入歌曲名，不要输入目录路径。")
    if not source_directory.is_dir():
        raise ValueError(f"歌曲目录不存在：\n{source_directory}")

    requested = Path(name)
    has_supported_extension = requested.suffix.casefold() in SUPPORTED_EXTENSIONS
    matches = []
    for candidate in source_directory.iterdir():
        if not candidate.is_file() or candidate.suffix.casefold() not in SUPPORTED_EXTENSIONS:
            continue
        if has_supported_extension:
            matched = candidate.name.casefold() == name.casefold()
        else:
            matched = candidate.stem.casefold() == name.casefold()
        if matched:
            matches.append(candidate)

    if not matches:
        raise ValueError(f"没有找到歌曲：{name}")
    if len(matches) > 1:
        choices = "\n".join(path.name for path in sorted(matches))
        raise ValueError(f"找到多个同名文件，请输入包含扩展名的完整文件名：\n{choices}")
    return matches[0]


def build_command(
    source: Path,
    output_directory: Path,
    language_code: str = "zh",
    allow_repetition: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        str(GENERATOR),
        "--source",
        str(source),
        "--output",
        str(output_directory),
        "--language",
        language_code,
        "--overwrite",
    ]
    if allow_repetition:
        command.append("--allow-repetition")
    return command


def repair_lrc_with_ai(
    source: Path,
    target: Path,
    reference_lyrics: str,
    api_key: str,
) -> None:
    try:
        draft_lrc = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AiRepairError(f"无法读取刚生成的 LRC：{exc}") from exc

    repaired_lrc = normalize_ai_lrc(
        request_ai_repair(source.stem, draft_lrc, reference_lyrics, api_key)
    )
    temporary_path = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{target.stem}.",
            suffix=".ai.tmp",
            dir=target.parent,
            delete=False,
        ) as temporary:
            temporary.write(repaired_lrc)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, target)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise AiRepairError(f"无法保存 AI 修复后的歌词：{exc}") from exc


class UpdateOneSongApp:
    def __init__(self, root: Tk, settings: LocalSettings) -> None:
        self.root = root
        self.settings = settings
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()

        root.title("单曲歌词更新")
        root.resizable(False, False)
        root.geometry("460x400")

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        self.song_name = ttk.Entry(frame, width=42)
        self.song_name.pack(fill="x")
        self.song_name.bind("<Return>", self.start)

        language_row = ttk.Frame(frame)
        language_row.pack(fill="x", pady=(10, 0))
        ttk.Label(language_row, text="初次识别语言：").pack(side="left")
        self.language_name = StringVar(value=DEFAULT_LANGUAGE)
        self.language_choice = ttk.Combobox(
            language_row,
            textvariable=self.language_name,
            values=tuple(LANGUAGE_OPTIONS),
            state="readonly",
            width=18,
        )
        self.language_choice.pack(side="left", fill="x", expand=True)

        self.allow_repetition = BooleanVar(value=False)
        self.repetition_check = ttk.Checkbutton(
            frame,
            text="允许大量重复歌词（确认属于歌曲原词）",
            variable=self.allow_repetition,
        )
        self.repetition_check.pack(anchor="w", pady=(8, 0))

        self.ai_enabled = BooleanVar(value=False)
        self.ai_check = ttk.Checkbutton(
            frame,
            text="AI 辅助修复",
            variable=self.ai_enabled,
            command=self.toggle_ai_input,
        )
        self.ai_check.pack(anchor="w", pady=(10, 4))
        self.reference_lyrics = Text(frame, height=11, wrap="word", state="disabled")
        self.reference_lyrics.pack(fill="both", expand=True)

        self.start_button = ttk.Button(frame, text="开始", command=self.start)
        self.start_button.pack(fill="x", pady=(8, 0))
        self.song_name.focus_set()

    def toggle_ai_input(self) -> None:
        state = "normal" if self.ai_enabled.get() else "disabled"
        self.reference_lyrics.configure(state=state)
        if self.ai_enabled.get():
            self.reference_lyrics.focus_set()

    def start(self, _event: object | None = None) -> None:
        try:
            source = find_song(self.song_name.get(), self.settings.music_directory)
        except ValueError as exc:
            messagebox.showerror("无法开始", str(exc), parent=self.root)
            return

        use_ai = self.ai_enabled.get()
        allow_repetition = self.allow_repetition.get()
        language_code = LANGUAGE_OPTIONS[self.language_name.get()]
        reference_lyrics = self.reference_lyrics.get("1.0", "end").strip()
        if use_ai and not reference_lyrics:
            messagebox.showerror("无法开始", "请粘贴完整的参考歌词。", parent=self.root)
            return
        if use_ai and not self.settings.deepseek_api_key:
            messagebox.showerror(
                "无法开始",
                "本机配置中的 DeepSeek ApiKey 为空，请填写新 Key 后重试。",
                parent=self.root,
            )
            return

        self.song_name.configure(state="disabled")
        self.language_choice.configure(state="disabled")
        self.repetition_check.configure(state="disabled")
        self.ai_check.configure(state="disabled")
        self.reference_lyrics.configure(state="disabled")
        self.start_button.configure(state="disabled", text="处理中…")
        threading.Thread(
            target=self.run_generator,
            args=(source, language_code, allow_repetition, use_ai, reference_lyrics),
            daemon=True,
        ).start()
        self.root.after(100, self.poll_events)

    def run_generator(
        self,
        source: Path,
        language_code: str,
        allow_repetition: bool,
        use_ai: bool,
        reference_lyrics: str,
    ) -> None:
        output_lines: list[str] = []
        try:
            process = subprocess.Popen(
                build_command(
                    source,
                    self.settings.lyrics_directory,
                    language_code,
                    allow_repetition,
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.rstrip()
                output_lines.append(line)
                match = PROGRESS_PATTERN.search(line)
                if match:
                    self.events.put(("progress", int(match.group(1))))
            return_code = process.wait()
        except OSError as exc:
            self.events.put(("finished", (False, f"无法启动歌词工具：{exc}", source)))
            return

        if return_code != 0:
            useful_lines = [line for line in output_lines if line.strip()][-8:]
            detail = "\n".join(useful_lines) or f"歌词工具退出码：{return_code}"
            self.events.put(("finished", (False, detail, source)))
            return

        if use_ai:
            target = self.settings.lyrics_directory / f"{source.stem}.lrc"
            self.events.put(("stage", "AI 修复中…"))
            try:
                repair_lrc_with_ai(
                    source,
                    target,
                    reference_lyrics,
                    self.settings.deepseek_api_key,
                )
            except AiRepairError as exc:
                detail = f"{exc}\n\nWhisper 生成的原始 LRC 已保留：\n{target}"
                self.events.put(("finished", (False, detail, source)))
                return
            self.events.put(("finished", (True, "歌词生成及 AI 修复完成。", source)))
            return

        self.events.put(("finished", (True, "歌词更新完成。", source)))

    def poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    self.start_button.configure(text=f"处理中 {payload}%")
                    continue
                if event == "stage":
                    self.start_button.configure(text=payload)
                    continue

                succeeded, detail, source = payload
                self.song_name.configure(state="normal")
                self.language_choice.configure(state="readonly")
                self.repetition_check.configure(state="normal")
                self.ai_check.configure(state="normal")
                self.toggle_ai_input()
                self.start_button.configure(state="normal", text="开始")
                self.song_name.focus_set()
                if succeeded:
                    target = self.settings.lyrics_directory / f"{source.stem}.lrc"
                    messagebox.showinfo(
                        "更新完成",
                        f"{detail}\n\n{target}",
                        parent=self.root,
                    )
                else:
                    messagebox.showerror("更新失败", detail, parent=self.root)
                return
        except queue.Empty:
            self.root.after(100, self.poll_events)


def main() -> None:
    root = Tk()
    root.withdraw()
    try:
        settings = load_local_settings()
    except LocalSettingsError as exc:
        messagebox.showerror("本机配置错误", str(exc), parent=root)
        root.destroy()
        return
    root.deiconify()
    UpdateOneSongApp(root, settings)
    root.mainloop()


if __name__ == "__main__":
    main()
