"""Create the empty SQLite file from config/schema.sql (Phase 0)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "config" / "schema.sql"
DB_PATH = ROOT / "data" / "processed" / "discovery.sqlite"


def init_db(db_path: Path = DB_PATH) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sql = SCHEMA.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(sql)
    return db_path


if __name__ == "__main__":
    path = init_db()
    print(f"Empty database ready: {path}")
