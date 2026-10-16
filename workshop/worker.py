"""One isolated processing step; cancellation terminates this process tree."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from tools import ai_lyrics, generate_lrc, prepare_music
from .core import Job, Settings, STAMP, atomic_text, read_text, validate_lrc


def process(settings: Settings, job: Job, stage: str) -> dict:
    settings.validate()
    result = {}
    if stage == "convert":
        source = Path(job.source)
        prepare_music.resolve_source_and_output(str(source), job.directory)
        ffmpeg = prepare_music.locate_ffmpeg(settings.ffmpeg or None)
        prepare_music.validate_ffmpeg(ffmpeg)
        print("正在分析响度并生成标准 MP3……", flush=True)
        prepare_music.normalize_audio(ffmpeg, source, job.path("audio"))
        result["audio"] = str(job.path("audio"))
        # Copy the same-stem lyric into staging, never into the live library.
        lyric = prepare_music.find_matching_lrc(source)
        if lyric and not job.path("draft").exists():
            try:
                atomic_text(job.path("draft"), validate_lrc(read_text(lyric)))
                result["lyric_status"] = "已有歌词副本"
            except (OSError, ValueError) as exc:
                print(f"歌词复制警告：{exc}", flush=True)
    elif stage == "recognize":
        source = Path(job.audio or job.source)
        if source.suffix.casefold() not in generate_lrc.AUDIO_EXTENSIONS:
            raise ValueError("请先转换视频或其他素材为可用音频。")
        ffmpeg = generate_lrc.locate_ffmpeg(settings.ffmpeg or None)
        whisper = generate_lrc.locate_whisper(settings.whisper or None)
        model = generate_lrc.locate_model(settings.model or None)
        generate_lrc.validate_tools(ffmpeg, whisper)
        generate_lrc.validate_model(model)
        track = generate_lrc.Track(source, Path(source.name), Path(job.path("draft").name))
        entry = generate_lrc.process_track(track, Path(job.directory), ffmpeg, whisper, model,
                                          job.language, None, False, True, job.allow_repetition)
        if job.path("candidate").is_file():
            archive = Path(job.directory) / ("previous-" + uuid.uuid4().hex + ".candidate.lrc")
            shutil.copy2(job.path("candidate"), archive)
            job.path("candidate").unlink()
        result["detail"] = entry.detail
    elif stage == "ai":
        if not settings.api_key:
            raise ValueError("请先在设置中填写 AI 接口密钥。")
        draft = validate_lrc(read_text(job.path("ai_input")))
        if draft.startswith("#INSTRUMENTAL"):
            raise ValueError("纯音乐标记不需要 AI 校对。")
        reference = read_text(job.path("reference")).strip()
        if not reference:
            raise ValueError("请先粘贴参考歌词。")
        if not job.allow_time_changes:
            reference += "\n\n校对限制：只修改每行歌词文字，保留所有时间标签、标签顺序与行数；不得估计或新增时间。"
        repaired = ai_lyrics.request_ai_repair(job.stem, draft, reference, settings.api_key)
        candidate = validate_lrc(ai_lyrics.normalize_ai_lrc(repaired))
        if not job.allow_time_changes and STAMP.findall(candidate) != STAMP.findall(draft):
            raise ValueError("AI 更改了时间标签，已拒绝候选；原歌词保持不变。可改用允许估计补时模式。")
        if job.path("candidate").is_file():
            shutil.copy2(job.path("candidate"), Path(job.directory) / ("previous-" + uuid.uuid4().hex + ".candidate.lrc"))
        atomic_text(job.path("candidate"), candidate)
        result["detail"] = "校对结果已保存；歌词时间需试听确认" if job.allow_time_changes else "文字校对完成，时间标签已保留"
    else:
        raise ValueError("未知处理步骤。")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--stage", choices=("convert", "recognize", "ai"), required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    job = Job(**json.loads(Path(args.job).read_text(encoding="utf-8")))
    settings = Settings.load(Path(args.base))
    result_path = Path(job.directory) / (args.stage + "_result.json")
    try:
        result = process(settings, job, args.stage)
        result["ok"] = True
        atomic_text(result_path, json.dumps(result, ensure_ascii=False))
        print(result.get("detail", "处理完成，结果已保存到工作目录。"), flush=True)
        return 0
    except Exception as exc:
        message = str(exc)
        if settings.api_key:
            message = message.replace(settings.api_key, "[密钥已隐藏]")
        atomic_text(result_path, json.dumps({"ok": False, "detail": message}, ensure_ascii=False))
        print("处理失败：" + message, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
