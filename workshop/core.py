"""File contracts, staging and recoverable writes for Music Workshop."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from tools import prepare_music
from .shared_settings import ini_text, qt_decode, qt_encode, read_ini, settings_file, settings_guard

STAMP = re.compile(r"\[(\d+):([0-5]\d)(?:\.(\d{1,3}))?\]")
META = re.compile(r"^\[(?:ar|al|ti|au|by|offset|re|ve|length):[^\]\r\n]*\]$", re.I)
PENDING = "未处理"


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".workshop-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_text(path: Path) -> str:
    return decode_text(path.read_bytes(), path.name)


def decode_text(data: bytes, name: str) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeError:
            continue
    raise ValueError(f"无法读取文本编码：{name}")


def filename(name: str, suffix: str | None = None) -> str:
    if (not name or name in {".", ".."} or name != name.strip()
            or prepare_music.INVALID_FILENAME_CHARS.search(name)
            or name.endswith((".", " "))
            or Path(name).stem.upper() in prepare_music.WINDOWS_RESERVED_NAMES):
        raise ValueError(f"文件名无效，不能包含路径：{name!r}")
    if suffix and Path(name).suffix.casefold() != suffix:
        raise ValueError(f"文件必须是 {suffix}：{name}")
    return name


def library_path(root: Path, folder: str, name: str) -> Path:
    path = root / folder / filename(name)
    if not path.resolve().is_relative_to((root / folder).resolve()):
        raise ValueError("文件引用指向资料目录外。")
    return path


def validate_root(root: Path) -> None:
    for folder in ("music", "lyrics", "playlists"):
        if not (root / folder).is_dir():
            raise ValueError(f"资料根目录须已有 music、lyrics、playlists 三个子目录：{root}")


@dataclass
class Settings:
    library: str
    work: str
    ffmpeg: str = ""
    whisper: str = ""
    model: str = ""
    api_key: str = field(default="", repr=False)
    theme: str = "light"

    @classmethod
    def load(cls, base: Path) -> "Settings":
        path = settings_file(base)
        result = cls(str(path.parent), str(path.parent / "MusicWorkshopWork"),
                     whisper=str(path.parent / "tools/whisper/Release/whisper-cli.exe"),
                     model=str(path.parent / "tools/whisper/models/ggml-large-v3.bin"))
        with settings_guard(path):
            parser = read_ini(path)
            result.api_key = qt_decode(parser.get("Workshop", "ApiKey", fallback=""))
            saved_theme = parser.get("Workshop", "Theme", fallback="light")
            result.theme = saved_theme if saved_theme in {"light", "dark"} else "light"
            ffmpeg = qt_decode(parser.get("Workshop", "FFmpeg", fallback=""))
            result.ffmpeg = str((path.parent / ffmpeg).resolve()) if ffmpeg else ""
            for field, key in (("whisper", "Whisper"), ("model", "Model")):
                value = qt_decode(parser.get("Workshop", key, fallback=""))
                if value:
                    setattr(result, field, str((path.parent / value).resolve()))
        return result

    def validate(self) -> None:
        root, work = Path(self.library).resolve(), Path(self.work).resolve()
        validate_root(root)
        for folder in ("music", "lyrics", "playlists"):
            data = (root / folder).resolve()
            if data.is_relative_to(work) or work.is_relative_to(data):
                raise ValueError("工作目录不能与 music、lyrics、playlists 重合或相互包含。")

    def save(self, base: Path, fields: set[str] | None = None) -> None:
        path = settings_file(base)
        if Path(self.library).resolve() != path.parent or Path(self.work).resolve() != path.parent / "MusicWorkshopWork":
            raise ValueError("资料目录固定为软件所在目录，工作目录固定为其下的 MusicWorkshopWork。")
        self.validate()
        with settings_guard(path):
            parser = read_ini(path)
            for section in ("Library", "Workshop"):
                if not parser.has_section(section):
                    parser.add_section(section)
            parser.remove_option("Library", "Root")
            parser.remove_option("Workshop", "Work")
            selected = {"ffmpeg", "whisper", "model", "api_key", "theme"} if fields is None else fields
            defaults = {"whisper": "tools/whisper/Release/whisper-cli.exe", "model": "tools/whisper/models/ggml-large-v3.bin"}
            for field, key in (("ffmpeg", "FFmpeg"), ("whisper", "Whisper"), ("model", "Model")):
                if field not in selected:
                    continue
                value = getattr(self, field) or defaults.get(field, "")
                if value:
                    resolved = (path.parent / value).resolve()
                    value = resolved.relative_to(path.parent).as_posix() if resolved.is_relative_to(path.parent) else resolved.as_posix()
                parser.set("Workshop", key, qt_encode(value))
            if "api_key" in selected:
                parser.set("Workshop", "ApiKey", qt_encode(self.api_key))
            if "theme" in selected:
                parser.set("Workshop", "Theme", "dark" if self.theme == "dark" else "light")
            atomic_text(path, ini_text(parser))


@dataclass
class Song:
    name: str
    audio: Path
    lyric: Path | None
    playlists: list[str]


def parse_playlist(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    rows, errors, mappings = [], [], {}
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            if raw.count("|") != 1:
                raise ValueError("须使用 音乐文件名|歌词文件名")
            audio, lyric = [part.strip() for part in raw.split("|")]
            filename(audio, ".mp3")
            if lyric != "-":
                filename(lyric, ".lrc")
            previous = mappings.setdefault(audio.casefold(), lyric.casefold())
            if previous != lyric.casefold():
                raise ValueError("同一首歌配置了不同歌词")
            rows.append((audio, lyric))
        except ValueError as exc:
            errors.append(f"第 {number} 行：{exc}")
    return rows, errors


def check_playlist(root: Path, text: str) -> list[str]:
    rows, issues = parse_playlist(text)
    for audio, lyric in dict.fromkeys(rows):
        if not library_path(root, "music", audio).is_file():
            issues.append(f"音乐缺失：{audio}")
        if lyric != "-" and not library_path(root, "lyrics", lyric).is_file():
            issues.append(f"歌词缺失：{lyric}")
    return issues


def scan_library(root: Path) -> tuple[list[Song], list[str]]:
    validate_root(root)
    membership, warnings = {}, []
    playlists = sorted((root / "playlists").glob("*.txt"), key=lambda p: p.name.casefold())
    if not playlists and (root / "playlist.txt").is_file():
        playlists = [root / "playlist.txt"]
    for playlist in playlists:
        try:
            text = read_text(playlist)
            rows, _ = parse_playlist(text)
            warnings.extend(f"{playlist.name}：{issue}" for issue in check_playlist(root, text))
            for audio, lyric in dict.fromkeys(rows):
                membership.setdefault(audio.casefold(), []).append((playlist.name, lyric))
        except (OSError, ValueError) as exc:
            warnings.append(f"{playlist.name}：{exc}")
    songs = []
    for audio in sorted((root / "music").iterdir(), key=lambda p: p.name.casefold()):
        if not audio.is_file() or audio.suffix.casefold() != ".mp3":
            continue
        entries = membership.get(audio.name.casefold(), [])
        names = list(dict.fromkeys(lyric for _, lyric in entries))
        lyric_name = names[0] if names else audio.stem + ".lrc"
        if len(names) > 1:
            warnings.append(f"{audio.name}：不同歌单使用不同歌词；详情显示第一份映射。")
        lyric = library_path(root, "lyrics", lyric_name) if lyric_name != "-" else None
        songs.append(Song(audio.name, audio, lyric, list(dict.fromkeys(p for p, _ in entries))))
    return songs, warnings


def scan_audio_library(root: Path) -> list[Song]:
    """The music library is independent of playlist membership and lyric mappings."""
    validate_root(root)
    return [Song(path.name, path, library_path(root, "lyrics", path.stem + ".lrc"), [])
            for path in sorted((root / "music").iterdir(), key=lambda path: path.name.casefold())
            if path.is_file() and path.suffix.casefold() == ".mp3"]


def delete_playlist_file(settings: Settings, name: str) -> Path:
    settings.validate()
    target = library_path(Path(settings.library), "playlists", filename(name, ".txt"))
    original = target.read_bytes()
    backup = Path(settings.work) / "backups" / uuid.uuid4().hex / name
    backup.parent.mkdir(parents=True)
    backup.write_bytes(original)
    atomic_text(backup.parent / "restore.json", json.dumps({"target": str(target), "backup": str(backup)}, ensure_ascii=False))
    if target.read_bytes() != original:
        raise ValueError("歌单已被其他程序修改，请重新载入后再删除。")
    target.unlink()
    return backup


def validate_lrc(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()
    if text.splitlines() and text.splitlines()[0].strip() == "#INSTRUMENTAL":
        return "#INSTRUMENTAL\n"
    primary, count = [], 0
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or META.fullmatch(line.strip()):
            continue
        matches = list(STAMP.finditer(line))
        prefix = "".join(match.group() for match in matches)
        if not matches or not line.startswith(prefix):
            raise ValueError(f"第 {number} 行不是有效 LRC 时间标签。")
        primary.append(stamp_ms(matches[0]))
        count += len(matches)
    if not count:
        raise ValueError("没有有效的时间戳歌词。")
    if primary != sorted(primary):
        raise ValueError("歌词主时间戳必须按顺序排列。")
    return text + "\n"


def stamp_ms(match: re.Match) -> int:
    return int(match[1]) * 60000 + int(match[2]) * 1000 + int((match[3] or "0").ljust(3, "0"))


def shift_lrc(text: str, seconds: float) -> str:
    offset = round(seconds * 1000)
    def shifted(match):
        value = stamp_ms(match) + offset
        if value < 0:
            raise ValueError("调整后存在负时间，请缩小偏移。")
        minutes, remain = divmod(value, 60000)
        return f"[{minutes:02d}:{remain / 1000:06.3f}]"
    return validate_lrc(STAMP.sub(shifted, validate_lrc(text)))


@dataclass
class Job:
    id: str
    source: str
    stem: str
    directory: str
    audio: str = ""
    original_lyric: str = ""
    target_lyric: str = ""
    audio_status: str = PENDING
    lyric_status: str = PENDING
    ai_status: str = PENDING
    language: str = "zh"
    allow_repetition: bool = False
    allow_time_changes: bool = False
    message: str = ""
    stages: list[str] = field(default_factory=list)
    completed_stages: int = 0
    task_state: str = "draft"
    current_stage: str = ""
    existing_song: bool = False
    in_processing: bool = False
    process_convert: bool = True
    process_recognize: bool = False
    process_ai: bool = False

    def path(self, kind: str) -> Path:
        names = {"audio": self.stem + ".mp3", "draft": self.stem + ".draft.lrc",
                 "candidate": self.stem + ".candidate.lrc", "reference": "reference.txt",
                 "ai_input": "ai_input.lrc", "log": "task_report.txt"}
        return Path(self.directory) / names[kind]


def load_jobs(work: Path) -> list[Job]:
    path = work / "jobs.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    jobs = []
    for row in data:
        for name in ("source", "directory", "audio", "original_lyric"):
            if row.get(name):
                row[name] = str((work.parent / row[name]).resolve())
        jobs.append(Job(**row))
    for job in jobs:
        if job.existing_song:
            job.process_convert = False
        if not Path(job.directory).resolve().is_relative_to((work / "jobs").resolve()):
            raise ValueError("任务记录指向工作目录外。")
        if job.task_state in {"queued", "running", "cancelling"}:
            job.task_state = "cancelled"
            job.message = "上次处理已中断。"
        for name in ("audio_status", "lyric_status", "ai_status"):
            if getattr(job, name) in {"运行中", "排队中"}:
                setattr(job, name, "已中断")
                job.task_state = "cancelled"
                job.message = "上次处理已中断。"
    return jobs


def save_jobs(work: Path, jobs: list[Job]) -> None:
    rows = []
    root = work.parent.resolve()
    for job in jobs:
        row = asdict(job)
        for name in ("source", "directory", "audio", "original_lyric"):
            if row[name]:
                # Creation/loading already resolve paths. Saving must not reopen every media path.
                path = Path(os.path.abspath(row[name]))
                try:
                    row[name] = path.relative_to(root).as_posix()
                except ValueError:
                    pass
        rows.append(row)
    atomic_text(work / "jobs.json", json.dumps(rows, ensure_ascii=False, indent=2))


def create_job(settings: Settings, source: Path, stem: str, song: Song | None = None) -> Job:
    settings.validate()
    source = source.resolve()
    if not source.is_file() or source.suffix.casefold() not in prepare_music.MEDIA_EXTENSIONS:
        raise ValueError(f"不支持或不存在的媒体：{source}")
    work = Path(settings.work).resolve()
    if source.is_relative_to(work):
        raise ValueError("不能将工作目录的派生文件再次作为原始素材导入。")
    filename(stem + ".mp3", ".mp3")
    job_id = uuid.uuid4().hex
    directory = work / "jobs" / job_id
    directory.mkdir(parents=True)
    job = Job(job_id, str(source), stem, str(directory))
    job.existing_song = song is not None
    job.process_convert = song is None
    job.in_processing = song is None
    if song:
        job.audio, job.audio_status = str(source), "已有音频"
        job.original_lyric = str(song.lyric) if song.lyric else ""
        job.target_lyric = song.lyric.name if song.lyric else stem + ".lrc"
    atomic_text(directory / "job.json", json.dumps(asdict(job), ensure_ascii=False, indent=2))
    return job


def import_jobs(settings: Settings, sources: list[Path], existing: list[Job]) -> list[Job]:
    settings.validate()
    used = {p.stem.casefold() for p in (Path(settings.library) / "music").glob("*.mp3")}
    used.update(job.stem.casefold() for job in existing)
    created = []
    for source in sources:
        base = prepare_music.sanitize_stem(source.stem, len(created) + 1)
        stem, number = base, 2
        while stem.casefold() in used:
            stem, number = f"{base} ({number})", number + 1
        used.add(stem.casefold())
        created.append(create_job(settings, source, stem))
    return created


def recoverable_copy(source: Path, target: Path, work: Path, overwrite: bool = False) -> Path | None:
    if source.resolve() == target.resolve():
        return None
    if not source.is_file():
        raise ValueError(f"没有可用的生成结果：{source}")
    backup = None
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"目标已存在：{target.name}")
        backup = work / "backups" / uuid.uuid4().hex / target.name
        backup.parent.mkdir(parents=True)
        shutil.copy2(target, backup)
        atomic_text(backup.parent / "restore.json", json.dumps({"target": str(target.resolve()), "backup": str(backup)}, ensure_ascii=False))
    descriptor, name = tempfile.mkstemp(prefix=".workshop-", suffix=".tmp", dir=target.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return backup


def save_library_text(settings: Settings, folder: str, name: str, text: str) -> Path:
    settings.validate()
    if folder not in {"lyrics", "playlists"}:
        raise ValueError("只能写入歌词或歌单目录。")
    filename(name, ".lrc" if folder == "lyrics" else ".txt")
    if folder == "lyrics":
        text = validate_lrc(text)
    else:
        _, issues = parse_playlist(text)
        if issues:
            raise ValueError("\n".join(issues))
    work = Path(settings.work)
    temporary = work / "writes" / (uuid.uuid4().hex + Path(name).suffix)
    atomic_text(temporary, text)
    target = library_path(Path(settings.library), folder, name)
    try:
        recoverable_copy(temporary, target, work, overwrite=True)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def save_lyric_document(settings: Settings, name: str, text: str, expected: bytes | None) -> Path:
    """Save the editor's text verbatim, with a backup and a check against external changes."""
    settings.validate()
    filename(name, ".lrc")
    target = library_path(Path(settings.library), "lyrics", name)
    current = target.read_bytes() if target.exists() else None
    if current != expected:
        raise ValueError("原歌词已被其他操作修改，请重新打开后再编辑。")
    work = Path(settings.work)
    temporary = work / "writes" / (uuid.uuid4().hex + ".lrc")
    atomic_text(temporary, text)
    try:
        # Check again after preparing the output, before backing up and replacing the document.
        if (target.read_bytes() if target.exists() else None) != expected:
            raise ValueError("原歌词已被其他操作修改，请重新打开后再编辑。")
        recoverable_copy(temporary, target, work, overwrite=True)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def export_job(settings: Settings, job: Job, playlist: str = "", overwrite: bool = False) -> list[Path]:
    settings.validate()
    root, work = Path(settings.library), Path(settings.work)
    if not job.audio or not Path(job.audio).is_file():
        raise ValueError("这首歌还没有可用音频。")
    filename(job.stem + ".mp3", ".mp3")
    if playlist:
        filename(playlist, ".txt")
    audio_target = library_path(root, "music", job.stem + ".mp3")
    if audio_target.resolve() == Path(job.source).resolve() and Path(job.audio).resolve() != audio_target.resolve():
        raise ValueError("派生音频会覆盖源素材，请重新导入以分配独立文件名；源素材保持不变。")
    lyric_source = job.path("candidate") if job.path("candidate").is_file() else job.path("draft")
    lyric_name = job.target_lyric or job.stem + ".lrc"
    lyric_target = library_path(root, "lyrics", filename(lyric_name, ".lrc"))
    if lyric_source.is_file():
        validate_lrc(read_text(lyric_source))
    # Preflight all collisions before changing any data file.
    for source, target in [(Path(job.audio), audio_target)] + ([(lyric_source, lyric_target)] if lyric_source.is_file() else []):
        if source.resolve() != target.resolve() and target.exists() and not overwrite:
            raise FileExistsError(f"目标已存在：{target.name}")
    playlist_text = None
    if playlist:
        playlist_path = library_path(root, "playlists", playlist)
        playlist_text = read_text(playlist_path) if playlist_path.exists() else ""
        rows, issues = parse_playlist(playlist_text)
        if issues:
            raise ValueError("请先修正目标歌单：\n" + "\n".join(issues))
        mapped = lyric_name if lyric_source.is_file() or lyric_target.is_file() else "-"
        previous = [lyric for audio, lyric in rows if audio.casefold() == audio_target.name.casefold()]
        if previous and any(name.casefold() != mapped.casefold() for name in previous):
            raise ValueError("该歌单已有不同歌词映射，请在歌单管理中修改。")
        if not previous:
            playlist_text = playlist_text.rstrip() + ("\n" if playlist_text.strip() else "") + f"{audio_target.name}|{mapped}\n"
    recoverable_copy(Path(job.audio), audio_target, work, overwrite)
    outputs = [audio_target]
    if lyric_source.is_file():
        recoverable_copy(lyric_source, lyric_target, work, overwrite)
        outputs.append(lyric_target)
    if playlist and playlist_text is not None:
        outputs.append(save_library_text(settings, "playlists", playlist, playlist_text))
    atomic_text(Path(job.directory) / "export_report.txt", "\n".join(map(str, outputs)) + "\n")
    return outputs
