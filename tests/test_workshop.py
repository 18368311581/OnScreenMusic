from __future__ import annotations

import hashlib
import json
import queue
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from workshop import core, worker
from workshop.runner import Runner
from workshop.playlists import inspect_playlist, read_entries, write_entries
from tools import generate_lrc

BASE = Path(__file__).resolve().parents[1]


class WorkshopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workshop-test-")
        self.base = Path(self.temporary.name)
        self.root = self.base
        for name in ("music", "lyrics", "playlists"):
            (self.root / name).mkdir(parents=True)
        self.settings = core.Settings(str(self.root), str(self.base / "MusicWorkshopWork"))
        self.source = self.base / "原始歌曲.wav"
        self.source.write_bytes(b"original-audio")

    def tearDown(self):
        self.temporary.cleanup()

    def job(self, source=None, stem="歌曲"):
        return core.create_job(self.settings, source or self.source, stem)

    def prepared_job(self):
        job = self.job()
        job.path("audio").write_bytes(b"derived-mp3")
        job.audio = str(job.path("audio"))
        return job

    def test_private_settings_round_trip_and_repr(self):
        self.settings.api_key = "test-private-key"
        self.settings.save(self.base)
        loaded = core.Settings.load(self.base)
        self.assertEqual(loaded.api_key, self.settings.api_key)
        self.assertNotIn(self.settings.api_key, repr(loaded))
        self.assertEqual(loaded.library, self.settings.library)

    def test_shared_ini_keeps_player_and_unknown_fields(self):
        from workshop.shared_settings import read_ini, qt_decode
        path = self.base / "OnScreenMusic.ini"
        path.write_text('[Audio]\nVolume=17\n[Playback]\nSingleRepeat=true\nPositionMs=43210\n'
                        '[Window]\nPosition=@Point(420 510)\n[Library]\nPlaylistFile="中文,歌单.txt"\n'
                        '[Other]\nOpaque=@ByteArray(a,b)\n', encoding="utf-8")
        self.settings.api_key = 'mock,@key,\\quotes"百分号%'
        self.settings.save(self.base)
        parsed = read_ini(path)
        self.assertEqual(parsed.get("Audio", "Volume"), "17")
        self.assertEqual(parsed.get("Playback", "PositionMs"), "43210")
        self.assertEqual(parsed.get("Window", "Position"), "@Point(420 510)")
        self.assertEqual(parsed.get("Library", "PlaylistFile"), '"中文,歌单.txt"')
        self.assertEqual(parsed.get("Other", "Opaque"), "@ByteArray(a,b)")
        self.assertEqual(qt_decode(parsed.get("Workshop", "ApiKey")), self.settings.api_key)
        self.assertFalse(parsed.has_option("Workshop", "library"))
        self.assertFalse((self.base / "MusicWorkshop.local.ini").exists())

    def test_library_root_is_fixed_and_tool_paths_can_be_saved_individually(self):
        from workshop.shared_settings import qt_decode, read_ini
        (self.base / "MusicWorkshop.local.ini").write_text('[Workshop]\napi_key=ignored-old-config\n', encoding="utf-8")
        (self.base / "OnScreenMusic.ini").write_text('[Library]\nRoot=C:/unavailable\n[Workshop]\nWork=C:/old-work\nWhisper=C:/old-tool.exe\nModel=C:/old-model.bin\n', encoding="utf-8")
        loaded = core.Settings.load(self.base)
        self.assertEqual(loaded.library, str(self.base))
        self.assertEqual(loaded.work, str(self.base / "MusicWorkshopWork"))
        self.assertEqual(loaded.whisper, str(Path("C:/old-tool.exe")))
        self.assertEqual(loaded.model, str(Path("C:/old-model.bin")))
        self.assertFalse(loaded.api_key)
        loaded.save(self.base)
        parser = read_ini(self.base / "OnScreenMusic.ini")
        self.assertFalse(parser.has_option("Library", "Root"))
        self.assertFalse(parser.has_option("Workshop", "Work"))
        self.assertEqual(qt_decode(parser.get("Workshop", "Model")), "C:/old-model.bin")

    def test_config_and_internal_job_paths_follow_relocated_folder(self):
        internal = self.root / "music" / "内部.mp3"
        internal.write_bytes(b"mp3")
        job = self.job(internal, "内部")
        job.audio = str(internal)
        self.settings.save(self.base)
        core.save_jobs(Path(self.settings.work), [job])
        manifest = (Path(self.settings.work) / "jobs.json").read_text(encoding="utf-8")
        self.assertNotIn(self.base.as_posix(), manifest)
        destination = self.base.parent / (self.base.name + "-moved")
        try:
            shutil.copytree(self.base, destination)
            loaded = core.Settings.load(destination)
            self.assertEqual(loaded.library, str(destination))
            restored = core.load_jobs(Path(loaded.work))[0]
            self.assertEqual(restored.source, str(destination / "music/内部.mp3"))
            self.assertTrue(Path(restored.directory).is_dir())
        finally:
            shutil.rmtree(destination, ignore_errors=True)

    def test_development_entry_uses_same_config_as_deployed_player(self):
        from workshop.shared_settings import settings_file
        deployed = self.base / "release-v1.0"
        deployed.mkdir()
        (deployed / "OnScreenMusic.exe").write_bytes(b"fixture")
        self.assertEqual(settings_file(self.base), settings_file(deployed))

    def test_qt_string_encoding_handles_punctuation_and_literals(self):
        from workshop.shared_settings import qt_decode, qt_encode
        for value in ('C:/含空格 路径/模型.bin', '@Variant(test)', 'a,b;key%"\\path', "line\nnext\tend"):
            self.assertEqual(qt_decode(qt_encode(value)), value)

    def test_work_directory_must_not_include_library_data(self):
        self.settings.work = str(self.root)
        with self.assertRaises(ValueError):
            self.settings.validate()

    def test_filename_rejects_paths_and_reserved_names(self):
        for name in ("../song.mp3", "C:\\song.mp3", "a|b.mp3", "CON.mp3", "song.mp3 ", "song.mp3\n"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                core.filename(name, ".mp3")

    def test_import_allocates_distinct_flat_names(self):
        other = self.base / "other"
        other.mkdir()
        second = other / self.source.name
        second.write_bytes(b"different-original")
        (self.root / "music" / "原始歌曲.mp3").write_bytes(b"existing")
        jobs = core.import_jobs(self.settings, [self.source, second], [])
        self.assertEqual([j.stem for j in jobs], ["原始歌曲 (2)", "原始歌曲 (3)"])
        self.assertEqual(self.source.read_bytes(), b"original-audio")

    def test_playlist_preserves_weight_and_detects_conflicting_lyrics(self):
        rows, issues = core.parse_playlist("# 注释\n歌曲.mp3|歌曲.lrc\n歌曲.mp3|歌曲.lrc\n")
        self.assertEqual(len(rows), 2)
        self.assertFalse(issues)
        _, issues = core.parse_playlist("歌曲.mp3|歌曲.lrc\n歌曲.mp3|-\n")
        self.assertIn("不同歌词", issues[0])

    def test_missing_music_and_lyrics_are_reported(self):
        issues = core.check_playlist(self.root, "歌曲.mp3|歌曲.lrc\n")
        self.assertEqual(len(issues), 2)

    def test_library_uses_custom_lyric_mapping_and_top_level_only(self):
        (self.root / "music" / "歌曲.mp3").write_bytes(b"mp3")
        nested = self.root / "music" / "nested"
        nested.mkdir()
        (nested / "hidden.mp3").write_bytes(b"mp3")
        (self.root / "lyrics" / "自定义.lrc").write_text("[00:01]歌词", encoding="utf-8")
        (self.root / "playlists" / "歌单.txt").write_text("歌曲.mp3|自定义.lrc\n", encoding="utf-8")
        songs, issues = core.scan_library(self.root)
        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0].lyric.name, "自定义.lrc")
        self.assertFalse(issues)

    def test_lrc_multitag_and_fraction_validation(self):
        text = "[ti:歌曲]\n[00:01][00:08.120]歌词一\n[00:03.50]歌词二\n"
        self.assertEqual(core.validate_lrc(text), text)
        for bad in ("[00:99]bad", "[00:03]a\n[00:01]b", "no lyrics", "[00:01.1234]bad"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                core.validate_lrc(bad)

    def test_shift_all_tags_and_reject_negative_times(self):
        shifted = core.shift_lrc("[00:01][00:08.120]歌词\n", 0.5)
        self.assertEqual(shifted, "[00:01.500][00:08.620]歌词\n")
        with self.assertRaises(ValueError):
            core.shift_lrc("[00:01]歌词", -2)

    def test_pure_music_marker_is_explicit(self):
        self.assertEqual(core.validate_lrc("#INSTRUMENTAL\nignored"), "#INSTRUMENTAL\n")

    def test_save_preserves_original_in_recoverable_copy(self):
        target = self.root / "lyrics" / "歌曲.lrc"
        target.write_text("[00:01]原歌词\n", encoding="utf-8")
        core.save_library_text(self.settings, "lyrics", target.name, "[00:01]新歌词\n")
        backups = list((Path(self.settings.work) / "backups").glob("*/歌曲.lrc"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "[00:01]原歌词\n")
        metadata = json.loads((backups[0].parent / "restore.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["target"], str(target.resolve()))
        self.assertEqual(target.read_text(encoding="utf-8"), "[00:01]新歌词\n")

    def test_invalid_lyric_does_not_replace_existing_file(self):
        target = self.root / "lyrics" / "歌曲.lrc"
        target.write_bytes(b"original")
        with self.assertRaises(ValueError):
            core.save_library_text(self.settings, "lyrics", target.name, "invalid")
        self.assertEqual(target.read_bytes(), b"original")

    def test_export_preflights_all_collisions_before_copy(self):
        job = self.prepared_job()
        job.path("draft").write_text("[00:01]新歌词", encoding="utf-8")
        (self.root / "lyrics" / "歌曲.lrc").write_bytes(b"old")
        with self.assertRaises(FileExistsError):
            core.export_job(self.settings, job)
        self.assertFalse((self.root / "music" / "歌曲.mp3").exists())
        self.assertEqual((self.root / "lyrics" / "歌曲.lrc").read_bytes(), b"old")

    def test_export_without_lyrics_works_and_writes_dash_mapping(self):
        job = self.prepared_job()
        core.export_job(self.settings, job, "歌单.txt")
        self.assertEqual((self.root / "playlists" / "歌单.txt").read_text(encoding="utf-8"), "歌曲.mp3|-\n")
        self.assertEqual(self.source.read_bytes(), b"original-audio")

    def test_export_uses_candidate_and_preserves_playlist_weight(self):
        job = self.prepared_job()
        job.path("draft").write_text("[00:01]错字\n", encoding="utf-8")
        job.path("candidate").write_text("[00:01]正确\n", encoding="utf-8")
        playlist = self.root / "playlists" / "歌单.txt"
        playlist.write_text("# 原注释\n歌曲.mp3|歌曲.lrc\n歌曲.mp3|歌曲.lrc\n", encoding="utf-8")
        core.export_job(self.settings, job, playlist.name)
        self.assertEqual(len(core.parse_playlist(playlist.read_text(encoding="utf-8"))[0]), 2)
        self.assertEqual((self.root / "lyrics" / "歌曲.lrc").read_text(encoding="utf-8"), "[00:01]正确\n")

    def test_export_refuses_to_overwrite_source_audio(self):
        source = self.root / "music" / "歌曲.mp3"
        source.write_bytes(b"original-mp3")
        job = self.job(source)
        job.path("audio").write_bytes(b"derived")
        job.audio = str(job.path("audio"))
        with self.assertRaises(ValueError):
            core.export_job(self.settings, job, overwrite=True)
        self.assertEqual(source.read_bytes(), b"original-mp3")

    def test_invalid_destination_playlist_prevents_audio_write(self):
        job = self.prepared_job()
        (self.root / "playlists" / "bad.txt").write_text("bad", encoding="utf-8")
        with self.assertRaises(ValueError):
            core.export_job(self.settings, job, "bad.txt")
        self.assertFalse((self.root / "music" / "歌曲.mp3").exists())

    def test_ai_failure_and_time_change_preserve_existing_candidate(self):
        job = self.prepared_job()
        core.atomic_text(job.path("ai_input"), "[00:01.00]原词\n")
        core.atomic_text(job.path("reference"), "正确歌词")
        core.atomic_text(job.path("candidate"), "[00:01.00]之前候选\n")
        self.settings.api_key = "mock-key"
        with mock.patch.object(worker.ai_lyrics, "request_ai_repair", return_value="[00:02.00]正确歌词"):
            with self.assertRaises(ValueError):
                worker.process(self.settings, job, "ai")
        self.assertIn("之前候选", core.read_text(job.path("candidate")))
        with mock.patch.object(worker.ai_lyrics, "request_ai_repair", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                worker.process(self.settings, job, "ai")
        self.assertIn("之前候选", core.read_text(job.path("candidate")))

    def test_ai_success_preserves_previous_candidate_and_time_labels(self):
        job = self.prepared_job()
        core.atomic_text(job.path("ai_input"), "[00:01.00]原词\n")
        core.atomic_text(job.path("reference"), "正确歌词")
        core.atomic_text(job.path("candidate"), "[00:01.00]旧候选\n")
        self.settings.api_key = "mock-key"
        with mock.patch.object(worker.ai_lyrics, "request_ai_repair", return_value="[00:01.00]正确歌词"):
            worker.process(self.settings, job, "ai")
        self.assertEqual(core.read_text(job.path("candidate")), "[00:01.00]正确歌词\n")
        self.assertEqual(len(list(Path(job.directory).glob("previous-*.candidate.lrc"))), 1)

    def test_existing_song_cannot_be_enqueued_for_conversion(self):
        source = self.root / "music/existing.mp3"
        source.write_bytes(b"original-existing")
        song = core.Song(source.name, source, None, [])
        job = core.create_job(self.settings, source, source.stem, song)
        runner = Runner(self.base, queue.Queue())
        try:
            with self.assertRaisesRegex(ValueError, "现有歌曲"):
                runner.enqueue(job, ["convert"])
            self.assertFalse(runner.busy)
            self.assertEqual(source.read_bytes(), b"original-existing")
        finally:
            runner.close()
            runner.thread.join(3)

    def test_recognition_ai_pipeline_uses_fresh_draft_instead_of_old_input(self):
        job = self.prepared_job()
        target = self.root / 'lyrics' / (job.stem + '.lrc')
        target.write_bytes(b'[00:01]old-library-lyric\n')
        core.atomic_text(job.path("ai_input"), "[00:01.00]旧草稿\n")
        core.atomic_text(job.path("reference"), "正确参考歌词")
        self.settings.api_key = "mock-key"
        runner = Runner(self.base, queue.Queue())
        def fake_stage(original, staged, stage, token, key):
            if stage == "recognize":
                core.atomic_text(staged.path("draft"), "[00:05.00]新识别草稿\n")
            else:
                worker.process(self.settings, staged, "ai")
        try:
            with mock.patch.object(runner, "_stage", side_effect=fake_stage), \
                 mock.patch.object(worker.ai_lyrics, "request_ai_repair", return_value="[00:05.00]新校对歌词\n") as request:
                runner.enqueue(job, ["recognize", "ai"])
                deadline = time.monotonic() + 5
                while runner.busy and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(runner.busy)
                self.assertEqual(job.task_state, "succeeded")
                self.assertEqual(request.call_args.args[1], "[00:05.00]新识别草稿\n")
            self.assertEqual(core.read_text(job.path("candidate")), "[00:05.00]新校对歌词\n")
            self.assertEqual(core.read_text(target), "[00:05.00]新校对歌词\n")
            backups = list((Path(self.settings.work) / 'backups').glob('*/' + target.name))
            self.assertEqual(backups[0].read_bytes(), b'[00:01]old-library-lyric\n')
            self.assertEqual(self.source.read_bytes(), b"original-audio")
        finally:
            runner.close()
            runner.thread.join(3)

    def test_failed_ai_leaves_library_lyric_unchanged(self):
        job = self.prepared_job()
        target = self.root / 'lyrics' / (job.stem + '.lrc')
        target.write_bytes(b'[00:01]original\n')
        runner = Runner(self.base, queue.Queue())
        def stage(original, staged, kind, token, key):
            if kind == 'recognize':
                core.atomic_text(staged.path('draft'), '[00:02]new draft\n')
            else:
                raise RuntimeError('mock AI failure')
        try:
            with mock.patch.object(runner, '_stage', side_effect=stage):
                runner.enqueue(job, ['recognize', 'ai'])
                deadline = time.monotonic() + 5
                while runner.busy and time.monotonic() < deadline:
                    time.sleep(.02)
            self.assertEqual(job.task_state, 'failed')
            self.assertEqual(target.read_bytes(), b'[00:01]original\n')
        finally:
            runner.close()
            runner.thread.join(3)

    def test_recognition_alone_updates_lyric_and_creates_no_backup_for_new_file(self):
        job = self.prepared_job()
        core.atomic_text(job.path('candidate'), '[00:01]stale candidate\n')
        runner = Runner(self.base, queue.Queue())
        def stage(original, staged, kind, token, key):
            core.atomic_text(staged.path('draft'), '[00:03]new recognized lyric\n')
            staged.path('candidate').unlink(missing_ok=True)
        try:
            with mock.patch.object(runner, '_stage', side_effect=stage):
                runner.enqueue(job, ['recognize'])
                deadline = time.monotonic() + 5
                while runner.busy and time.monotonic() < deadline:
                    time.sleep(.02)
            self.assertEqual(job.task_state, 'succeeded')
            target = self.root / 'lyrics' / (job.stem + '.lrc')
            self.assertEqual(core.read_text(target), '[00:03]new recognized lyric\n')
            self.assertFalse(list((Path(self.settings.work) / 'backups').glob('*')))
        finally:
            runner.close()
            runner.thread.join(3)

    def test_restart_marks_active_jobs_as_interrupted(self):
        job = self.job()
        job.audio_status = "运行中"
        core.save_jobs(Path(self.settings.work), [job])
        loaded = core.load_jobs(Path(self.settings.work))
        self.assertEqual(loaded[0].audio_status, "已中断")
        self.assertEqual(loaded[0].task_state, "cancelled")

    def test_document_save_preserves_text_and_original_bytes_in_backup(self):
        target = self.root / "lyrics/自定义.lrc"
        original = b"\xef\xbb\xbf[00:01]original\r\n"
        target.write_bytes(original)
        text = "\n[00:01]手动编辑  \n\n"
        core.save_lyric_document(self.settings, target.name, text, original)
        self.assertEqual(target.read_bytes(), text.encode("utf-8"))
        backups = list(Path(self.settings.work).glob("backups/*/自定义.lrc"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_document_save_refuses_external_replacement_deletion_and_creation(self):
        target = self.root / "lyrics/自定义.lrc"
        target.write_bytes(b"external")
        with self.assertRaisesRegex(ValueError, "其他操作修改"):
            core.save_lyric_document(self.settings, target.name, "edited", b"original")
        target.unlink()
        with self.assertRaisesRegex(ValueError, "其他操作修改"):
            core.save_lyric_document(self.settings, target.name, "edited", b"original")
        target.write_bytes(b"newly-created")
        with self.assertRaisesRegex(ValueError, "其他操作修改"):
            core.save_lyric_document(self.settings, target.name, "edited", None)
        self.assertEqual(target.read_bytes(), b"newly-created")
        with self.assertRaises(ValueError):
            core.save_lyric_document(self.settings, "../outside.lrc", "edited", None)

    def test_per_song_processing_flags_survive_manifest_round_trip(self):
        job = self.job()
        job.process_convert = False
        job.process_recognize = True
        job.process_ai = True
        job.allow_repetition = True
        core.save_jobs(Path(self.settings.work), [job])
        loaded = core.load_jobs(Path(self.settings.work))[0]
        self.assertFalse(loaded.process_convert)
        self.assertTrue(loaded.process_recognize)
        self.assertTrue(loaded.process_ai)
        self.assertTrue(loaded.allow_repetition)

    def test_local_recognition_receives_per_song_repetition_override(self):
        job = self.prepared_job()
        job.allow_repetition = True
        with mock.patch.object(generate_lrc, "locate_ffmpeg", return_value=Path("ffmpeg.exe")), \
             mock.patch.object(generate_lrc, "locate_whisper", return_value=Path("whisper.exe")), \
             mock.patch.object(generate_lrc, "locate_model", return_value=Path("model.bin")), \
             mock.patch.object(generate_lrc, "validate_tools"), \
             mock.patch.object(generate_lrc, "validate_model"), \
             mock.patch.object(generate_lrc, "process_track", return_value=mock.Mock(detail="已保留重复歌词")) as process:
            worker.process(self.settings, job, "recognize")
        self.assertIs(process.call_args.args[-1], True)
        self.assertEqual(self.source.read_bytes(), b"original-audio")

    def test_playlist_inspection_preserves_valid_weight_comments_and_disabled_lyrics(self):
        (self.root / "music/歌曲.mp3").write_bytes(b"unchanged")
        (self.root / "lyrics/自定义.lrc").write_text("[00:01]歌词\n", encoding="utf-8")
        (self.root / "music/纯音乐.mp3").write_bytes(b"unchanged")
        text = ("# 注释\n\n歌曲.mp3|自定义.lrc\n歌曲.mp3|自定义.lrc\n纯音乐.mp3|-\n"
                "丢失.mp3|-\n格式错误\n歌曲.mp3|-\n../路径.mp3|-\n")
        cleaned, issues = inspect_playlist(self.root, text)
        self.assertEqual([issue.number for issue in issues], [6, 7, 8, 9])
        self.assertEqual([issue.unparsed for issue in issues], [False, True, True, True])
        entries, comments = read_entries(cleaned)
        self.assertEqual(entries[0].weight, 2)
        self.assertEqual(entries[0].lyric, "自定义.lrc")
        self.assertFalse(entries[1].use_lyrics)
        self.assertEqual(comments, ["# 注释"])
        self.assertFalse(inspect_playlist(self.root, write_entries(entries, comments))[1])
        with self.assertRaises(ValueError):
            read_entries(text)
        self.assertEqual(len(read_entries(text, strict=False)[0]), 3)

    def test_playlist_inspection_reports_missing_lyrics_per_weighted_line(self):
        (self.root / "music/歌曲.mp3").write_bytes(b"unchanged")
        text = "歌曲.mp3|找不到.lrc\n" * 2
        cleaned, issues = inspect_playlist(self.root, text)
        self.assertEqual(cleaned, "")
        self.assertEqual(len(issues), 2)
        self.assertTrue(all("歌词缺失" in issue.reason and not issue.unparsed for issue in issues))

    def test_job_manifest_cannot_escape_work_directory(self):
        job = self.job()
        job.directory = str(self.base / "outside")
        core.save_jobs(Path(self.settings.work), [job])
        with self.assertRaises(ValueError):
            core.load_jobs(Path(self.settings.work))

    def test_real_ffmpeg_conversion_and_invalid_file_continuation(self):
        ffmpeg = generate_lrc.locate_ffmpeg(None)
        self.settings.ffmpeg = str(ffmpeg)
        source = self.base / "tone.wav"
        subprocess.run([str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        str(source)], check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        digest = hashlib.sha256(source.read_bytes()).digest()
        bad = self.job()
        good = self.job(source, "正常音频")
        for relative in ("workshop/__init__.py", "workshop/core.py", "workshop/worker.py",
                         "workshop/shared_settings.py",
                         "tools/ai_lyrics.py", "tools/prepare_music.py", "tools/generate_lrc.py"):
            destination = self.base / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BASE / relative, destination)
        self.settings.save(self.base)
        runner = Runner(self.base, queue.Queue())
        try:
            runner.enqueue(bad, ["convert"])
            runner.enqueue(good, ["convert"])
            deadline = time.monotonic() + 20
            while runner.busy and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(runner.busy)
            self.assertEqual(bad.audio_status, "失败")
            self.assertEqual(good.audio_status, "成功")
            ffprobe = ffmpeg.with_name("ffprobe.exe")
            probe = subprocess.run([str(ffprobe), "-v", "error", "-show_streams", "-of", "json", good.audio],
                                   capture_output=True, text=True, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            stream = json.loads(probe.stdout)["streams"][0]
            self.assertEqual((stream["codec_name"], stream["sample_rate"], stream["channels"]), ("mp3", "44100", 2))
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), digest)
        finally:
            runner.close()
            runner.thread.join(3)

    def test_stop_cancels_current_and_remaining_queue(self):
        import sys
        self.settings.save(self.base)
        active, waiting = self.job(stem="当前"), self.job(stem="下一首")
        real_popen = subprocess.Popen
        def fake_worker(command, **kwargs):
            if "workshop.worker" in command:
                command = [sys.executable, "-u", "-c", "import time; print('started',flush=True); time.sleep(30)"]
            return real_popen(command, **kwargs)
        runner = Runner(self.base, queue.Queue())
        try:
            with mock.patch("workshop.runner.subprocess.Popen", side_effect=fake_worker):
                runner.enqueue(active, ["convert"])
                runner.enqueue(waiting, ["convert"])
                deadline = time.monotonic() + 5
                while runner.process is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertIsNotNone(runner.process)
                process = runner.process
                runner.stop()
                deadline = time.monotonic() + 8
                while runner.busy and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(runner.busy)
                self.assertIsNotNone(process.poll())
                self.assertEqual((active.audio_status, waiting.audio_status), ("已取消", "已取消"))
        finally:
            runner.close()
            runner.thread.join(3)

    def test_cancel_one_queued_task_leaves_active_and_next_tasks_running(self):
        import threading
        active, cancelled, following = self.job(stem="当前"), self.job(stem="取消"), self.job(stem="继续")
        entered, release = threading.Event(), threading.Event()
        runner = Runner(self.base, queue.Queue())
        def stage(job, staged, kind, token, key):
            if job is active:
                entered.set()
                release.wait(3)
            runner.check_cancelled(token)
            staged.path("audio").write_bytes(job.stem.encode("utf-8"))
            staged.audio = str(staged.path("audio"))
        try:
            with mock.patch.object(runner, "_stage", side_effect=stage):
                runner.enqueue(active, ["convert"])
                runner.enqueue(cancelled, ["convert"])
                runner.enqueue(following, ["convert"])
                self.assertTrue(entered.wait(3))
                self.assertTrue(runner.cancel(cancelled.id))
                self.assertEqual(cancelled.task_state, "cancelled")
                self.assertEqual(active.task_state, "running")
                release.set()
                deadline = time.monotonic() + 5
                while runner.busy and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(runner.busy)
            self.assertEqual((active.task_state, following.task_state), ("succeeded", "succeeded"))
            self.assertFalse(cancelled.path("audio").exists())
            self.assertFalse(runner.cancel(active.id))
        finally:
            release.set()
            runner.close()
            runner.thread.join(3)

    def test_cancel_between_stages_preserves_prior_results_and_continues_queue(self):
        import threading
        cancelled, following = self.prepared_job(), self.job(stem="下一任务")
        core.atomic_text(cancelled.path("draft"), "[00:01]原草稿\n")
        core.atomic_text(cancelled.path("candidate"), "[00:01]原候选\n")
        before = {kind: cancelled.path(kind).read_bytes() for kind in ("audio", "draft", "candidate")}
        entered = threading.Event()
        runner = Runner(self.base, queue.Queue())
        def stage(job, staged, kind, token, key):
            if kind == "recognize":
                core.atomic_text(staged.path("draft"), "[00:02]未完成草稿\n")
                entered.set()
                token.wait(3)
                runner.check_cancelled(token)
            else:
                staged.path("audio").write_bytes(b"new-derived")
                staged.audio = str(staged.path("audio"))
        try:
            with mock.patch.object(runner, "_stage", side_effect=stage):
                runner.enqueue(cancelled, ["convert", "recognize"])
                runner.enqueue(following, ["convert"])
                self.assertTrue(entered.wait(3))
                self.assertEqual(cancelled.completed_stages, 1)
                runner.cancel(cancelled.id)
                deadline = time.monotonic() + 5
                while runner.busy and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(runner.busy)
            self.assertEqual(cancelled.task_state, "cancelled")
            self.assertEqual(following.task_state, "succeeded")
            for kind, content in before.items():
                self.assertEqual(cancelled.path(kind).read_bytes(), content)
            self.assertFalse(list((Path(cancelled.directory) / "runs").iterdir()))
            self.assertEqual(self.source.read_bytes(), b"original-audio")
        finally:
            runner.close()
            runner.thread.join(3)


if __name__ == "__main__":
    unittest.main()
