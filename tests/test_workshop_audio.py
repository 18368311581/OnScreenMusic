"""Native Windows preview checks using generated silence, without media-library access."""
import os
from pathlib import Path
import tempfile
import time
import unittest
import wave

from workshop.audio import AudioPreview


@unittest.skipUnless(os.name == "nt", "Windows audio preview")
class AudioPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workshop-audio-test-")
        self.source = Path(self.temporary.name) / "中文 试听.wav"
        with wave.open(str(self.source), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(44100)
            output.writeframes(bytes(44100 * 2 * 3))
        self.preview = AudioPreview()
        self.preview.set_volume(0)

    def tearDown(self):
        self.preview.close()
        self.temporary.cleanup()

    def test_native_play_pause_seek_resume_and_close(self):
        self.preview.load(self.source)
        self.assertAlmostEqual(self.preview.duration, 3000, delta=50)
        self.assertFalse(self.preview.playing())
        self.preview.seek(1200)
        self.assertAlmostEqual(self.preview.position(), 1200, delta=50)
        self.preview.play()
        self.assertTrue(self.preview.playing())
        self.preview.seek(1700)
        self.assertTrue(self.preview.playing())
        self.preview.pause()
        position = self.preview.position()
        time.sleep(0.06)
        self.assertFalse(self.preview.playing())
        self.assertAlmostEqual(self.preview.position(), position, delta=50)
        self.preview.seek(500)
        self.assertFalse(self.preview.playing())
        self.preview.play()
        self.assertTrue(self.preview.playing())
        self.preview.close()
        self.assertFalse(self.preview.loaded)
        self.assertEqual(self.preview.duration, 0)
        self.source.rename(self.source.with_name("released.wav"))

    def test_invalid_audio_reports_error_and_releases_device(self):
        self.source.write_bytes(b"not audio")
        with self.assertRaises(OSError):
            self.preview.load(self.source)
        self.assertFalse(self.preview.loaded)
        self.preview.close()
