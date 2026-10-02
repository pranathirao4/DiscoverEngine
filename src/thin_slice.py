"""Phase 0.5: ~100 items through relevance gate + RER extraction."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from common import COMMON_FIELDS, PROCESSED_DIR, load_env, load_taxonomy
from groq_client import GroqClient
from label import LABEL_FIELDS, extract_item, gate_item
from lexical import looks_like_retrieval
from write_corpus import CORPUS_ALL, write_corpus_all

OUT_CSV = PROCESSED_DIR / "thin_slice_labeled.csv"
COUNTS_PATH = PROCESSED_DIR / "thin_slice_counts.json"


def _load_corpus() -> list[dict]:
    if not CORPUS_ALL.exists():
        write_corpus_all()
    with CORPUS_ALL.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sample_items(rows: list[dict], n: int = 100) -> list[dict]:
    lexical_hits = [row for row in rows if looks_like_retrieval(row.get("text") or "")]
    hit_ids = {row.get("id") for row in lexical_hits}
    rest = [row for row in rows if row.get("id") not in hit_ids]
    posts = [row for row in lexical_hits if row.get("type") == "reddit_post"]
    comments = [row for row in lexical_hits if row.get("type") == "reddit_comment"]
    play = [row for row in lexical_hits if row.get("source") == "play"]
    other = [row for row in lexical_hits if row not in posts + comments + play]
    picked: list[dict] = []
    seen: set[str] = set()

    def take(bucket: list[dict], limit: int) -> None:
        for row in bucket:
            if len(picked) >= n:
                return
            item_id = row.get("id")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            picked.append(row)

    take(play, max(25, n // 4))
    take(posts, max(25, n // 4))
    take(comments, max(30, n // 3))
    take(other, n)
    take(lexical_hits, n)
    take(rest, n)
    return picked[:n]


def run_thin_slice(n: int = 100) -> Path:
    load_env()
    tax = load_taxonomy()
    rows = sample_items(_load_corpus(), n=n)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    try:
        client = GroqClient()
        _ = client.api_key
        if not client.api_key:
            raise RuntimeError("GROQ_API_KEY is missing")
    except Exception as exc:
        unlabeled = PROCESSED_DIR / "thin_slice_unlabeled.csv"
        with unlabeled.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COMMON_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Groq key missing ({exc}). Wrote unlabeled sample: {unlabeled}")
        print("Add GROQ_API_KEY to env and re-run: python src/cli.py thin-slice")
        return unlabeled

    labeled: list[dict] = []
    for i, item in enumerate(rows, start=1):
        print(f"[{i}/{len(rows)}] gate {item['id']}", flush=True)
        out = gate_item(client, item, tax)
        if out["relevance"] in {"in_scope", "adjacent"}:
            print(f"  extract {item['id']}", flush=True)
            out = extract_item(client, out, tax)
        labeled.append(out)

    fieldnames = COMMON_FIELDS + LABEL_FIELDS
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(labeled)

    counts = {
        "n": len(labeled),
        "relevance": dict(Counter(row["relevance"] for row in labeled)),
        "confidence": dict(Counter(row["confidence"] for row in labeled)),
        "failure_type": dict(Counter(row["failure_type"] for row in labeled if row["failure_type"])),
        "csv": str(OUT_CSV),
    }
    COUNTS_PATH.write_text(json.dumps(counts, indent=2), encoding="utf-8")
    print(json.dumps(counts, indent=2))
    return OUT_CSV


if __name__ == "__main__":
    run_thin_slice()
