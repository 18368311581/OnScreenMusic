from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "update_one_song_gui.pyw"
LOADER = importlib.machinery.SourceFileLoader("update_one_song_gui", str(MODULE_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
update_gui = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = update_gui
LOADER.exec_module(update_gui)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.data = json.dumps(
            {"choices": [{"message": {"content": content}}]},
            ensure_ascii=False,
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self.data


class FakeOpener:
    def __init__(self, content: str) -> None:
        self.content = content
        self.api_request = None

    def open(self, api_request, timeout: int):
        self.api_request = api_request
        if timeout != 180:
            raise AssertionError("unexpected timeout")
        return FakeResponse(self.content)


class UpdateOneSongGuiTests(unittest.TestCase):
    def test_build_command_uses_selected_language(self) -> None:
        command = update_gui.build_command(
            Path("歌曲.mp3"), Path("歌词目录"), "ja", True
        )

        language_index = command.index("--language")
        self.assertEqual(command[language_index + 1], "ja")
        output_index = command.index("--output")
        self.assertEqual(command[output_index + 1], "歌词目录")
        self.assertIn("--allow-repetition", command)
        self.assertEqual(update_gui.LANGUAGE_OPTIONS[update_gui.DEFAULT_LANGUAGE], "zh")

    def test_load_local_settings_reads_paths_and_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            config_path = root / "settings.ini"
            config_path.write_text(
                "[Paths]\n"
                "MusicDirectory=music\n"
                "LyricsDirectory=lyrics\n"
                "\n"
                "[DeepSeek]\n"
                "ApiKey=test-key\n",
                encoding="utf-8",
            )

            settings = update_gui.load_local_settings(config_path)

            self.assertEqual(settings.music_directory, (root / "music").resolve())
            self.assertEqual(settings.lyrics_directory, (root / "lyrics").resolve())
            self.assertEqual(settings.deepseek_api_key, "test-key")

    def test_load_local_settings_reports_missing_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            config_path = Path(temp_name) / "settings.ini"
            config_path.write_text(
                "[Paths]\nMusicDirectory=music\n",
                encoding="utf-8",
            )

            with self.assertRaises(update_gui.LocalSettingsError):
                update_gui.load_local_settings(config_path)

    def test_normalize_ai_lrc_accepts_code_fence_and_timed_lines(self) -> None:
        result = update_gui.normalize_ai_lrc(
            "```lrc\n[00:01.00]第一句\n[00:03.50]第二句\n```"
        )

        self.assertEqual(result, "[00:01.00]第一句\n[00:03.50]第二句\n")

    def test_normalize_ai_lrc_rejects_non_lrc_text(self) -> None:
        with self.assertRaises(update_gui.AiRepairError):
            update_gui.normalize_ai_lrc("这是修复结果\n[00:01.00]第一句")

    def test_normalize_ai_lrc_rejects_reversed_timestamps(self) -> None:
        with self.assertRaises(update_gui.AiRepairError):
            update_gui.normalize_ai_lrc("[00:03.00]第二句\n[00:01.00]第一句")

    def test_request_uses_provided_key_and_no_proxy(self) -> None:
        opener = FakeOpener("[00:01.00]修复歌词")
        with mock.patch.object(update_gui.request, "build_opener", return_value=opener):
            with mock.patch.dict(os.environ, {}, clear=False):
                result = update_gui.request_ai_repair(
                    "歌曲",
                    "[00:01.00]识别歌词",
                    "完整歌词",
                    "test-key",
                )
                self.assertEqual(os.environ["NO_PROXY"], "api.deepseek.com")

        self.assertEqual(result, "[00:01.00]修复歌词")
        self.assertEqual(opener.api_request.full_url, update_gui.DEEPSEEK_ENDPOINT)
        self.assertEqual(opener.api_request.get_header("Authorization"), "Bearer test-key")

    def test_repair_replaces_lrc_only_after_valid_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "歌曲.mp3"
            target = root / "歌曲.lrc"
            source.write_bytes(b"audio")
            target.write_text("[00:01.00]错字\n", encoding="utf-8")

            with mock.patch.object(
                update_gui,
                "request_ai_repair",
                return_value="[00:01.00]正确歌词",
            ):
                update_gui.repair_lrc_with_ai(source, target, "正确歌词", "test-key")

            self.assertEqual(target.read_text(encoding="utf-8"), "[00:01.00]正确歌词\n")
            self.assertEqual(list(root.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
