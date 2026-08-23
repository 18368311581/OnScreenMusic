from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "convert_dpl_playlist.py"
SPEC = importlib.util.spec_from_file_location("convert_dpl_playlist", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
convert_dpl_playlist = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = convert_dpl_playlist
SPEC.loader.exec_module(convert_dpl_playlist)


class ConvertDplPlaylistTests(unittest.TestCase):
    def test_extracts_file_names_and_ignores_other_dpl_fields(self) -> None:
        text = (
            "DAUMPLAYLIST\n"
            "playname=C:\\Music\\当前歌曲.mp3\n"
            "1*file*C:\\Music\\中文歌曲.mp3\n"
            "1*duration2*123000\n"
            "2*file*D:\\Other\\English Song.MP3\n"
        )

        names, warnings = convert_dpl_playlist.extract_audio_names(text)

        self.assertEqual(names, ["中文歌曲.mp3", "English Song.MP3"])
        self.assertEqual(warnings, [])

    def test_skips_non_mp3_and_duplicate_names(self) -> None:
        text = (
            "DAUMPLAYLIST\n"
            "1*file*C:\\Music\\歌曲.mp3\n"
            "2*file*D:\\Backup\\歌曲.MP3\n"
            "3*file*C:\\Music\\无损.flac\n"
        )

        names, warnings = convert_dpl_playlist.extract_audio_names(text)

        self.assertEqual(names, ["歌曲.mp3"])
        self.assertEqual(len(warnings), 2)

    def test_builds_same_name_lyrics(self) -> None:
        playlist = convert_dpl_playlist.build_playlist(
            ["中文歌曲.mp3", "S.T.A.Y .MP3"]
        )

        self.assertEqual(
            playlist,
            "中文歌曲.mp3|中文歌曲.lrc\nS.T.A.Y .MP3|S.T.A.Y .lrc\n",
        )

    def test_decodes_utf8_bom_gb18030_and_utf16(self) -> None:
        text = "DAUMPLAYLIST\n1*file*C:\\音乐\\歌曲.mp3\n"

        self.assertEqual(convert_dpl_playlist.decode_dpl(text.encode("utf-8-sig")), text)
        self.assertEqual(convert_dpl_playlist.decode_dpl(text.encode("gb18030")), text)
        self.assertEqual(convert_dpl_playlist.decode_dpl(text.encode("utf-16")), text)

    def test_main_writes_utf8_playlist_without_checking_music_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "likes.dpl"
            output = root / "playlists" / "likes.txt"
            source.write_text(
                "DAUMPLAYLIST\n1*file*Z:\\不存在\\仍然保留.mp3\n",
                encoding="utf-8",
            )

            exit_code = convert_dpl_playlist.main(
                ["--source", str(source), "--output", str(output)]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "仍然保留.mp3|仍然保留.lrc\n",
            )


if __name__ == "__main__":
    unittest.main()
