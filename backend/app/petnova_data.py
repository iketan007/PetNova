"""PetNova account and pet-care data storage.

Uses SQLite from the Python standard library. Configure PETNOVA_DB_PATH to a
persistent mounted path in production and PETNOVA_AUTH_SECRET to a long random
secret (32+ characters). Chat endpoint remains independent of this module.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = os.getenv("PETNOVA_DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "petnova.sqlite3"))
TOKEN_SECRET = os.getenv("PETNOVA_AUTH_SECRET", "")


def _connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT NOT NULL UNIQUE COLLATE NOCASE,
          name TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pets (
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
        CREATE TABLE IF NOT EXISTS health_records (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
          title TEXT NOT NULL,
          record_type TEXT NOT NULL DEFAULT 'General',
          record_date TEXT NOT NULL,
          notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS reminders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          pet_id INTEGER REFERENCES pets(id) ON DELETE CASCADE,
          title TEXT NOT NULL,
          due_at TEXT NOT NULL,
          notes TEXT NOT NULL DEFAULT '',
          completed INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_pets_user ON pets(user_id);
        CREATE INDEX IF NOT EXISTS idx_records_user ON health_records(user_id);
        CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);
        """)


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)
    return base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def _verify_password(password: str, encoded: str) -> bool:
    try:
        salt_b64, digest_b64 = encoded.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_token(user_id: int) -> str:
    if len(TOKEN_SECRET) < 32:
        raise RuntimeError("Set PETNOVA_AUTH_SECRET to a random secret of at least 32 characters.")
    payload = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + 60 * 60 * 24 * 7}, separators=(",", ":")).encode())
    signature = _b64(hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return payload + "." + signature


def verify_token(token: str) -> Optional[int]:
    try:
        if len(TOKEN_SECRET) < 32:
            return None
        payload, signature = token.split(".", 1)
        expected = _b64(hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_unb64(payload))
        if int(data["exp"]) < int(time.time()):
            return None
        return int(data["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def register_user(name: str, email: str, password: str) -> Dict[str, Any]:
    with _connect() as db:
        try:
            cur = db.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                             (name.strip(), email.strip().lower(), _hash_password(password)))
        except sqlite3.IntegrityError:
            raise ValueError("An account with this email already exists.")
        row = db.execute("SELECT id,name,email FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    with _connect() as db:
        row = db.execute("SELECT id,name,email,password_hash FROM users WHERE email=? COLLATE NOCASE",
                         (email.strip(),)).fetchone()
    if not row or not _verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    with _connect() as db:
        row = db.execute("SELECT id,name,email,created_at FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_pets(user_id: int):
    with _connect() as db:
        rows = db.execute("SELECT * FROM pets WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
    return [dict(row) for row in rows]


def create_pet(user_id: int, data: Dict[str, Any]):
    with _connect() as db:
        cur = db.execute("""INSERT INTO pets(user_id,name,species,breed,birth_date,weight,notes)
            VALUES(?,?,?,?,?,?,?)""", (user_id, data["name"].strip(), data["species"], data.get("breed",""),
            data.get("birth_date",""), data.get("weight"), data.get("notes","")))
        return dict(db.execute("SELECT * FROM pets WHERE id=?", (cur.lastrowid,)).fetchone())


def update_pet(user_id: int, pet_id: int, data: Dict[str, Any]):
    allowed = {"name", "species", "breed", "birth_date", "weight", "notes"}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return get_pet(user_id, pet_id)
    sql = ", ".join(f"{key}=?" for key in fields)
    with _connect() as db:
        db.execute(f"UPDATE pets SET {sql} WHERE id=? AND user_id=?", (*fields.values(), pet_id, user_id))
        row = db.execute("SELECT * FROM pets WHERE id=? AND user_id=?", (pet_id, user_id)).fetchone()
    return dict(row) if row else None


def get_pet(user_id: int, pet_id: int):
    with _connect() as db:
        row = db.execute("SELECT * FROM pets WHERE id=? AND user_id=?", (pet_id, user_id)).fetchone()
    return dict(row) if row else None


def delete_pet(user_id: int, pet_id: int) -> bool:
    with _connect() as db:
        cur = db.execute("DELETE FROM pets WHERE id=? AND user_id=?", (pet_id, user_id))
    return cur.rowcount > 0


def list_records(user_id: int, pet_id: Optional[int] = None):
    with _connect() as db:
        if pet_id is None:
            rows = db.execute("""SELECT h.*,p.name AS pet_name FROM health_records h JOIN pets p ON p.id=h.pet_id
                WHERE h.user_id=? ORDER BY h.record_date DESC,h.id DESC""", (user_id,)).fetchall()
        else:
            rows = db.execute("""SELECT h.*,p.name AS pet_name FROM health_records h JOIN pets p ON p.id=h.pet_id
                WHERE h.user_id=? AND h.pet_id=? ORDER BY h.record_date DESC,h.id DESC""", (user_id, pet_id)).fetchall()
    return [dict(row) for row in rows]


def create_record(user_id: int, data: Dict[str, Any]):
    with _connect() as db:
        pet = db.execute("SELECT id FROM pets WHERE id=? AND user_id=?", (data["pet_id"], user_id)).fetchone()
        if not pet:
            raise LookupError("Pet not found.")
        cur = db.execute("""INSERT INTO health_records(user_id,pet_id,title,record_type,record_date,notes)
            VALUES(?,?,?,?,?,?)""", (user_id, data["pet_id"], data["title"].strip(), data.get("record_type","General"),
            data["record_date"], data.get("notes","")))
        return dict(db.execute("""SELECT h.*,p.name AS pet_name FROM health_records h JOIN pets p ON p.id=h.pet_id
            WHERE h.id=?""", (cur.lastrowid,)).fetchone())


def delete_record(user_id: int, record_id: int) -> bool:
    with _connect() as db:
        cur = db.execute("DELETE FROM health_records WHERE id=? AND user_id=?", (record_id, user_id))
    return cur.rowcount > 0


def list_reminders(user_id: int):
    with _connect() as db:
        rows = db.execute("""SELECT r.*,p.name AS pet_name FROM reminders r LEFT JOIN pets p ON p.id=r.pet_id
            WHERE r.user_id=? ORDER BY r.completed ASC,r.due_at ASC,r.id DESC""", (user_id,)).fetchall()
    return [dict(row) for row in rows]


def create_reminder(user_id: int, data: Dict[str, Any]):
    with _connect() as db:
        pet_id = data.get("pet_id")
        if pet_id is not None and not db.execute("SELECT id FROM pets WHERE id=? AND user_id=?", (pet_id,user_id)).fetchone():
            raise LookupError("Pet not found.")
        cur = db.execute("""INSERT INTO reminders(user_id,pet_id,title,due_at,notes) VALUES(?,?,?,?,?)""",
                         (user_id, pet_id, data["title"].strip(), data["due_at"], data.get("notes","")))
        row = db.execute("""SELECT r.*,p.name AS pet_name FROM reminders r LEFT JOIN pets p ON p.id=r.pet_id
            WHERE r.id=?""", (cur.lastrowid,)).fetchone()
        return dict(row)


def update_reminder(user_id: int, reminder_id: int, completed: bool):
    with _connect() as db:
        cur = db.execute("UPDATE reminders SET completed=? WHERE id=? AND user_id=?", (int(completed), reminder_id, user_id))
        row = db.execute("""SELECT r.*,p.name AS pet_name FROM reminders r LEFT JOIN pets p ON p.id=r.pet_id
            WHERE r.id=? AND r.user_id=?""", (reminder_id, user_id)).fetchone()
    return dict(row) if cur.rowcount else None


def delete_reminder(user_id: int, reminder_id: int) -> bool:
    with _connect() as db:
        cur = db.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (reminder_id, user_id))
    return cur.rowcount > 0


init_db()
