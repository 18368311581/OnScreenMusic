from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "generate_lrc.py"
SPEC = importlib.util.spec_from_file_location("generate_lrc", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
generate_lrc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generate_lrc
SPEC.loader.exec_module(generate_lrc)


class GenerateLrcTests(unittest.TestCase):
    @unittest.skipUnless(generate_lrc.FALLBACK_FFMPEG.is_file(), "本机未安装项目约定的 FFmpeg")
    def test_real_ffmpeg_prepares_whisper_wav(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "测试输入.m4a"
            temporary_wav = root / "prepared.wav"
            fixture = subprocess.run(
                [
                    str(generate_lrc.FALLBACK_FFMPEG),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=0.1",
                    "-c:a",
                    "aac",
                    str(source),
                ],
                capture_output=True,
                check=False,
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr.decode(errors="replace"))

            generate_lrc.run_ffmpeg(
                generate_lrc.FALLBACK_FFMPEG,
                source,
                temporary_wav,
            )

            self.assertGreater(temporary_wav.stat().st_size, 44)

    def test_discover_tracks_preserves_relative_directories_and_finds_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            source = Path(temp_name)
            nested = source / "歌手"
            nested.mkdir()
            (nested / "歌曲.flac").write_bytes(b"flac")
            (nested / "歌曲.mp3").write_bytes(b"mp3")
            (source / "忽略.txt").write_text("x", encoding="utf-8")

            tracks = generate_lrc.discover_tracks(source)

            self.assertEqual(len(tracks), 2)
            self.assertEqual(tracks[0].relative_target, Path("歌手") / "歌曲.lrc")
            conflicts = generate_lrc.find_output_conflicts(tracks)
            self.assertEqual(len(conflicts), 1)

    def test_discover_tracks_accepts_one_audio_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            audio = Path(temp_name) / "单曲.MP3"
            audio.write_bytes(b"audio")

            tracks = generate_lrc.discover_tracks(audio)

            self.assertEqual(len(tracks), 1)
            self.assertEqual(tracks[0].relative_source, Path("单曲.MP3"))
            self.assertEqual(tracks[0].relative_target, Path("单曲.lrc"))

    def test_normalize_lrc_keeps_metadata_and_valid_lyrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            generated = Path(temp_name) / "result.lrc"
            generated.write_text(
                "[by:whisper.cpp]\n[00:01.2] 第一句 \n[00:02.345]第二句\n[00:03.00]   \n",
                encoding="utf-8",
            )

            result = generate_lrc.normalize_lrc(generated)

            self.assertEqual(
                result.text,
                "[by:whisper.cpp]\n[00:01.20]第一句\n[00:02.34]第二句\n",
            )
            self.assertEqual(result.repaired_characters, 0)
            self.assertEqual(result.filtered_hallucination_lines, 0)

    def test_normalize_lrc_repairs_truncated_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            generated = Path(temp_name) / "result.lrc"
            generated.write_bytes(
                b"[by:whisper.cpp]\r\n[01:31.36]"
                + "最轻轻的冲散铃铃".encode("utf-8")
                + b"\xe9\x93\r\n"
            )

            result = generate_lrc.normalize_lrc(generated)

            self.assertEqual(
                result.text,
                "[by:whisper.cpp]\n[01:31.36]最轻轻的冲散铃铃�\n",
            )
            self.assertEqual(result.repaired_characters, 1)

    def test_normalize_lrc_filters_watermarks_and_credit_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            generated = Path(temp_name) / "result.lrc"
            generated.write_text(
                "[by:whisper.cpp]\n"
                "[00:00.00]作曲:李宗盛\n"
                "[00:01.00]优优独播剧场——YoYo Television Series Exclusive\n"
                "[00:20.00]Zither Harp\n"
                "[00:30.00]我跨过忘川 也走过彼岸\n",
                encoding="utf-8",
            )

            result = generate_lrc.normalize_lrc(generated)

            self.assertEqual(
                result.text,
                "[by:whisper.cpp]\n[00:30.00]我跨过忘川 也走过彼岸\n",
            )
            self.assertEqual(result.filtered_hallucination_lines, 3)

    def test_normalize_lrc_rejects_only_credit_hallucinations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            generated = Path(temp_name) / "result.lrc"
            generated.write_text(
                "[by:whisper.cpp]\n"
                + "".join(f"[03:{second:02d}.00]作曲:李宗盛\n" for second in range(22, 33)),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(generate_lrc.TrackError, "疑似模型幻觉"):
                generate_lrc.normalize_lrc(generated)

    def test_normalize_lrc_rejects_generic_repetition_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            generated = Path(temp_name) / "result.lrc"
            generated.write_text(
                "[by:whisper.cpp]\n"
                + "".join(
                    f"[00:{second:02d}.00]这是一句不断重复的虚假识别结果\n"
                    for second in range(10)
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(generate_lrc.TrackError, "重复 10/10 次"):
                generate_lrc.normalize_lrc(generated)

    def test_normalize_lrc_allows_confirmed_repetition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            generated = Path(temp_name) / "result.lrc"
            generated.write_text(
                "".join(
                    f"[00:{second:02d}.00]确实属于原歌的重复歌词\n"
                    for second in range(10)
                ),
                encoding="utf-8",
            )

            result = generate_lrc.normalize_lrc(generated, allow_repetition=True)

            self.assertEqual(result.text.count("确实属于原歌的重复歌词"), 10)
            self.assertEqual(result.repetition_warning, "同一句歌词重复 10/10 次")

    def test_strong_whisper_command_is_always_enabled(self) -> None:
        command = generate_lrc.build_whisper_command(
            Path("whisper-cli.exe"),
            Path("model.bin"),
            Path("audio.wav"),
            Path("result"),
            "zh",
            "歌曲《测试》的中文歌词。",
            None,
            False,
        )

        self.assertIn("-sns", command)
        self.assertIn("-nf", command)
        self.assertEqual(command[command.index("-mc") + 1], "0")
        self.assertEqual(command[command.index("--prompt") + 1], "歌曲《测试》的中文歌词。")
        self.assertIn("--suppress-regex", command)
        self.assertNotIn("-ml", command)

    def test_process_track_generates_then_skips_existing_lrc(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source_root = root / "source"
            output_root = root / "output"
            audio = source_root / "子目录" / "测试.mp3"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"audio")
            track = generate_lrc.Track(
                source=audio,
                relative_source=Path("子目录") / "测试.mp3",
                relative_target=Path("子目录") / "测试.lrc",
            )

            def fake_ffmpeg(_ffmpeg: Path, _source: Path, wav: Path) -> None:
                wav.write_bytes(b"R" * 45)

            def fake_whisper(
                _whisper: Path,
                _model: Path,
                _wav: Path,
                output_prefix: Path,
                _language: str,
                _prompt: str,
                _threads: int | None,
                _no_gpu: bool,
            ) -> Path:
                generated = output_prefix.with_suffix(".lrc")
                generated.write_text("[00:00.00]测试歌词\n", encoding="utf-8")
                return generated

            with mock.patch.object(generate_lrc, "run_ffmpeg", side_effect=fake_ffmpeg), mock.patch.object(
                generate_lrc, "run_whisper", side_effect=fake_whisper
            ):
                entry = generate_lrc.process_track(
                    track,
                    output_root,
                    Path("ffmpeg.exe"),
                    Path("whisper-cli.exe"),
                    Path("model.bin"),
                    "auto",
                    None,
                    False,
                    False,
                )

            target = output_root / "子目录" / "测试.lrc"
            self.assertEqual(entry.status, "成功")
            self.assertEqual(target.read_text(encoding="utf-8"), "[00:00.00]测试歌词\n")

            skipped = generate_lrc.process_track(
                track,
                output_root,
                Path("ffmpeg.exe"),
                Path("whisper-cli.exe"),
                Path("model.bin"),
                "auto",
                None,
                False,
                False,
            )
            self.assertEqual(skipped.status, "跳过")

    def test_main_continues_after_one_track_fails_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "a.mp3").write_bytes(b"a")
            (source / "b.mp3").write_bytes(b"b")
            tool = root / "tool.exe"
            model = root / "model.bin"
            tool.write_bytes(b"tool")
            model.write_bytes(b"model")

            calls = 0

            def fake_process(track, output_root, *_args, **_kwargs):
                nonlocal calls
                calls += 1
                target = output_root / track.relative_target
                if track.relative_source.name == "a.mp3":
                    raise generate_lrc.TrackError("模拟识别失败")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("[00:00.00]成功\n", encoding="utf-8")
                return generate_lrc.ReportEntry(track.source, target, "成功", "已生成")

            with mock.patch.object(generate_lrc, "locate_ffmpeg", return_value=tool), mock.patch.object(
                generate_lrc, "locate_whisper", return_value=tool
            ), mock.patch.object(generate_lrc, "locate_model", return_value=model), mock.patch.object(
                generate_lrc, "validate_tools"
            ), mock.patch.object(
                generate_lrc, "validate_model"
            ), mock.patch.object(generate_lrc, "process_track", side_effect=fake_process):
                return_code = generate_lrc.main(
                    ["--source", str(source), "--output", str(output)]
                )

            self.assertEqual(return_code, 1)
            self.assertEqual(calls, 2)
            report = (output / generate_lrc.REPORT_NAME).read_text(encoding="utf-8")
            self.assertIn("成功：1，跳过：0，失败：1", report)
            self.assertIn("模拟识别失败", report)


if __name__ == "__main__":
    unittest.main()
