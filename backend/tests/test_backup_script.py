"""Regression tests for the operational SQLite backup script."""
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_petnova_db.py"


class BackupScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source.sqlite3"
        self.destination = self.root / "backup.sqlite3"
        with sqlite3.connect(self.source) as db:
            db.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT INTO sample(value) VALUES (?)", ("backup-check",))

    def run_script(self, destination=None, source=None):
        args = [
            sys.executable,
            str(SCRIPT),
            str(destination or self.destination),
            "--source",
            str(source or self.source),
        ]
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def test_creates_consistent_backup_with_data(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(self.destination) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                db.execute("SELECT value FROM sample").fetchone()[0],
                "backup-check",
            )

    def test_refuses_to_overwrite_existing_backup(self):
        self.destination.write_bytes(b"keep this existing file")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.destination.read_bytes(), b"keep this existing file")

    def test_missing_source_fails_without_creating_backup(self):
        missing = self.root / "missing.sqlite3"
        result = self.run_script(source=missing)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
