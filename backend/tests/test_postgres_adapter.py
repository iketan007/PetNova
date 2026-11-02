"""Offline unit tests for the PostgreSQL compatibility adapter."""
from app.petnova_postgres import _Connection


class FakeCursor:
    def __init__(self, rows=None, rowcount=1):
        self.rows = list(rows or [])
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class FakePsycopgConnection:
    def __init__(self, cursor=None):
        self.cursor = cursor or FakeCursor()
        self.calls = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self.cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_insert_translates_placeholders_and_preserves_lastrowid():
    fake = FakePsycopgConnection(FakeCursor([{"id": 42}]))
    adapter = _Connection(fake)

    cursor = adapter.execute(
        "INSERT INTO pets(user_id,name) VALUES(?,?)",
        (7, "Milo"),
    )

    assert fake.calls == [
        ("INSERT INTO pets(user_id,name) VALUES(%s,%s) RETURNING id", (7, "Milo"))
    ]
    assert cursor.lastrowid == 42


def test_select_removes_sqlite_collation_and_translates_parameters():
    fake = FakePsycopgConnection(FakeCursor([{"id": 3}]))
    adapter = _Connection(fake)

    row = adapter.execute(
        "SELECT id FROM users WHERE email=? COLLATE NOCASE",
        ("person@example.com",),
    ).fetchone()

    assert fake.calls == [
        ("SELECT id FROM users WHERE email=%s ", ("person@example.com",))
    ]
    assert row == {"id": 3}


def test_connection_context_commits_on_success():
    fake = FakePsycopgConnection()
    with _Connection(fake):
        pass
    assert fake.committed
    assert not fake.rolled_back
    assert fake.closed


def test_connection_context_rolls_back_on_exception():
    fake = FakePsycopgConnection()
    try:
        with _Connection(fake):
            raise RuntimeError("expected")
    except RuntimeError:
        pass
    assert fake.rolled_back
    assert not fake.committed
    assert fake.closed
