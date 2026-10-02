"""Union harvested sources into corpus_all.csv (audit). Relevant CSV waits for the gate."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from common import COMMON_FIELDS, PROCESSED_DIR, RAW_DIR
from init_db import DB_PATH, init_db

SOURCES = [
    RAW_DIR / "reddit_arctic.csv",
    RAW_DIR / "play_reviews.csv",
    RAW_DIR / "reddit_provided_relevant.csv",
    RAW_DIR / "app_store_reviews.csv",
    RAW_DIR / "youtube_comments.csv",
]

CORPUS_ALL = PROCESSED_DIR / "corpus_all.csv"


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_corpus_all() -> dict:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    merged: list[dict] = []
    seen: set[str] = set()
    per_file: dict[str, int] = {}
    for path in SOURCES:
        rows = _read_csv(path)
        kept = 0
        for raw in rows:
            item_id = (raw.get("id") or "").strip()
            text = (raw.get("text") or "").strip()
            if not item_id or not text or item_id in seen:
                continue
            seen.add(item_id)
            row = {field: raw.get(field, "") or "" for field in COMMON_FIELDS}
            merged.append(row)
            kept += 1
        per_file[path.name] = kept

    with CORPUS_ALL.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_FIELDS)
        writer.writeheader()
        writer.writerows(merged)

    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM utterances")
        conn.executemany(
            """
            INSERT INTO utterances (
                id, source, date, text, url, rating, country_or_subreddit, type,
                parent_post_id, search_queries
            ) VALUES (:id, :source, :date, :text, :url, :rating, :country_or_subreddit, :type,
                      :parent_post_id, :search_queries)
            """,
            merged,
        )
        conn.commit()

    summary = {"rows": len(merged), "per_file": per_file, "path": str(CORPUS_ALL)}
    print(f"corpus_all.csv: {len(merged)} unique rows", flush=True)
    for name, count in per_file.items():
        print(f"  {name}: {count}", flush=True)
    return summary


if __name__ == "__main__":
    write_corpus_all()
