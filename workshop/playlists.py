"""One visible row per song, preserving the player's weighted TXT contract."""
from dataclasses import dataclass
from pathlib import Path
from .core import library_path, parse_playlist


@dataclass
class PlaylistEntry:
    audio: str
    lyric: str
    weight: int = 1
    use_lyrics: bool = True


@dataclass(frozen=True)
class PlaylistIssue:
    number: int
    text: str
    reason: str
    unparsed: bool = False

    def description(self):
        return f"第 {self.number} 行：{self.reason}"


def inspect_playlist(root: Path, text: str):
    """Return the original valid lines and one issue per rejected line, without writing files."""
    kept, issues, mappings, checked = [], [], {}, {}
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            kept.append(raw)
            continue
        rows, errors = parse_playlist(raw)
        if errors:
            issues.append(PlaylistIssue(number, raw, errors[0].removeprefix("第 1 行："), True))
            continue
        audio, lyric = rows[0]
        previous = mappings.setdefault(audio.casefold(), lyric.casefold())
        if previous != lyric.casefold():
            issues.append(PlaylistIssue(number, raw, "同一首歌配置了不同歌词", True))
            continue
        key = (audio.casefold(), lyric.casefold())
        if key not in checked:
            missing = []
            try:
                if not library_path(root, "music", audio).is_file():
                    missing.append("音乐缺失：" + audio)
                if lyric != "-" and not library_path(root, "lyrics", lyric).is_file():
                    missing.append("歌词缺失：" + lyric)
            except (OSError, ValueError) as exc:
                missing.append(str(exc))
            checked[key] = "；".join(missing)
        if checked[key]:
            issues.append(PlaylistIssue(number, raw, checked[key]))
        else:
            kept.append(raw)
    return "\n".join(kept) + ("\n" if kept else ""), issues


def read_entries(text, *, strict=True):
    rows, errors = parse_playlist(text)
    if errors and strict:
        raise ValueError("\n".join(errors))
    entries = {}
    comments = [line for line in text.splitlines() if line.lstrip().startswith("#")]
    for audio, lyric in rows:
        key = audio.casefold()
        if key in entries:
            entries[key].weight += 1
        else:
            entries[key] = PlaylistEntry(audio, lyric if lyric != "-" else Path(audio).stem + ".lrc", 1, lyric != "-")
    return list(entries.values()), comments


def write_entries(entries, comments):
    lines = list(comments)
    used = set()
    for entry in entries:
        if entry.audio.casefold() in used:
            raise ValueError("歌单中不能重复添加同一首歌。")
        used.add(entry.audio.casefold())
        if type(entry.weight) is not int or not 1 <= entry.weight <= 10000:
            raise ValueError("权重须为 1–10000 的整数。")
        lines.extend([f"{entry.audio}|{entry.lyric if entry.use_lyrics else '-'}"] * entry.weight)
    text = "\n".join(lines) + ("\n" if lines else "")
    _, errors = parse_playlist(text)
    if errors:
        raise ValueError("\n".join(errors))
    return text
