#!/usr/bin/env python3
"""Convert a PotPlayer DPL file to an On Screen Music playlist."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path, PureWindowsPath


FILE_RECORD = re.compile(r"^\s*\d+\*file\*(.*)$")


class ConversionError(RuntimeError):
    """An input or output error that prevents conversion."""


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 PotPlayer DPL 歌单转换为 On Screen Music 的 UTF-8 歌单。"
    )
    parser.add_argument("--source", required=True, help="输入的 .dpl 文件")
    parser.add_argument(
        "--output",
        help="输出的 .txt 文件；默认与输入文件同目录、同名",
    )
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的输出文件")
    return parser.parse_args(argv)


def decode_dpl(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise ConversionError("DPL 的 UTF-16 内容无法解码。") from exc

    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ConversionError("DPL 不是有效的 UTF-8、UTF-16 或 GB18030 文本。")


def extract_audio_names(text: str) -> tuple[list[str], list[str]]:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line != "DAUMPLAYLIST":
        raise ConversionError("文件头不是 DAUMPLAYLIST，无法确认这是 PotPlayer DPL。")

    audio_names: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = FILE_RECORD.match(line)
        if match is None:
            continue

        audio_name = PureWindowsPath(match.group(1)).name
        if not audio_name:
            warnings.append(f"第 {line_number} 行没有文件名，已跳过")
            continue
        if PureWindowsPath(audio_name).suffix.casefold() != ".mp3":
            warnings.append(f"第 {line_number} 行不是 MP3，已跳过：{audio_name}")
            continue

        key = audio_name.casefold()
        if key in seen:
            warnings.append(f"第 {line_number} 行重复列出歌曲，已跳过：{audio_name}")
            continue
        seen.add(key)
        audio_names.append(audio_name)

    if not audio_names:
        raise ConversionError("DPL 中没有可转换的 MP3 文件记录。")
    return audio_names, warnings


def build_playlist(audio_names: list[str]) -> str:
    lines = [
        f"{audio_name}|{PureWindowsPath(audio_name).stem}.lrc"
        for audio_name in audio_names
    ]
    return "\n".join(lines) + "\n"


def resolve_paths(source_arg: str, output_arg: str | None) -> tuple[Path, Path]:
    source = Path(source_arg).expanduser()
    if not source.is_file():
        raise ConversionError(f"找不到 DPL 文件：{source}")
    source = source.resolve()
    output = (
        Path(output_arg).expanduser().resolve(strict=False)
        if output_arg
        else source.with_suffix(".txt")
    )
    if output.exists() and not output.is_file():
        raise ConversionError(f"输出路径不是普通文件：{output}")
    return source, output


def write_playlist(output: Path, text: str, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise ConversionError(f"输出文件已存在：{output}；如需覆盖请加入 --overwrite。")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, output)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = parse_args(argv)
    try:
        source, output = resolve_paths(args.source, args.output)
        text = decode_dpl(source.read_bytes())
        audio_names, warnings = extract_audio_names(text)
        write_playlist(output, build_playlist(audio_names), args.overwrite)
    except (ConversionError, OSError) as exc:
        print(f"转换失败：{exc}", file=sys.stderr)
        return 2

    for warning in warnings:
        print(f"警告：{warning}", file=sys.stderr)
    print(f"转换完成：{len(audio_names)} 首")
    print(f"输出文件：{output}")
    print("说明：未检查音乐或歌词文件是否存在。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
