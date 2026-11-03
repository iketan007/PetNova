#!/usr/bin/env python3
"""Read-only preflight report for a PetNova SQLite export.

Usage:
  python scripts/inspect_petnova_db.py /secure/path/petnova-export.sqlite3

The report contains only table counts, ID high-water marks, integrity and
ownership checks, file size, and a SHA-256 digest. It never prints user data.
Use the online-backup script first; a non-empty WAL sidecar makes this report
fail because hashing only the main file would not identify the full snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

TABLES = ("users", "pets", "health_records", "reminders")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_database(path: Path | str) -> dict[str, Any]:
    """Inspect an existing SQLite database without changing it."""
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("source path is not a regular file")

    uri = source.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only = ON")

        integrity_rows = [row[0] for row in db.execute("PRAGMA integrity_check")]
        integrity_ok = integrity_rows == ["ok"]

        existing_tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing_tables = [table for table in TABLES if table not in existing_tables]
        if missing_tables:
            raise ValueError("missing required tables: " + ", ".join(missing_tables))

        table_report: dict[str, dict[str, int]] = {}
        for table in TABLES:
            # Table names are selected only from the fixed allow-list above.
            row = db.execute(
                f'SELECT COUNT(*) AS row_count, COALESCE(MAX(id), 0) AS max_id FROM "{table}"'
            ).fetchone()
            table_report[table] = {
                "rows": int(row["row_count"]),
                "max_id": int(row["max_id"]),
            }

        foreign_key_violations = [
            {
                "table": row["table"],
                "rowid": row["rowid"],
                "parent": row["parent"],
                "fkid": row["fkid"],
            }
            for row in db.execute("PRAGMA foreign_key_check")
        ]

        duplicate_emails = db.execute(
            """SELECT COUNT(*) FROM (
                   SELECT lower(email) AS normalized_email
                   FROM users
                   GROUP BY lower(email)
                   HAVING COUNT(*) > 1
               )"""
        ).fetchone()[0]
        record_owner_mismatches = db.execute(
            """SELECT COUNT(*) FROM health_records AS h
               JOIN pets AS p ON p.id = h.pet_id
               WHERE h.user_id != p.user_id"""
        ).fetchone()[0]
        reminder_owner_mismatches = db.execute(
            """SELECT COUNT(*) FROM reminders AS r
               JOIN pets AS p ON p.id = r.pet_id
               WHERE r.user_id != p.user_id"""
        ).fetchone()[0]

    wal_path = Path(str(source) + "-wal")
    wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
    ownership_checks = {
        "health_record_owner_mismatches": int(record_owner_mismatches),
        "reminder_owner_mismatches": int(reminder_owner_mismatches),
    }
    ok = (
        integrity_ok
        and not foreign_key_violations
        and int(duplicate_emails) == 0
        and all(value == 0 for value in ownership_checks.values())
        and wal_bytes == 0
    )
    return {
        "ok": ok,
        "file_name": source.name,
        "file_size_bytes": source.stat().st_size,
        "sha256": _sha256(source),
        "wal_sidecar_bytes": wal_bytes,
        "self_contained_snapshot": wal_bytes == 0,
        "integrity_check": "ok" if integrity_ok else integrity_rows,
        "foreign_key_violation_count": len(foreign_key_violations),
        "case_insensitive_duplicate_email_groups": int(duplicate_emails),
        "ownership_checks": ownership_checks,
        "tables": table_report,
        # Include only structural FK diagnostics; never include user content.
        "foreign_key_violations": foreign_key_violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="SQLite export to inspect (read-only)")
    args = parser.parse_args()

    try:
        report = inspect_database(args.database)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 3

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
