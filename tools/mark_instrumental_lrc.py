#!/usr/bin/env python3
"""Find obviously invalid repetitive LRC files and mark them as instrumental."""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


REPORT_NAME = "mark_instrumental_report.txt"
INSTRUMENTAL_TEXT = "#INSTRUMENTAL\n"
TIMED_LINE = re.compile(r"^(?:\[\d+:[0-5]\d(?:\.\d{1,3})?\])+(.*)$")
CREDIT_LINE = re.compile(
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


class ScanError(RuntimeError):
    pass


@dataclass(frozen=True)
class Analysis:
    candidate: bool
    reason: str
    timed_lines: int
    unique_lines: int
    already_instrumental: bool = False


@dataclass(frozen=True)
class ReportEntry:
    path: Path
    status: str
    detail: str


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="扫描异常重复的 LRC；默认仅预览，加入 --apply 后标记为纯音乐。"
    )
    parser.add_argument("--source", required=True, help="待扫描的歌词目录")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="将确认命中的 LRC 原子替换为 #INSTRUMENTAL",
    )
    parser.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    return parser.parse_args(argv)


def compact_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def decode_lrc(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ScanError("无法读取：{}".format(exc)) from exc

    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ScanError("无法按 UTF-8 或 GB18030 解码")


def extract_timed_lyrics(text: str) -> List[str]:
    lyrics = []
    for raw_line in text.splitlines():
        match = TIMED_LINE.match(raw_line.strip())
        if not match:
            continue
        lyric = match.group(1).strip()
        if lyric:
            lyrics.append(lyric)
    return lyrics


def longest_identical_run(lines: Sequence[str]) -> int:
    if not lines:
        return 0
    longest = 1
    current = 1
    for previous, line in zip(lines, lines[1:]):
        if line == previous:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def analyze_lrc_text(text: str) -> Analysis:
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    if nonempty and nonempty[0].casefold() == "#instrumental":
        return Analysis(False, "已经标注为纯音乐", 0, 0, True)

    lyrics = extract_timed_lyrics(text)
    if not lyrics:
        return Analysis(False, "没有带时间戳的歌词，无法可靠判断", 0, 0)

    compact_lines = [compact_text(line) for line in lyrics]
    counts = Counter(compact_lines)
    unique_lines = len(counts)
    timed_lines = len(compact_lines)

    if timed_lines < 10:
        return Analysis(
            True,
            "只有 {} 行带时间戳歌词，不足 10 行".format(timed_lines),
            timed_lines,
            unique_lines,
        )

    label_count = sum(line in NON_LYRIC_LABELS for line in compact_lines)
    if label_count == timed_lines:
        return Analysis(
            True,
            "全部内容都是纯音乐占位标签（{}/{} 行）".format(
                label_count, timed_lines
            ),
            timed_lines,
            unique_lines,
        )

    suspicious_count = 0
    for original, compact in zip(lyrics, compact_lines):
        if (
            any(marker in compact for marker in HALLUCINATION_MARKERS)
            or CREDIT_LINE.match(original) is not None
            or compact in NON_LYRIC_LABELS
        ):
            suspicious_count += 1
    if timed_lines >= 6 and suspicious_count / timed_lines >= 0.8:
        return Analysis(
            True,
            "字幕水印、制作信息或占位内容占 {}/{} 行".format(
                suspicious_count, timed_lines
            ),
            timed_lines,
            unique_lines,
        )

    most_common_line, most_common_count = counts.most_common(1)[0]
    repeated_ratio = most_common_count / timed_lines
    longest_run = longest_identical_run(compact_lines)
    if (
        timed_lines >= 8
        and unique_lines <= 3
        and most_common_count >= 6
        and repeated_ratio >= 0.7
    ):
        return Analysis(
            True,
            "同一句内容重复 {}/{} 次，全文只有 {} 种内容".format(
                most_common_count, timed_lines, unique_lines
            ),
            timed_lines,
            unique_lines,
        )
    if timed_lines >= 10 and unique_lines <= 3 and longest_run >= 8:
        return Analysis(
            True,
            "同一句内容连续重复 {} 次，全文只有 {} 种内容".format(
                longest_run, unique_lines
            ),
            timed_lines,
            unique_lines,
        )

    return Analysis(
        False,
        "未达到保守的异常重复判定阈值",
        timed_lines,
        unique_lines,
    )


def discover_lrc_files(source: Path, recursive: bool) -> List[Path]:
    iterator: Iterable[Path] = source.rglob("*") if recursive else source.iterdir()
    return sorted(
        (
            path
            for path in iterator
            if path.is_file() and path.suffix.casefold() == ".lrc"
        ),
        key=lambda path: path.relative_to(source).as_posix().casefold(),
    )


def replace_with_instrumental(path: Path) -> None:
    temporary = path.with_name(".{}.{}.tmp".format(path.name, uuid.uuid4().hex))
    try:
        temporary.write_text(INSTRUMENTAL_TEXT, encoding="utf-8", newline="\n")
        os.replace(str(temporary), str(path))
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise ScanError("写入失败：{}".format(exc)) from exc


def write_report(
    source: Path,
    apply_changes: bool,
    entries: Sequence[ReportEntry],
) -> Path:
    report = source / REPORT_NAME
    mode = "已执行替换" if apply_changes else "仅预览，未修改 LRC"
    lines = ["异常纯音乐 LRC 扫描报告", "模式：{}".format(mode), ""]
    for entry in entries:
        relative = entry.path.relative_to(source)
        lines.append("[{}] {} | {}".format(entry.status, relative, entry.detail))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    configure_console()
    args = parse_args(argv)
    source = Path(args.source).expanduser().resolve(strict=False)
    if not source.is_dir():
        print("启动失败：歌词目录不存在：{}".format(source), file=sys.stderr)
        return 2

    files = discover_lrc_files(source, args.recursive)
    entries = []
    candidates = 0
    updated = 0
    failures = 0
    already_marked = 0

    print("歌词目录：{}".format(source))
    print("扫描模式：{}".format("递归" if args.recursive else "仅第一层"))
    print("操作模式：{}".format("执行替换" if args.apply else "仅预览"))
    print("发现 LRC：{} 个".format(len(files)))

    for path in files:
        relative = path.relative_to(source)
        try:
            analysis = analyze_lrc_text(decode_lrc(path))
            if analysis.already_instrumental:
                already_marked += 1
                entries.append(ReportEntry(path, "已标注", analysis.reason))
            elif analysis.candidate:
                candidates += 1
                if args.apply:
                    replace_with_instrumental(path)
                    updated += 1
                    status = "已更新"
                else:
                    status = "候选"
                entries.append(ReportEntry(path, status, analysis.reason))
                print("[{}] {} | {}".format(status, relative, analysis.reason))
            else:
                entries.append(ReportEntry(path, "正常", analysis.reason))
        except ScanError as exc:
            failures += 1
            entries.append(ReportEntry(path, "失败", str(exc)))
            print("[失败] {} | {}".format(relative, exc))

    try:
        report = write_report(source, args.apply, entries)
    except OSError as exc:
        print("报告写入失败：{}".format(exc), file=sys.stderr)
        return 1

    print(
        "完成：候选 {}，已更新 {}，原本已标注 {}，失败 {}".format(
            candidates, updated, already_marked, failures
        )
    )
    print("报告：{}".format(report))
    if not args.apply and candidates:
        print("确认候选无误后，用同一命令加 --apply 执行替换。")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
