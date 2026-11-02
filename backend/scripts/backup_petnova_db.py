#!/usr/bin/env python3
"""Create a consistent SQLite backup of PetNova workspace data.

Usage:
  python scripts/backup_petnova_db.py /secure/path/petnova-backup.sqlite3

The source defaults to PETNOVA_DB_PATH, then the application's local default.
The destination must not already exist so this script never overwrites a backup.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = BACKEND_DIR / "data" / "petnova.sqlite3"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "destination",
        type=Path,
        help="new backup file path; use secure storage outside the app's ephemeral filesystem",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(os.getenv("PETNOVA_DB_PATH", str(DEFAULT_DB))),
        help="source SQLite file (defaults to PETNOVA_DB_PATH or local default)",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()

    if not source.is_file():
        print(f"ERROR: source database does not exist: {source}", file=sys.stderr)
        return 2
    if source == destination:
        print("ERROR: backup destination must differ from source database.", file=sys.stderr)
        return 2
    if destination.exists():
        print(f"ERROR: refusing to overwrite existing backup: {destination}", file=sys.stderr)
        return 2

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30) as src:
            check = src.execute("PRAGMA integrity_check").fetchone()
            if not check or check[0] != "ok":
                print(f"ERROR: source database integrity check failed: {check}", file=sys.stderr)
                return 3
            with sqlite3.connect(destination, timeout=30) as dst:
                src.backup(dst)
                backup_check = dst.execute("PRAGMA integrity_check").fetchone()
                if not backup_check or backup_check[0] != "ok":
                    raise sqlite3.DatabaseError(f"backup integrity check failed: {backup_check}")
    except Exception as exc:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"ERROR: database backup failed: {exc}", file=sys.stderr)
        return 3

    try:
        os.chmod(destination, 0o600)
    except OSError:
        # Some platforms do not support POSIX permission bits.
        pass

    print(f"Backup created and integrity-checked: {destination}")
    print("Store this file securely and keep it outside the service's ephemeral filesystem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
