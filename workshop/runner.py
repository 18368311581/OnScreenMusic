"""Serial tasks with per-task cancellation and staged result publication."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict
from pathlib import Path

from .core import Job, Settings, atomic_text, read_text, validate_lrc, library_path, filename, recoverable_copy
from .runtime import tool_command

FIELDS = {"convert": "audio_status", "recognize": "lyric_status", "ai": "ai_status"}
NAMES = {"convert": "音频转换", "recognize": "本地识别", "ai": "AI 校对"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Cancelled(Exception):
    pass


class Runner:
    def __init__(self, base: Path, events: queue.Queue):
        self.base, self.events = base, events
        self.tasks = queue.Queue()
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.cancellations = {}
        self.registered = {}
        self.process = None
        self.active_job = None
        self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @property
    def busy(self):
        return bool(self.tasks.unfinished_tasks)

    def enqueue(self, job: Job, stages: list[str]):
        if not stages:
            return
        if job.existing_song and "convert" in stages:
            raise ValueError("现有歌曲不进行音频转换。")
        with self.lock:
            if self.closed:
                raise ValueError("任务队列已经关闭。")
            if job.task_state in {"queued", "running", "cancelling"}:
                raise ValueError("这首歌已有进行中的任务。")
            if not self.busy:
                self.cancelled.clear()
            token = threading.Event()
            self.cancellations[job.id] = token
            self.registered[job.id] = job
            job.stages = list(stages)
            job.completed_stages = 0
            job.current_stage = ""
            job.task_state = "queued"
            job.message = "等待处理"
            for stage in stages:
                setattr(job, FIELDS[stage], "排队中")
            self.tasks.put((job, list(stages), token))
        self.events.put(("changed", job.id))

    @staticmethod
    def terminate(process):
        def stop_process():
            if process.poll() is not None:
                return
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        creationflags=NO_WINDOW, capture_output=True, timeout=15)
                else:
                    process.terminate()
            except (OSError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.kill()
        threading.Thread(target=stop_process, daemon=True).start()

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            token = self.cancellations.get(job_id)
            if token is None:
                return False
            token.set()
            job = self.registered[job_id]
            is_active = self.active_job is job
            process = self.process if is_active else None
            if is_active:
                job.task_state = "cancelling"
                job.message = "正在终止…"
            else:
                job.task_state = "cancelled"
                job.message = "已终止，未采用或导出结果"
                for stage in job.stages:
                    setattr(job, FIELDS[stage], "已取消")
        if process and process.poll() is None:
            self.terminate(process)
        self.events.put(("changed", job_id))
        return True

    def stop(self):
        self.cancelled.set()
        with self.lock:
            ids = list(self.cancellations)
        for job_id in ids:
            self.cancel(job_id)

    def close(self):
        self.stop()
        with self.lock:
            if not self.closed:
                self.closed = True
                self.tasks.put(None)

    def check_cancelled(self, token):
        if token.is_set() or self.cancelled.is_set():
            raise Cancelled()

    def _stage(self, job, staged, stage, token, key):
        self.check_cancelled(token)
        staged_path = Path(staged.directory)
        job_path = staged_path / "job.json"
        atomic_text(job_path, json.dumps(asdict(staged), ensure_ascii=False))
        result_path = staged_path / (stage + "_result.json")
        result_path.unlink(missing_ok=True)
        command = tool_command("workshop.worker", "--base", self.base, "--job", job_path, "--stage", stage)
        process = None
        try:
            with self.lock:
                self.check_cancelled(token)
                self.process = subprocess.Popen(command, cwd=self.base, creationflags=NO_WINDOW,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                process = self.process
            with job.path("log").open("a", encoding="utf-8") as log:
                log.write(f"\n=== {NAMES[stage]} ===\n")
                for line in process.stdout:
                    line = line.replace(key, "[密钥已隐藏]") if key else line
                    log.write(line)
                    log.flush()
                    self.events.put(("log", (job.id, line.rstrip())))
            return_code = process.wait()
            self.check_cancelled(token)
            result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
            if return_code or not result.get("ok"):
                raise RuntimeError(result.get("detail", f"工具退出码：{return_code}"))
            if "audio" in result:
                staged.audio = result["audio"]
            if "lyric_status" in result:
                staged.lyric_status = result["lyric_status"]
            staged.message = result.get("detail", "处理完成")
        finally:
            if process is not None:
                if process.poll() is None:
                    self.terminate(process)
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if process.stdout is not None:
                    process.stdout.close()
            with self.lock:
                self.process = None

    def _publish(self, job, staged, stages, token):
        run = Path(staged.directory)
        lyric = None
        if "ai" in stages or "recognize" in stages:
            lyric = staged.path("candidate" if "ai" in stages else "draft")
            # Only the final step's fresh output can replace the library document.
            validate_lrc(read_text(lyric))
        settings = Settings.load(self.base)
        outputs = []
        for kind in ("audio", "draft", "candidate"):
            source = staged.path(kind)
            if source.is_file():
                outputs.append((source, job.path(kind)))
        outputs.extend((p, Path(job.directory) / p.name) for p in run.glob("previous-*.candidate.lrc"))
        # Publishing involves only atomic renames. Cancellation and the commit share one gate.
        with self.lock:
            self.check_cancelled(token)
            for source, target in outputs:
                os.replace(source, target)
            if "recognize" in stages and "ai" not in stages and not staged.path("candidate").exists():
                job.path("candidate").unlink(missing_ok=True)
            if staged.audio:
                audio = Path(staged.audio)
                job.audio = str(Path(job.directory) / audio.name) if audio.parent == run else staged.audio
            if lyric is not None:
                name = filename(job.target_lyric or job.stem + ".lrc", ".lrc")
                target = library_path(Path(settings.library), "lyrics", name)
                recoverable_copy(job.path("candidate" if "ai" in stages else "draft"), target, Path(settings.work), overwrite=True)
            for stage in stages:
                setattr(job, FIELDS[stage], "成功")
            if staged.lyric_status not in {"未处理", "排队中"}:
                job.lyric_status = staged.lyric_status
            if "recognize" in stages and "ai" not in stages:
                job.ai_status = "草稿已更新，待校对"
            job.completed_stages = len(stages)
            job.task_state = "succeeded"
            job.current_stage = ""
            job.message = "处理完成，歌词已更新" if lyric is not None else "处理完成，音频已保存到工作目录"
            self.cancellations.pop(job.id, None)

    def _run(self):
        while True:
            task = self.tasks.get()
            if task is None:
                self.tasks.task_done()
                return
            job, stages, token = task
            run = None
            try:
                self.check_cancelled(token)
                with self.lock:
                    self.active_job = job
                    job.task_state = "running"
                run = Path(job.directory) / "runs" / uuid.uuid4().hex
                run.mkdir(parents=True)
                staged = Job(**asdict(job))
                staged.directory = str(run)
                for kind in ("draft", "candidate", "reference", "ai_input"):
                    if job.path(kind).is_file():
                        shutil.copy2(job.path(kind), staged.path(kind))
                key = Settings.load(self.base).api_key
                for index, stage in enumerate(stages):
                    self.check_cancelled(token)
                    if stage == "ai" and "recognize" in stages[:index]:
                        # Snapshot this run's fresh draft, rather than an earlier AI input.
                        atomic_text(staged.path("ai_input"), validate_lrc(read_text(staged.path("draft"))))
                    job.current_stage = stage
                    setattr(job, FIELDS[stage], "运行中")
                    self.events.put(("changed", job.id))
                    self._stage(job, staged, stage, token, key)
                    setattr(staged, FIELDS[stage], "成功")
                    job.completed_stages = index + 1
                    self.events.put(("changed", job.id))
                self._publish(job, staged, stages, token)
            except Cancelled:
                job.task_state = "cancelled"
                job.message = "已终止，未采用或导出结果"
                for stage in stages:
                    setattr(job, FIELDS[stage], "已取消")
            except Exception as exc:
                if token.is_set() or self.cancelled.is_set():
                    job.task_state = "cancelled"
                    job.message = "已终止，未采用或导出结果"
                    for stage in stages:
                        setattr(job, FIELDS[stage], "已取消")
                else:
                    job.task_state = "failed"
                    message = str(exc)
                    try:
                        key = Settings.load(self.base).api_key
                        message = message.replace(key, "[密钥已隐藏]") if key else message
                    except (OSError, ValueError):
                        message = "本机配置或任务记录无法读取。"
                    job.message = message
                    setattr(job, FIELDS[job.current_stage or stages[0]], "失败")
                    for stage in stages:
                        if getattr(job, FIELDS[stage]) == "排队中":
                            setattr(job, FIELDS[stage], "未执行")
                        elif getattr(job, FIELDS[stage]) == "运行中":
                            setattr(job, FIELDS[stage], "未提交")
            finally:
                if run is not None:
                    shutil.rmtree(run, ignore_errors=True)
                with self.lock:
                    self.active_job = None
                    if self.cancellations.get(job.id) is token or job.id not in self.cancellations:
                        self.cancellations.pop(job.id, None)
                        self.registered.pop(job.id, None)
                self.tasks.task_done()
                self.events.put(("finished", job.id))
