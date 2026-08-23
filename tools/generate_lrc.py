#!/usr/bin/env python3
"""Generate draft LRC files for a directory of audio files with whisper.cpp."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path


AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".wma",
}
FALLBACK_FFMPEG = Path(
    r"C:\Program Files (x86)\FFmpeg\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe"
)
STRONGEST_MODEL_NAME = "ggml-large-v3.bin"
FALLBACK_MODEL_NAME = "ggml-large-v3-turbo-q5_0.bin"
KNOWN_MODEL_SIZES = {
    STRONGEST_MODEL_NAME: 3_095_033_483,
    FALLBACK_MODEL_NAME: 574_041_195,
}
REPORT_NAME = "generate_lrc_report.txt"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LRC_LINE = re.compile(r"^\[(\d+):([0-5]\d)(?:\.(\d{1,3}))?\](.*)$")
PROGRESS_LINE = re.compile(r"progress\s*=\s*(\d+)%", re.IGNORECASE)
LYRIC_CREDIT_LINE = re.compile(
    r"^(?:作词|作曲|编曲|词曲|演唱|歌手|制作人)\s*[:：]?\s*\S"
)
HALLUCINATION_MARKERS = (
    "yoyotelevisionseriesexclusive",
    "televisionseriesexclusive",
    "独播剧场",
    "字幕制作",
    "字幕由",
    "感谢观看",
    "谢谢观看",
    "请不吝点赞",
    "请点赞订阅",
    "amaraorg",
)
NON_LYRIC_LABELS = {
    "music",
    "pianomusic",
    "instrumental",
    "zitherharp",
    "音乐",
    "纯音乐",
    "间奏",
}
SUPPRESS_REGEX = r"YoYo|Television|Series|Exclusive|Amara\.org"


class StartupError(RuntimeError):
    """An error that prevents batch processing from starting."""


class TrackError(RuntimeError):
    """An error limited to one audio file."""


@dataclass(frozen=True)
class Track:
    source: Path
    relative_source: Path
    relative_target: Path


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
    failed: int = 0


@dataclass(frozen=True)
class NormalizedLrc:
    text: str
    repaired_characters: int
    filtered_hallucination_lines: int
    repetition_warning: str | None


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="识别单首歌曲或目录中的歌曲，并在输出目录生成同名 LRC 草稿。"
    )
    parser.add_argument("--source", required=True, help="待识别音频文件或歌曲目录")
    parser.add_argument("--output", required=True, help="LRC 输出目录")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的 LRC")
    parser.add_argument("--language", default="auto", help="识别语言，默认 auto")
    parser.add_argument("--ffmpeg", help="显式指定 ffmpeg.exe 路径")
    parser.add_argument("--whisper", help="显式指定 whisper-cli.exe 路径")
    parser.add_argument("--model", help="显式指定 whisper.cpp 模型文件")
    parser.add_argument("--threads", type=int, help="传给 whisper.cpp 的线程数")
    parser.add_argument("--no-gpu", action="store_true", help="强制 whisper.cpp 只用 CPU")
    parser.add_argument(
        "--allow-repetition",
        action="store_true",
        help="允许输出被通用规则判定为大量重复的歌词",
    )
    return parser.parse_args(argv)


def resolve_source_and_output(source_arg: str, output_arg: str) -> tuple[Path, Path]:
    source = Path(source_arg).expanduser()
    if not source.exists():
        raise StartupError(f"源路径不存在：{source}")
    if not source.is_file() and not source.is_dir():
        raise StartupError(f"源路径不是普通文件或目录：{source}")

    source = source.resolve()
    output = Path(output_arg).expanduser().resolve(strict=False)
    if output.exists() and not output.is_dir():
        raise StartupError(f"输出路径不是目录：{output}")
    if source.is_dir() and (
        source == output or source in output.parents or output in source.parents
    ):
        raise StartupError("源目录和输出目录不能相同，也不能互相包含。")
    return source, output


def resolve_explicit_file(value: str, option: str) -> Path:
    candidate = Path(value).expanduser().resolve(strict=False)
    if not candidate.is_file():
        raise StartupError(f"{option} 指定的文件不存在：{candidate}")
    return candidate


def locate_ffmpeg(explicit_path: str | None) -> Path:
    if explicit_path:
        return resolve_explicit_file(explicit_path, "--ffmpeg")
    from_path = shutil.which("ffmpeg.exe") or shutil.which("ffmpeg")
    if from_path:
        return Path(from_path).resolve()
    if FALLBACK_FFMPEG.is_file():
        return FALLBACK_FFMPEG
    raise StartupError("找不到 FFmpeg。请使用 --ffmpeg 指定 ffmpeg.exe。")


def locate_whisper(explicit_path: str | None) -> Path:
    if explicit_path:
        return resolve_explicit_file(explicit_path, "--whisper")

    from_path = shutil.which("whisper-cli.exe") or shutil.which("whisper-cli")
    if from_path:
        return Path(from_path).resolve()

    tool_root = Path(__file__).resolve().parent / "whisper"
    candidates = (
        tool_root / "whisper-cli.exe",
        tool_root / "Release" / "whisper-cli.exe",
        tool_root / "bin" / "whisper-cli.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise StartupError(
        "找不到 whisper-cli.exe。请放到 tools\\whisper 中，或使用 --whisper 指定。"
    )


def locate_model(explicit_path: str | None) -> Path:
    if explicit_path:
        return resolve_explicit_file(explicit_path, "--model")

    tool_root = Path(__file__).resolve().parent / "whisper"
    candidates = tuple(
        candidate
        for model_name in (STRONGEST_MODEL_NAME, FALLBACK_MODEL_NAME)
        for candidate in (
            tool_root / "models" / model_name,
            tool_root / model_name,
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise StartupError(
        f"找不到模型 {STRONGEST_MODEL_NAME} 或 {FALLBACK_MODEL_NAME}。"
        "请放到 tools\\whisper\\models 中，或使用 --model 指定。"
    )


def run_startup_check(command: list[str], name: str) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StartupError(f"无法启动 {name}：{exc}") from exc
    output = "\n".join((result.stdout, result.stderr)).strip()
    if result.returncode != 0:
        raise StartupError(f"{name} 自检失败：{compact_error(output)}")
    return output


def validate_tools(ffmpeg: Path, whisper: Path) -> None:
    run_startup_check([str(ffmpeg), "-hide_banner", "-version"], "FFmpeg")
    help_text = run_startup_check([str(whisper), "--help"], "whisper.cpp")
    required_options = ("--output-lrc", "--output-file", "--print-progress")
    if not all(option in help_text for option in required_options):
        raise StartupError("whisper.cpp 版本过旧，缺少 LRC 输出或进度显示参数。")


def validate_model(model: Path) -> None:
    size = model.stat().st_size
    if size < 1_000_000:
        raise StartupError(f"模型文件明显不完整：{model}（{size} 字节）")
    expected_size = KNOWN_MODEL_SIZES.get(model.name.casefold())
    if expected_size is not None and size != expected_size:
        raise StartupError(
            f"模型大小不正确：应为 {expected_size} 字节，实际为 {size} 字节。"
        )


def discover_tracks(source: Path) -> list[Track]:
    if source.is_file():
        if source.suffix.casefold() not in AUDIO_EXTENSIONS:
            supported = "、".join(sorted(AUDIO_EXTENSIONS))
            raise StartupError(f"不支持该音频类型：{source.suffix}；支持：{supported}")
        return [
            Track(
                source=source,
                relative_source=Path(source.name),
                relative_target=Path(source.name).with_suffix(".lrc"),
            )
        ]

    audio_files = [
        item
        for item in source.rglob("*")
        if item.is_file() and item.suffix.casefold() in AUDIO_EXTENSIONS
    ]
    audio_files.sort(
        key=lambda item: (
            item.relative_to(source).as_posix().casefold(),
            item.relative_to(source).as_posix(),
        )
    )
    return [
        Track(
            source=item,
            relative_source=item.relative_to(source),
            relative_target=item.relative_to(source).with_suffix(".lrc"),
        )
        for item in audio_files
    ]


def find_output_conflicts(tracks: list[Track]) -> dict[str, list[Track]]:
    groups: dict[str, list[Track]] = defaultdict(list)
    for track in tracks:
        key = track.relative_target.as_posix().casefold()
        groups[key].append(track)
    return {key: group for key, group in groups.items() if len(group) > 1}


def run_ffmpeg(ffmpeg: Path, source: Path, temporary_wav: Path) -> None:
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(temporary_wav),
    ]
    try:
        result = subprocess.run(
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
    if result.returncode != 0:
        raise TrackError(f"音频读取失败：{compact_error(result.stderr)}")
    if not temporary_wav.is_file() or temporary_wav.stat().st_size <= 44:
        raise TrackError("FFmpeg 未生成有效的临时音频。")


def build_lyrics_prompt(source: Path, language: str) -> str:
    title = source.stem.strip()
    if language.casefold() == "zh":
        return f"歌曲《{title}》的中文歌词。"
    if language.casefold() == "auto":
        return f"《{title}》 Lyrics"
    return f"Song title: {title}. Lyrics."


def build_whisper_command(
    whisper: Path,
    model: Path,
    temporary_wav: Path,
    output_prefix: Path,
    language: str,
    prompt: str,
    threads: int | None,
    no_gpu: bool,
) -> list[str]:
    command = [
        str(whisper),
        "-m",
        str(model),
        "-f",
        str(temporary_wav),
        "-l",
        language,
        "-olrc",
        "-of",
        str(output_prefix),
        "-pp",
        "-sns",
        "-nf",
        "-mc",
        "0",
        "--prompt",
        prompt,
        "--suppress-regex",
        SUPPRESS_REGEX,
    ]
    if threads is not None:
        command.extend(("-t", str(threads)))
    if no_gpu:
        command.append("-ng")
    return command


def run_whisper(
    whisper: Path,
    model: Path,
    temporary_wav: Path,
    output_prefix: Path,
    language: str,
    prompt: str,
    threads: int | None,
    no_gpu: bool,
) -> Path:
    command = build_whisper_command(
        whisper,
        model,
        temporary_wav,
        output_prefix,
        language,
        prompt,
        threads,
        no_gpu,
    )

    output_tail: deque[str] = deque(maxlen=8)
    last_progress = -1
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError as exc:
        raise TrackError(f"无法运行 whisper.cpp：{exc}") from exc

    assert process.stdout is not None
    try:
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            output_tail.append(line)
            match = PROGRESS_LINE.search(line)
            if match:
                progress = int(match.group(1))
                if progress != last_progress:
                    print(f"  识别进度：{progress:3d}%", flush=True)
                    last_progress = progress
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise

    generated = output_prefix.with_suffix(".lrc")
    if return_code != 0:
        output_summary = compact_error("\n".join(output_tail))
        raise TrackError(f"歌词识别失败：{output_summary}")
    if not generated.is_file() or generated.stat().st_size == 0:
        raise TrackError("whisper.cpp 未生成 LRC 文件。")
    return generated


def compact_lyric_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def is_hallucination_line(text: str) -> bool:
    compact = compact_lyric_text(text)
    if any(marker in compact for marker in HALLUCINATION_MARKERS):
        return True
    if compact in NON_LYRIC_LABELS:
        return True
    return LYRIC_CREDIT_LINE.match(text) is not None


def repeated_lyric_error(lyrics: list[str]) -> str | None:
    if len(lyrics) < 8:
        return None

    compact_lines = [compact_lyric_text(line) for line in lyrics]
    counts: dict[str, int] = defaultdict(int)
    for line in compact_lines:
        counts[line] += 1
    most_common, count = max(counts.items(), key=lambda item: item[1])
    if count >= 8 and count / len(compact_lines) >= 0.5:
        return f"同一句歌词重复 {count}/{len(compact_lines)} 次"

    longest_run = 1
    current_run = 1
    for previous, current in zip(compact_lines, compact_lines[1:]):
        if current == previous:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 1
    if longest_run >= 6:
        return f"同一句歌词连续重复 {longest_run} 次"
    return None


def normalize_lrc(generated: Path, allow_repetition: bool = False) -> NormalizedLrc:
    try:
        raw = generated.read_bytes()
    except OSError as exc:
        raise TrackError(f"无法读取生成的 LRC：{exc}") from exc

    repaired_characters = 0
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8-sig", errors="replace")
        repaired_characters = text.count("\ufffd")

    normalized_lines: list[str] = []
    lyrics: list[str] = []
    total_timed_lines = 0
    filtered_hallucination_lines = 0
    lyric_lines = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = LRC_LINE.match(line)
        if match:
            total_timed_lines += 1
            lyric = match.group(4).strip()
            if not lyric:
                continue
            if is_hallucination_line(lyric):
                filtered_hallucination_lines += 1
                continue
            timestamp = f"[{int(match.group(1)):02d}:{match.group(2)}"
            fraction = match.group(3)
            if fraction is not None:
                timestamp += f".{fraction[:2].ljust(2, '0')}"
            timestamp += "]"
            normalized_lines.append(f"{timestamp}{lyric}")
            lyrics.append(lyric)
            lyric_lines += 1
        elif line.startswith("[") and line.endswith("]"):
            normalized_lines.append(line)

    if lyric_lines == 0:
        if filtered_hallucination_lines:
            raise TrackError(
                f"识别结果疑似模型幻觉：{total_timed_lines} 行歌词中有 "
                f"{filtered_hallucination_lines} 行字幕水印或制作信息，已拒绝输出。"
            )
        raise TrackError("没有识别出任何带时间戳的歌词。")

    repetition_error = repeated_lyric_error(lyrics)
    if repetition_error and not allow_repetition:
        raise TrackError(f"识别结果疑似模型幻觉：{repetition_error}，已拒绝输出。")

    return NormalizedLrc(
        text="\n".join(normalized_lines) + "\n",
        repaired_characters=repaired_characters,
        filtered_hallucination_lines=filtered_hallucination_lines,
        repetition_warning=repetition_error,
    )


def atomic_write_utf8(target: Path, text: str, overwrite: bool) -> None:
    if not overwrite:
        try:
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
        except FileExistsError as exc:
            raise TrackError("目标 LRC 在处理期间已被其他程序创建。") from exc
        return

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


def process_track(
    track: Track,
    output: Path,
    ffmpeg: Path,
    whisper: Path,
    model: Path,
    language: str,
    threads: int | None,
    no_gpu: bool,
    overwrite: bool,
    allow_repetition: bool = False,
) -> ReportEntry:
    target = output / track.relative_target
    if target.exists() and not overwrite:
        return ReportEntry(track.source, target, "跳过", "目标 LRC 已存在")

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="on_screen_music_lrc_") as temp_name:
        temp_dir = Path(temp_name)
        temporary_wav = temp_dir / "audio.wav"
        output_prefix = temp_dir / "result"
        run_ffmpeg(ffmpeg, track.source, temporary_wav)
        generated = run_whisper(
            whisper,
            model,
            temporary_wav,
            output_prefix,
            language,
            build_lyrics_prompt(track.source, language),
            threads,
            no_gpu,
        )
        normalized = normalize_lrc(generated, allow_repetition)
        atomic_write_utf8(target, normalized.text, overwrite)
    detail = "已生成 UTF-8 LRC 草稿"
    if normalized.filtered_hallucination_lines:
        detail += f"；已过滤 {normalized.filtered_hallucination_lines} 行字幕水印或制作信息"
    if normalized.repaired_characters:
        detail += (
            f"；警告：whisper.cpp 输出含 {normalized.repaired_characters} 处不完整字符，"
            "已替换为 �，请人工校对"
        )
    if normalized.repetition_warning:
        detail += f"；警告：{normalized.repetition_warning}，已按用户设置保留"
    return ReportEntry(track.source, target, "成功", detail)


def compact_error(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return "未知错误"
    return " | ".join(lines[-4:])


def clean_report_text(value: object) -> str:
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def write_report(
    output: Path,
    model: Path,
    entries: list[ReportEntry],
    counters: Counters,
    interrupted: bool,
) -> Path:
    report = output / REPORT_NAME
    lines = [
        "On Screen Music 批量歌词识别报告",
        f"模型：{model}",
        (
            f"成功：{counters.succeeded}，跳过：{counters.skipped}，"
            f"失败：{counters.failed}"
        ),
        f"用户中断：{'是' if interrupted else '否'}",
        "",
    ]
    for entry in entries:
        lines.append(
            f"[{entry.status}] {clean_report_text(entry.source)} -> "
            f"{clean_report_text(entry.target)} | {clean_report_text(entry.detail)}"
        )
    text = "\n".join(lines) + "\n"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{REPORT_NAME}.", suffix=".tmp", dir=output
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, report)
    finally:
        temporary.unlink(missing_ok=True)
    return report


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = parse_args(argv)

    if args.threads is not None and args.threads < 1:
        print("启动失败：--threads 必须大于 0。", file=sys.stderr)
        return 2

    try:
        source, output = resolve_source_and_output(args.source, args.output)
        ffmpeg = locate_ffmpeg(args.ffmpeg)
        whisper = locate_whisper(args.whisper)
        model = locate_model(args.model)
        validate_tools(ffmpeg, whisper)
        validate_model(model)
        tracks = discover_tracks(source)
        conflicts = find_output_conflicts(tracks)
        output.mkdir(parents=True, exist_ok=True)
    except (StartupError, OSError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 2

    print(f"源输入：{source}")
    print(f"输出目录：{output}")
    print(f"Whisper：{whisper}")
    print(f"模型：{model}")
    if model.name.casefold() == FALLBACK_MODEL_NAME.casefold():
        print(
            f"提示：未安装完整 {STRONGEST_MODEL_NAME}，当前使用 {model.name}。"
        )
    print("识别模式：完整抗幻觉模式")
    print(f"识别语言：{args.language}")
    print(f"发现音频：{len(tracks)} 首")

    conflicting_ids = {
        id(track)
        for group in conflicts.values()
        for track in group
    }
    counters = Counters()
    entries: list[ReportEntry] = []
    interrupted = False

    try:
        for index, track in enumerate(tracks, start=1):
            print(f"[{index}/{len(tracks)}] {track.relative_source}")
            target = output / track.relative_target
            if id(track) in conflicting_ids:
                group = conflicts[track.relative_target.as_posix().casefold()]
                names = "、".join(str(item.relative_source) for item in group)
                entry = ReportEntry(
                    track.source,
                    target,
                    "失败",
                    f"多个音频会生成同一个 LRC：{names}",
                )
            else:
                try:
                    entry = process_track(
                        track,
                        output,
                        ffmpeg,
                        whisper,
                        model,
                        args.language,
                        args.threads,
                        args.no_gpu,
                        args.overwrite,
                        args.allow_repetition,
                    )
                except (TrackError, OSError) as exc:
                    entry = ReportEntry(track.source, target, "失败", str(exc))

            entries.append(entry)
            if entry.status == "成功":
                counters.succeeded += 1
            elif entry.status == "跳过":
                counters.skipped += 1
            else:
                counters.failed += 1
            print(f"  {entry.status}：{entry.detail}")
    except KeyboardInterrupt:
        interrupted = True
        print("\n用户中断，正在写入已完成项目的报告……", file=sys.stderr)

    try:
        report = write_report(output, model, entries, counters, interrupted)
    except OSError as exc:
        print(f"报告写入失败：{exc}", file=sys.stderr)
        return 130 if interrupted else 1

    print(
        f"完成：成功 {counters.succeeded}，跳过 {counters.skipped}，"
        f"失败 {counters.failed}"
    )
    print(f"报告：{report}")

    if interrupted:
        return 130
    return 1 if counters.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
