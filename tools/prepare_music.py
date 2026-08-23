#!/usr/bin/env python3
"""Prepare a flat, loudness-normalized music directory for On Screen Music."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


MEDIA_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".wma",
    ".mp4",
    ".flv",
    ".mkv",
    ".mov",
    ".webm",
}
FALLBACK_FFMPEG = Path(
    r"C:\Program Files (x86)\FFmpeg\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe"
)
REPORT_NAME = "prepare_music_report.txt"
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
LOUDNESS_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class StartupError(RuntimeError):
    """An error that prevents any track processing from starting."""


class TrackError(RuntimeError):
    """An error limited to a single source track."""


@dataclass(frozen=True)
class Track:
    source: Path
    relative_source: Path
    output_stem: str
    lyric_source: Path | None


@dataclass(frozen=True)
class ReportEntry:
    source: Path
    target: Path
    status: str
    detail: str


@dataclass
class Counters:
    succeeded: int = 0
    skipped: int = 0
    warnings: int = 0
    failed: int = 0


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="整理歌单并输出响度统一的 320 kbps MP3 与 UTF-8 LRC。"
    )
    parser.add_argument("--source", required=True, help="原始歌单目录")
    parser.add_argument("--output", required=True, help="标准化歌单输出目录")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的派生文件")
    parser.add_argument("--ffmpeg", help="显式指定 ffmpeg.exe 路径")
    return parser.parse_args(argv)


def resolve_directories(source_arg: str, output_arg: str) -> tuple[Path, Path]:
    source = Path(source_arg).expanduser()
    if not source.exists():
        raise StartupError(f"源目录不存在：{source}")
    if not source.is_dir():
        raise StartupError(f"源路径不是目录：{source}")

    source = source.resolve()
    output = Path(output_arg).expanduser().resolve(strict=False)
    if output.exists() and not output.is_dir():
        raise StartupError(f"输出路径不是目录：{output}")

    if source == output or source in output.parents or output in source.parents:
        raise StartupError("源目录和输出目录不能相同，也不能互相包含。")
    return source, output


def locate_ffmpeg(explicit_path: str | None) -> Path:
    if explicit_path:
        candidate = Path(explicit_path).expanduser().resolve(strict=False)
        if not candidate.is_file():
            raise StartupError(f"--ffmpeg 指定的文件不存在：{candidate}")
        return candidate

    from_path = shutil.which("ffmpeg.exe") or shutil.which("ffmpeg")
    if from_path:
        return Path(from_path).resolve()
    if FALLBACK_FFMPEG.is_file():
        return FALLBACK_FFMPEG
    raise StartupError("找不到 FFmpeg。请使用 --ffmpeg 指定 ffmpeg.exe。")


def validate_ffmpeg(ffmpeg: Path) -> None:
    try:
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StartupError(f"无法启动 FFmpeg：{exc}") from exc
    if result.returncode != 0:
        raise StartupError(f"FFmpeg 自检失败：{compact_error(result.stderr)}")


def sanitize_stem(stem: str, index: int) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", stem).strip().rstrip(". ")
    if not cleaned:
        cleaned = f"track_{index:03d}"
    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def find_matching_lrc(audio: Path) -> Path | None:
    matches = [
        item
        for item in audio.parent.iterdir()
        if item.is_file()
        and item.suffix.casefold() == ".lrc"
        and item.stem.casefold() == audio.stem.casefold()
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: (item.name.casefold(), item.name))[0]


def discover_tracks(source: Path) -> list[Track]:
    audio_files = [
        item
        for item in source.rglob("*")
        if item.is_file() and item.suffix.casefold() in MEDIA_EXTENSIONS
    ]
    audio_files.sort(
        key=lambda item: (
            item.relative_to(source).as_posix().casefold(),
            item.relative_to(source).as_posix(),
        )
    )

    tracks: list[Track] = []
    used_stems: set[str] = set()
    for index, audio in enumerate(audio_files, start=1):
        base_stem = sanitize_stem(audio.stem, index)
        output_stem = base_stem
        suffix = 2
        while output_stem.casefold() in used_stems:
            output_stem = f"{base_stem} ({suffix})"
            suffix += 1
        used_stems.add(output_stem.casefold())
        tracks.append(
            Track(
                source=audio,
                relative_source=audio.relative_to(source),
                output_stem=output_stem,
                lyric_source=find_matching_lrc(audio),
            )
        )
    return tracks


def run_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except OSError as exc:
        raise TrackError(f"无法运行 FFmpeg：{exc}") from exc


def parse_loudness_measurements(stderr: str) -> dict[str, str]:
    for match in re.finditer(r"\{[^{}]*\}", stderr, re.DOTALL):
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if not all(key in data for key in LOUDNESS_KEYS):
            continue
        try:
            if not all(math.isfinite(float(data[key])) for key in LOUDNESS_KEYS):
                break
        except (TypeError, ValueError):
            break
        return {key: str(data[key]) for key in LOUDNESS_KEYS}
    raise TrackError("FFmpeg 未返回有效的响度测量结果，音频可能为空或损坏。")


def normalize_audio(ffmpeg: Path, source: Path, target: Path) -> None:
    analysis_filter = "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json"
    null_output = "NUL" if os.name == "nt" else os.devnull
    first_pass = run_ffmpeg(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-af",
            analysis_filter,
            "-f",
            "null",
            null_output,
        ]
    )
    if first_pass.returncode != 0:
        raise TrackError(f"响度分析失败：{compact_error(first_pass.stderr)}")
    measured = parse_loudness_measurements(first_pass.stderr)

    second_filter = (
        "loudnorm=I=-16:TP=-1.5:LRA=11:"
        f"measured_I={measured['input_i']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:"
        "linear=true:print_format=summary"
    )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}.", suffix=".tmp.mp3", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        second_pass = run_ffmpeg(
            [
                str(ffmpeg),
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-sn",
                "-dn",
                "-af",
                second_filter,
                "-ar",
                "44100",
                "-ac",
                "2",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "320k",
                str(temporary),
            ]
        )
        if second_pass.returncode != 0:
            raise TrackError(f"音频转换失败：{compact_error(second_pass.stderr)}")
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise TrackError("音频转换未生成有效输出文件。")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def decode_lrc(source: Path) -> str:
    raw = source.read_bytes()
    encodings = ("utf-8-sig", "utf-8", "gb18030")
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError("无法按 UTF-8、UTF-8 BOM 或 GB18030 解码")


def atomic_write_utf8(target: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def compact_error(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if not lines:
        return "未知错误"
    return " | ".join(lines[-4:])


def process_track(
    track: Track,
    output: Path,
    ffmpeg: Path,
    overwrite: bool,
    counters: Counters,
) -> ReportEntry:
    audio_target = output / f"{track.output_stem}.mp3"
    details: list[str] = []

    if audio_target.exists() and not overwrite:
        counters.skipped += 1
        status = "跳过"
        details.append("音频已存在")
    else:
        try:
            normalize_audio(ffmpeg, track.source, audio_target)
        except TrackError as exc:
            counters.failed += 1
            return ReportEntry(track.source, audio_target, "失败", str(exc))
        counters.succeeded += 1
        status = "成功"
        details.append("音频已转换")

    lyric_target = output / f"{track.output_stem}.lrc"
    if track.lyric_source is None:
        counters.warnings += 1
        details.append("警告：未找到同名 LRC")
    elif lyric_target.exists() and not overwrite:
        details.append("LRC 已存在，跳过")
    else:
        try:
            lyric_text = decode_lrc(track.lyric_source)
            atomic_write_utf8(lyric_target, lyric_text)
            details.append("LRC 已转为 UTF-8")
        except (OSError, UnicodeError) as exc:
            counters.warnings += 1
            details.append(f"警告：LRC 处理失败：{exc}")

    if any(detail.startswith("警告：") for detail in details):
        status = f"{status}（有警告）"
    return ReportEntry(track.source, audio_target, status, "；".join(details))


def write_report(
    output: Path,
    ffmpeg: Path,
    entries: list[ReportEntry],
    counters: Counters,
    interrupted: bool,
) -> Path:
    report = output / REPORT_NAME
    lines = [
        "On Screen Music 歌单预处理报告",
        f"FFmpeg：{ffmpeg}",
        (
            f"成功：{counters.succeeded}，跳过：{counters.skipped}，"
            f"警告：{counters.warnings}，失败：{counters.failed}"
        ),
        f"用户中断：{'是' if interrupted else '否'}",
        "",
    ]
    for entry in entries:
        source = str(entry.source).replace("\t", " ").replace("\r", " ").replace("\n", " ")
        target = str(entry.target).replace("\t", " ").replace("\r", " ").replace("\n", " ")
        detail = entry.detail.replace("\t", " ").replace("\r", " ").replace("\n", " ")
        lines.append(f"[{entry.status}] {source} -> {target} | {detail}")
    atomic_write_utf8(report, "\n".join(lines) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = parse_args(argv)

    try:
        source, output = resolve_directories(args.source, args.output)
        ffmpeg = locate_ffmpeg(args.ffmpeg)
        validate_ffmpeg(ffmpeg)
        tracks = discover_tracks(source)
        output.mkdir(parents=True, exist_ok=True)
    except StartupError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 2

    print(f"源目录：{source}")
    print(f"输出目录：{output}")
    print(f"FFmpeg：{ffmpeg}")
    print(f"发现媒体文件：{len(tracks)} 个")

    counters = Counters()
    entries: list[ReportEntry] = []
    interrupted = False
    try:
        for index, track in enumerate(tracks, start=1):
            print(f"[{index}/{len(tracks)}] {track.relative_source}")
            entry = process_track(track, output, ffmpeg, args.overwrite, counters)
            entries.append(entry)
            print(f"  {entry.status}：{entry.detail}")
    except KeyboardInterrupt:
        interrupted = True
        print("\n用户中断，正在写入已完成项目的报告……", file=sys.stderr)

    try:
        report = write_report(output, ffmpeg, entries, counters, interrupted)
    except OSError as exc:
        print(f"报告写入失败：{exc}", file=sys.stderr)
        if interrupted:
            return 130
        return 1

    print(
        f"完成：成功 {counters.succeeded}，跳过 {counters.skipped}，"
        f"警告 {counters.warnings}，失败 {counters.failed}"
    )
    print(f"报告：{report}")

    if interrupted:
        return 130
    if counters.failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
