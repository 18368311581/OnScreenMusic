from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "prepare_music.py"
SPEC = importlib.util.spec_from_file_location("prepare_music", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
prepare_music = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare_music
SPEC.loader.exec_module(prepare_music)


class PrepareMusicTests(unittest.TestCase):
    def test_decode_failure_reports_cause_and_preserves_files(self) -> None:
        stderr = (
            "[flac] Could not find codec parameters: unspecified sample format\n"
            "Cannot determine format of input 0:0 after EOF\n"
            "Task finished with error code: -1094995529 (Invalid data found)\n"
            "Terminating thread with return code -22 (Invalid argument)\n"
            "Nothing was written into output file\n"
            "size=0KiB time=N/A\nConversion failed!\n"
        )
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "损坏.flac"
            target = root / "已存在.mp3"
            source.write_bytes(b"invalid audio")
            target.write_bytes(b"existing output")
            with mock.patch.object(
                prepare_music, "run_ffmpeg",
                return_value=subprocess.CompletedProcess([], 1, "", stderr),
            ) as run:
                with self.assertRaisesRegex(prepare_music.TrackError, "无法解码源文件") as error:
                    prepare_music.normalize_audio(Path("ffmpeg.exe"), source, target)
            self.assertIn("Cannot determine format", str(error.exception))
            self.assertIn("Could not find codec parameters", str(error.exception))
            self.assertEqual(run.call_count, 1)
            self.assertEqual(source.read_bytes(), b"invalid audio")
            self.assertEqual(target.read_bytes(), b"existing output")
            self.assertEqual(len(list(root.iterdir())), 2)

    def test_discovers_one_file_and_matching_lrc(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / " 单曲. .wav"
            lyric = root / " 单曲. .lrc"
            source.write_bytes(b"wav")
            lyric.write_text("[00:01.00]歌词\n", encoding="utf-8")

            tracks = prepare_music.discover_tracks(source.resolve())

            self.assertEqual(len(tracks), 1)
            self.assertEqual(tracks[0].source, source.resolve())
            self.assertEqual(tracks[0].relative_source, Path(source.name))
            self.assertEqual(tracks[0].output_stem, "单曲")
            self.assertEqual(tracks[0].lyric_source, lyric)

    def test_rejects_unsupported_single_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "说明.txt"
            source.write_text("not media", encoding="utf-8")

            with self.assertRaisesRegex(prepare_music.StartupError, "不支持"):
                prepare_music.resolve_source_and_output(str(source), str(root / "output"))

    def test_rejects_single_mp3_output_overwriting_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "原始歌曲.mp3"
            source.write_bytes(b"original")

            with self.assertRaisesRegex(prepare_music.StartupError, "覆盖原始 MP3"):
                prepare_music.resolve_source_and_output(str(source), str(root))

    def test_main_processes_single_file_and_preserves_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "单曲.wav"
            lyric = root / "单曲.lrc"
            output = root / "output"
            source_bytes = b"source audio"
            lyric_text = "[00:01.00]测试歌词\n"
            source.write_bytes(source_bytes)
            lyric.write_text(lyric_text, encoding="utf-8")

            def fake_normalize(_ffmpeg: Path, _source: Path, target: Path) -> None:
                target.write_bytes(b"normalized mp3")

            with mock.patch.object(
                prepare_music, "locate_ffmpeg", return_value=Path("ffmpeg.exe")
            ), mock.patch.object(prepare_music, "validate_ffmpeg"), mock.patch.object(
                prepare_music, "normalize_audio", side_effect=fake_normalize
            ):
                return_code = prepare_music.main(
                    ["--source", str(source), "--output", str(output)]
                )

            self.assertEqual(return_code, 0)
            self.assertEqual((output / "单曲.mp3").read_bytes(), b"normalized mp3")
            self.assertEqual((output / "单曲.lrc").read_text(encoding="utf-8"), lyric_text)
            self.assertTrue((output / prepare_music.REPORT_NAME).is_file())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(lyric.read_text(encoding="utf-8"), lyric_text)

    def test_normalize_audio_drops_input_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "原始歌曲.mp3"
            target = root / "输出歌曲.mp3"
            source.write_bytes(b"source audio")
            commands: list[list[str]] = []
            measurements = {
                "input_i": "-18.0",
                "input_tp": "-2.0",
                "input_lra": "5.0",
                "input_thresh": "-28.0",
                "target_offset": "0.0",
            }

            def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if "-f" in command:
                    return subprocess.CompletedProcess(
                        command, 0, "", json.dumps(measurements)
                    )
                Path(command[-1]).write_bytes(b"normalized mp3")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(prepare_music, "run_ffmpeg", side_effect=fake_run):
                prepare_music.normalize_audio(Path("ffmpeg.exe"), source, target)

            self.assertEqual(target.read_bytes(), b"normalized mp3")
            self.assertEqual(len(commands), 2)
            output_command = commands[1]
            self.assertEqual(
                output_command[
                    output_command.index("-map_metadata") + 1
                ],
                "-1",
            )
            self.assertEqual(
                output_command[
                    output_command.index("-id3v2_version") + 1
                ],
                "0",
            )
            self.assertEqual(
                output_command[
                    output_command.index("-write_id3v1") + 1
                ],
                "0",
            )


if __name__ == "__main__":
    unittest.main()
