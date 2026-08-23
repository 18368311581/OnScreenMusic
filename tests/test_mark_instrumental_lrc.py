from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "mark_instrumental_lrc.py"
SPEC = importlib.util.spec_from_file_location("mark_instrumental_lrc", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
mark_instrumental = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mark_instrumental
SPEC.loader.exec_module(mark_instrumental)


def timed_lines(values):
    return "\n".join(
        "[00:{:02d}.00]{}".format(index, value)
        for index, value in enumerate(values)
    ) + "\n"


class MarkInstrumentalLrcTests(unittest.TestCase):
    def test_repeated_credit_is_candidate(self) -> None:
        text = timed_lines(["作曲:李宗盛"] * 11)
        result = mark_instrumental.analyze_lrc_text(text)
        self.assertTrue(result.candidate)
        self.assertIn("制作信息", result.reason)

    def test_watermark_is_candidate(self) -> None:
        text = timed_lines(
            ["作曲:陌优独播剧场——YoYo Television Series Exclusive"] * 10
        )
        self.assertTrue(mark_instrumental.analyze_lrc_text(text).candidate)

    def test_generic_extreme_loop_is_candidate(self) -> None:
        text = timed_lines(["无法理解的内容"] * 9 + ["另一句"])
        result = mark_instrumental.analyze_lrc_text(text)
        self.assertTrue(result.candidate)
        self.assertIn("重复", result.reason)

    def test_nine_line_im_sorry_loop_is_candidate(self) -> None:
        text = """[by:whisper.cpp]
[00:00.00]I'm sorry, I'm sorry
[00:30.00]I'm sorry, I'm sorry
[01:00.00]I'm sorry, I'm sorry
[01:30.00]I'm sorry, I'm sorry
[02:00.00]I'm sorry, I'm sorry, I'm sorry
[02:30.00]I'm sorry, I'm sorry
[02:47.92]I'm sorry, I'm sorry, I'm sorry
[02:51.70]I'm sorry, I'm sorry
[03:05.48]I'm sorry, I'm sorry
"""
        result = mark_instrumental.analyze_lrc_text(text)
        self.assertTrue(result.candidate)
        self.assertIn("不足 10 行", result.reason)

    def test_fewer_than_ten_unique_lyrics_is_candidate(self) -> None:
        text = timed_lines(
            [
                "第一句",
                "第二句",
                "第三句",
                "第四句",
                "第五句",
                "第六句",
                "第七句",
                "第八句",
                "第九句",
            ]
        )
        result = mark_instrumental.analyze_lrc_text(text)
        self.assertTrue(result.candidate)
        self.assertIn("只有 9 行", result.reason)

    def test_normal_repeated_chorus_is_not_candidate(self) -> None:
        text = timed_lines(
            [
                "第一句歌词",
                "第二句歌词",
                "这是副歌",
                "这是副歌",
                "第三句歌词",
                "第四句歌词",
                "这是副歌",
                "这是副歌",
                "第五句歌词",
                "第六句歌词",
            ]
        )
        self.assertFalse(mark_instrumental.analyze_lrc_text(text).candidate)

    def test_exactly_ten_unique_lyrics_is_not_short_candidate(self) -> None:
        text = timed_lines(["第{}句歌词".format(index) for index in range(10)])
        self.assertFalse(mark_instrumental.analyze_lrc_text(text).candidate)

    def test_preview_then_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            source = Path(temp_name)
            candidate = source / "纯音乐.lrc"
            original = timed_lines(["Zither Harp"] * 8)
            candidate.write_text(original, encoding="utf-8")

            preview_code = mark_instrumental.main(["--source", str(source)])
            self.assertEqual(preview_code, 0)
            self.assertEqual(candidate.read_text(encoding="utf-8"), original)

            apply_code = mark_instrumental.main(
                ["--source", str(source), "--apply"]
            )
            self.assertEqual(apply_code, 0)
            self.assertEqual(
                candidate.read_text(encoding="utf-8"),
                mark_instrumental.INSTRUMENTAL_TEXT,
            )
            self.assertTrue((source / mark_instrumental.REPORT_NAME).is_file())


if __name__ == "__main__":
    unittest.main()
