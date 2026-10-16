"""Tool downloads tested with in-memory HTTP and tiny temporary archives, never large assets."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from workshop.core import Settings
from workshop import tool_setup


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status, self.headers = status, headers or {}


class ToolSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workshop-tools-test-")
        self.root = Path(self.temporary.name)
        for name in ("music", "lyrics", "playlists"):
            (self.root / name).mkdir()
        Settings(str(self.root), str(self.root / "MusicWorkshopWork")).save(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_existing_model_is_reused_without_downloading(self):
        model = self.root / tool_setup.TOOLS["model"][1]
        model.parent.mkdir(parents=True)
        model.write_bytes(b"existing-model")
        with mock.patch.object(tool_setup, "download_source") as source, mock.patch.object(tool_setup, "download_file") as download:
            result = tool_setup.setup_tool(self.root, "model")
            source.assert_not_called()
            download.assert_not_called()
        self.assertEqual(result, model)
        self.assertEqual(Settings.load(self.root).model, str(model))
        self.assertEqual(model.read_bytes(), b"existing-model")

    def test_partial_download_resumes_and_checks_hash(self):
        target = self.root / "model.bin"
        target.with_name("model.bin.part").write_bytes(b"abc")
        response = Response(b"def", 206, {"Content-Range": "bytes 3-5/6"})
        with mock.patch.object(tool_setup.urllib.request, "urlopen", return_value=response) as request:
            tool_setup.download_file("https://example.invalid/model", target, hashlib.sha256(b"abcdef").hexdigest())
        self.assertEqual(request.call_args.args[0].get_header("Range"), "bytes=3-")
        self.assertEqual(target.read_bytes(), b"abcdef")
        self.assertFalse(target.with_name("model.bin.part").exists())

    def test_corrupt_download_does_not_replace_existing_file(self):
        target = self.root / "tool.zip"
        target.write_bytes(b"original")
        with mock.patch.object(tool_setup.urllib.request, "urlopen", return_value=Response(b"wrong")):
            with self.assertRaisesRegex(ValueError, "校验失败"):
                tool_setup.download_file("https://example.invalid/tool", target, "0" * 64)
        self.assertEqual(target.read_bytes(), b"original")

    def test_archive_installs_runtime_and_dlls_only(self):
        archive = self.root / "tools.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("Release/whisper-cli.exe", b"runtime")
            bundle.writestr("Release/ggml.dll", b"dependency")
            bundle.writestr("docs/readme.txt", b"excluded")
        target = self.root / "installed/whisper-cli.exe"
        tool_setup.install_archive(archive, target)
        self.assertEqual(target.read_bytes(), b"runtime")
        self.assertEqual((target.parent / "ggml.dll").read_bytes(), b"dependency")
        self.assertFalse((target.parent / "docs").exists())

    def test_unsafe_archive_does_not_overwrite_runtime(self):
        archive = self.root / "unsafe.zip"
        target = self.root / "installed/whisper-cli.exe"
        target.parent.mkdir()
        target.write_bytes(b"original")
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("Release/whisper-cli.exe", b"new")
            bundle.writestr("Release/../outside.txt", b"unsafe")
        with self.assertRaises(ValueError):
            tool_setup.install_archive(archive, target)
        self.assertEqual(target.read_bytes(), b"original")
        self.assertFalse((self.root / "outside.txt").exists())

    def test_source_selects_cpu_release_and_requires_model_checksum(self):
        releases = [{"assets": []}, {"assets": [
            {"name": "whisper-cublas-x64.zip", "browser_download_url": "wrong"},
            {"name": "whisper-bin-x64.zip", "browser_download_url": "https://github.com/cpu.zip", "digest": "sha256:" + "a" * 64}]}]
        with mock.patch.object(tool_setup, "_json", return_value=releases):
            self.assertEqual(tool_setup.download_source("whisper"), ("https://github.com/cpu.zip", "a" * 64))
        with mock.patch.object(tool_setup, "_json", return_value={"siblings": [{"rfilename": "ggml-large-v3.bin"}]}):
            with self.assertRaises(ValueError):
                tool_setup.download_source("model")

    def test_independent_saves_keep_concurrent_tool_and_key_changes(self):
        first, second = Settings.load(self.root), Settings.load(self.root)
        first.api_key = "new-key"
        first.save(self.root, fields={"api_key"})
        second.whisper = str(self.root / "custom/whisper-cli.exe")
        second.save(self.root, fields={"whisper"})
        result = Settings.load(self.root)
        self.assertEqual(result.api_key, "new-key")
        self.assertEqual(result.whisper, second.whisper)
        self.assertEqual(result.model, first.model)


if __name__ == "__main__":
    unittest.main()
