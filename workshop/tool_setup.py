"""User-launched console downloads; no packages or system PATH are changed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time
import urllib.request
import zipfile

from .core import Settings, filename


TOOLS = {
    "ffmpeg": ("FFmpeg", "tools/ffmpeg/bin/ffmpeg.exe"),
    "whisper": ("本地识别程序", "tools/whisper/Release/whisper-cli.exe"),
    "model": ("本地识别模型 · large-v3（约 3.1 GB）", "tools/whisper/models/ggml-large-v3.bin"),
}
HEADERS = {"User-Agent": "MusicWorkshop-tool-setup", "Accept": "application/json"}


def find_tool(root: Path, kind: str, configured="") -> Path | None:
    candidates = [root / configured] if configured else []
    candidates.append(root / TOOLS[kind][1])
    if kind != "model":
        found = shutil.which("ffmpeg.exe" if kind == "ffmpeg" else "whisper-cli.exe")
        if found:
            candidates.append(Path(found))
    search = root / "tools"
    if search.is_dir():
        candidates.extend(search.rglob(Path(TOOLS[kind][1]).name))
    if kind == "ffmpeg":
        from tools.generate_lrc import FALLBACK_FFMPEG
        candidates.append(FALLBACK_FFMPEG)
    return next((path.resolve() for path in candidates if path.is_file() and path.stat().st_size > 0), None)


def _json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as response:
        return json.loads(response.read(8 * 1024 * 1024))


def download_source(kind):
    if kind == "whisper":
        releases = _json("https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=30")
        for release in releases:
            if release.get("draft"):
                continue
            for asset in release.get("assets", []):
                name = asset["name"].lower()
                if (name.startswith("whisper") and name.endswith(".zip") and ("x64" in name or "amd64" in name)
                        and not any(part in name for part in ("cuda", "cublas", "vulkan", "arm", "sdl"))):
                    digest = asset.get("digest") or ""
                    return asset["browser_download_url"], digest.removeprefix("sha256:") or None
        raise ValueError("官网暂未找到 Windows x64 CPU 安装包，请稍后再试。")
    if kind == "model":
        data = _json("https://huggingface.co/api/models/ggerganov/whisper.cpp?blobs=true")
        row = next(row for row in data["siblings"] if row["rfilename"] == "ggml-large-v3.bin")
        digest = row.get("lfs", {}).get("sha256") or row.get("lfs", {}).get("oid")
        if not digest or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("无法读取官方模型校验值，未开始下载。")
        return "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin", digest
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    with urllib.request.urlopen(url + ".sha256", timeout=30) as response:
        text = response.read(4096).decode("ascii")
    digest = re.search(r"\b[0-9a-fA-F]{64}\b", text)
    if not digest:
        raise ValueError("无法读取 FFmpeg 校验值，未开始下载。")
    return url, digest.group()


def download_file(url, target: Path, digest=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": HEADERS["User-Agent"]}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    last_print = time.monotonic()
    with urllib.request.urlopen(request, timeout=45) as response:
        resumed = offset > 0 and response.status == 206
        if resumed and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise ValueError("下载服务器返回了错误的续传位置。")
        count = offset if resumed else 0
        with partial.open("ab" if resumed else "wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                count += len(chunk)
                if count > 5 * 1024 ** 3:
                    raise ValueError("下载文件超过预期大小，已停止。")
                if time.monotonic() - last_print > 3:
                    print(f"已下载 {count / 1024 ** 2:.0f} MB", flush=True)
                    last_print = time.monotonic()
    if digest:
        print("正在校验文件…", flush=True)
        with partial.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual.lower() != digest.lower():
            partial.unlink()
            raise ValueError("下载文件校验失败，未安装；请重新下载。")
    os.replace(partial, target)


def install_archive(archive: Path, target: Path):
    """Stage only the executable's runtime directory, rejecting paths and links outside it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        names = [item for item in bundle.infolist() if PurePosixPath(item.filename.replace("\\", "/")).name == target.name]
        if len(names) != 1:
            raise ValueError("安装包未包含唯一的目标程序，未安装。")
        prefix = PurePosixPath(names[0].filename.replace("\\", "/")).parent
        with tempfile.TemporaryDirectory(prefix="tool-stage-", dir=archive.parent) as temporary:
            stage = Path(temporary)
            total = 0
            for member in bundle.infolist():
                path = PurePosixPath(member.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("安装包包含不安全路径，未安装。")
                if not path.is_relative_to(prefix) or member.is_dir():
                    continue
                relative = path.relative_to(prefix)
                for part in relative.parts:
                    filename(part)
                total += member.file_size
                if total > 2 * 1024 ** 3:
                    raise ValueError("安装包解压后超过预期大小。")
                destination = stage / Path(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
            if not (stage / target.name).is_file() or (stage / target.name).stat().st_size == 0:
                raise ValueError("安装程序文件为空，未安装。")
            for source in sorted((path for path in stage.rglob("*") if path.is_file()), key=lambda path: path.name == target.name):
                if source.is_file():
                    destination = target.parent / source.relative_to(stage)
                    if not destination.resolve().is_relative_to(target.parent.resolve()):
                        raise ValueError("安装目标指向工具目录外，未写入。")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists():
                        backup = archive.parent / ("backup-" + str(time.time_ns())) / source.relative_to(stage)
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(destination, backup)
                    os.replace(source, destination)


def setup_tool(root: Path, kind):
    settings = Settings.load(root)
    print(TOOLS[kind][0], flush=True)
    existing = find_tool(root, kind, getattr(settings, kind))
    if existing:
        print(f"已有文件，直接使用：{existing}", flush=True)
        target = existing
    else:
        print("从官方发布来源下载，Ctrl+C 可中止；不会修改系统 PATH。", flush=True)
        url, digest = download_source(kind)
        print("下载来源：" + url, flush=True)
        target = root / TOOLS[kind][1]
        if kind == "model":
            download_file(url, target, digest)
        else:
            archive = Path(settings.work) / "downloads" / f"{kind}.zip"
            download_file(url, archive, digest)
            install_archive(archive, target)
    setattr(settings, kind, str(target))
    settings.save(root, fields={kind})
    print(f"完成，已单独保存该工具的配置：{target}", flush=True)
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=TOOLS)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--no-pause", action="store_true")
    args = parser.parse_args()
    result = 0
    try:
        setup_tool(args.root.resolve(), args.kind)
    except (Exception, KeyboardInterrupt) as error:
        print("下载未完成：" + (str(error) or "已中止"), flush=True)
        result = 1
    if not args.no_pause:
        try:
            input("按回车关闭此窗口…")
        except (EOFError, KeyboardInterrupt):
            pass
    return result


if __name__ == "__main__":
    raise SystemExit(main())
