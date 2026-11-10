"""Check the log directory helper without touching the installed system."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[2] / 'ensure-log-dir.sh'

class LogDirectoryTests(unittest.TestCase):
    def test_creates_missing_directory_with_mode_755(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'erx' / 'log'
            result = subprocess.run(['bash', str(HELPER), str(p)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(p.is_dir())
            self.assertEqual(p.stat().st_mode & 0o777, 0o755)

    def test_existing_directory_and_contents_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'log'; p.mkdir(mode=0o700)
            (p / 'existing.log').write_text('preserve')
            before = p.stat().st_mode & 0o777
            result = subprocess.run(['bash', str(HELPER), str(p)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(p.stat().st_mode & 0o777, before)
            self.assertEqual((p / 'existing.log').read_text(), 'preserve')

    def test_non_directory_path_fails_without_overwriting(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'log'; p.write_text('keep')
            result = subprocess.run(['bash', str(HELPER), str(p)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(p.read_text(), 'keep')

if __name__ == '__main__': unittest.main()
