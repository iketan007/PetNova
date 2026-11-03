"""Tests for the read-only SQLite migration preflight report."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.inspect_petnova_db import inspect_database


SCHEMA = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE pets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  species TEXT NOT NULL,
  breed TEXT NOT NULL DEFAULT '',
  birth_date TEXT NOT NULL DEFAULT '',
  weight REAL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE health_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  record_type TEXT NOT NULL DEFAULT 'General',
  record_date TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  pet_id INTEGER REFERENCES pets(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  due_at TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  completed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class DatabaseInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "petnova.sqlite3"
        with sqlite3.connect(self.path) as db:
            db.executescript(SCHEMA)
            db.execute(
                "INSERT INTO users(email,name,password_hash) VALUES(?,?,?)",
                ("owner@example.com", "Owner", "test-hash"),
            )
            db.execute(
                "INSERT INTO pets(user_id,name,species) VALUES(?,?,?)",
                (1, "Milo", "Dog"),
            )
            db.execute(
                "INSERT INTO health_records(user_id,pet_id,title,record_date) VALUES(?,?,?,?)",
                (1, 1, "Vaccination", "2026-11-03"),
            )
            db.execute(
                "INSERT INTO reminders(user_id,pet_id,title,due_at) VALUES(?,?,?,?)",
                (1, 1, "Medicine", "2026-11-04T10:00:00"),
            )

    def test_clean_database_reports_counts_ids_and_digest(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        report = inspect_database(self.path)
        after = hashlib.sha256(self.path.read_bytes()).hexdigest()

        self.assertTrue(report["ok"])
        self.assertEqual(report["integrity_check"], "ok")
        self.assertEqual(report["foreign_key_violation_count"], 0)
        self.assertEqual(report["tables"]["users"], {"rows": 1, "max_id": 1})
        self.assertEqual(report["tables"]["pets"], {"rows": 1, "max_id": 1})
        self.assertEqual(report["tables"]["health_records"], {"rows": 1, "max_id": 1})
        self.assertEqual(report["tables"]["reminders"], {"rows": 1, "max_id": 1})
        self.assertEqual(report["sha256"], before)
        self.assertEqual(after, before, "inspection must not modify the database")
        self.assertNotIn("owner@example.com", str(report))
        self.assertNotIn("Vaccination", str(report))

    def test_detects_cross_owner_record_and_reminder_links(self):
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO users(email,name,password_hash) VALUES(?,?,?)",
                ("other@example.com", "Other", "test-hash"),
            )
            db.execute(
                "INSERT INTO health_records(user_id,pet_id,title,record_date) VALUES(?,?,?,?)",
                (2, 1, "Wrong owner", "2026-11-03"),
            )
            db.execute(
                "INSERT INTO reminders(user_id,pet_id,title,due_at) VALUES(?,?,?,?)",
                (2, 1, "Wrong owner", "2026-11-04T10:00:00"),
            )

        report = inspect_database(self.path)
        self.assertFalse(report["ok"])
        self.assertEqual(report["ownership_checks"]["health_record_owner_mismatches"], 1)
        self.assertEqual(report["ownership_checks"]["reminder_owner_mismatches"], 1)

    def test_detects_foreign_key_violations(self):
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute(
                "INSERT INTO pets(user_id,name,species) VALUES(?,?,?)",
                (999, "Orphan", "Dog"),
            )

        report = inspect_database(self.path)
        self.assertFalse(report["ok"])
        self.assertEqual(report["foreign_key_violation_count"], 1)

    def test_rejects_missing_database_and_incomplete_schema(self):
        with self.assertRaises(FileNotFoundError):
            inspect_database(self.path.parent / "missing.sqlite3")

        incomplete = self.path.parent / "incomplete.sqlite3"
        with sqlite3.connect(incomplete) as db:
            db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
        with self.assertRaisesRegex(ValueError, "missing required tables"):
            inspect_database(incomplete)


if __name__ == "__main__":
    unittest.main()
