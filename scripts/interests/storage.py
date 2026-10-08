"""Durable normalized history; public files are atomically replaced."""
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path


def stable_id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text() == text:
        return
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path)
    os.chmod(path, 0o600)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events (
      source TEXT NOT NULL, id TEXT NOT NULL, occurred INTEGER NOT NULL,
      item TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(source,id));
    CREATE INDEX IF NOT EXISTS events_time ON events(source,occurred);
    CREATE TABLE IF NOT EXISTS snapshots (
      observed INTEGER NOT NULL, appid TEXT NOT NULL, minutes INTEGER NOT NULL,
      payload TEXT NOT NULL, PRIMARY KEY(observed,appid));
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY, source TEXT NOT NULL, attempted INTEGER NOT NULL,
      ok INTEGER NOT NULL, reason TEXT NOT NULL);
    """)
    version = get_meta(db, "schema", 1)
    if version != 1:
        raise ValueError("Unsupported history schema; preserve database and upgrade collector")
    set_meta(db, "schema", 1)
    db.commit()
    return db


def get_meta(db, key, default=None):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_meta(db, key, value):
    db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))


def save_events(db, source, events):
    for event in events:
        db.execute("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)", (
            source, event["id"], event["occurred"], event["item"], json.dumps(event)))


@contextmanager
def exclusive_lock(state_dir):
    import fcntl
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_dir / "sync.lock").open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another interests collection is running") from None
        yield
