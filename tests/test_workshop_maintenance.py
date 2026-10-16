import tempfile
import unittest
from pathlib import Path
from workshop.maintenance import CleanupFile, collect_cleanup, clean_files


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.work = self.base / 'MusicWorkshopWork'
        self.paths = ['writes/old.lrc', 'jobs/id/runs/stale/large.wav', 'downloads/ffmpeg.zip',
                      'backups/id/song.lrc', 'jobs/id/song.mp3', 'jobs/id/song.candidate.lrc', 'jobs.json']
        for relative in self.paths:
            path = self.work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'keep-or-clean')
        self.lyric = self.base / 'lyrics/song.lrc'
        self.lyric.parent.mkdir()
        self.lyric.write_bytes(b'original-library-lyric')

    def tearDown(self):
        self.temporary.cleanup()

    def test_temp_cleanup_preserves_results_backups_and_library(self):
        files = [item for item in collect_cleanup(self.work) if item.category == 'temporary']
        count, _, skipped = clean_files(self.work, files)
        self.assertEqual((count, skipped), (2, 0))
        for relative in self.paths[2:]:
            self.assertTrue((self.work / relative).is_file())
        self.assertEqual(self.lyric.read_bytes(), b'original-library-lyric')

    def test_changed_files_and_escaped_paths_are_skipped(self):
        files = [item for item in collect_cleanup(self.work) if item.relative == 'writes/old.lrc']
        (self.work / 'writes/old.lrc').write_bytes(b'new-data-do-not-delete')
        files.append(CleanupFile('../lyrics/song.lrc', 'temporary', self.lyric.stat().st_size, self.lyric.stat().st_mtime_ns))
        self.assertEqual(clean_files(self.work, files), (0, 0, 2))
        self.assertTrue(self.lyric.exists())

    def test_download_and_backup_cleanup_are_separate_and_explicit(self):
        files = collect_cleanup(self.work)
        self.assertEqual(clean_files(self.work, [item for item in files if item.category == 'downloads'])[0], 1)
        self.assertTrue((self.work / 'backups/id/song.lrc').exists())
        self.assertEqual(clean_files(self.work, [item for item in files if item.category == 'backups'])[0], 1)
        self.assertTrue((self.work / 'jobs/id/song.mp3').exists())
        self.assertTrue(self.lyric.exists())

    def test_links_are_not_followed(self):
        link = self.work / 'writes/linked.lrc'
        try:
            link.symlink_to(self.lyric)
        except OSError:
            self.skipTest('Creating symbolic links requires Windows developer mode')
        self.assertNotIn('writes/linked.lrc', [item.relative for item in collect_cleanup(self.work)])
        self.assertTrue(self.lyric.exists())
