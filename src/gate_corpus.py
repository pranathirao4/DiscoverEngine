"""Phase 2: gate and extract the full Play + Reddit corpus, then record go/no-go."""

from __future__ import annotations

import csv
import json
import sqlite3
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from common import COMMON_FIELDS, PROCESSED_DIR, load_env, load_taxonomy
from groq_client import GroqClient
from init_db import DB_PATH, init_db
from label import LABEL_FIELDS, cache_has, extract_item, gate_item, lexical_out_of_scope
from lexical import looks_like_retrieval
from prompts import EXTRACT_PROMPT_VERSION, RELEVANCE_PROMPT_VERSION
from write_corpus import CORPUS_ALL, write_corpus_all

LABELED_JSONL = PROCESSED_DIR / "corpus_labeled.jsonl"
LABELED_CSV = PROCESSED_DIR / "corpus_labeled.csv"
RELEVANT_CSV = PROCESSED_DIR / "corpus_relevant.csv"
COUNTS_PATH = PROCESSED_DIR / "gate_counts.json"
GO_NO_GO_PATH = PROCESSED_DIR / "go_nogo.json"
GO_THRESHOLD = 150
ADJACENT_EXTRACT_CAP = 40
FIELDNAMES = COMMON_FIELDS + LABEL_FIELDS


def _load_done(path: Path) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            item_id = row.get("id")
            if item_id:
                done[item_id] = row
    return done


def _append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _order_for_gate(rows: list[dict]) -> list[dict]:
    """Lexical retrieval hits first, then the rest. Every row is still gated."""
    hits = [row for row in rows if looks_like_retrieval(row.get("text") or "")]
    hit_ids = {row.get("id") for row in hits}
    rest = [row for row in rows if row.get("id") not in hit_ids]
    return hits + rest


def _persist_sqlite(rows: list[dict], model_id: str) -> None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM retrieval_evidence")
        conn.execute("DELETE FROM relevance_labels")
        conn.executemany(
            """
            INSERT OR REPLACE INTO relevance_labels (
                utterance_id, relevance, confidence, exclude_reason, rationale,
                prompt_version, model_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row["relevance"],
                    row["confidence"],
                    row.get("exclude_reason") or "",
                    row.get("rationale") or "",
                    RELEVANCE_PROMPT_VERSION,
                    model_id,
                )
                for row in rows
                if row.get("id")
            ],
        )
        extracted = [row for row in rows if row.get("failure_type") or row.get("quotes") not in ("", "[]", None)]
        conn.executemany(
            """
            INSERT OR REPLACE INTO retrieval_evidence (
                utterance_id, photo_type, failure_type, memory_anchors, forgotten_anchors,
                retrieval_behaviors, quotes, confidence, prompt_version, model_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row.get("photo_type") or "",
                    row.get("failure_type") or "",
                    row.get("memory_anchors") or "[]",
                    row.get("forgotten_anchors") or "[]",
                    row.get("retrieval_behaviors") or "[]",
                    row.get("quotes") or "[]",
                    row.get("confidence") or "",
                    EXTRACT_PROMPT_VERSION,
                    model_id,
                )
                for row in extracted
            ],
        )
        conn.commit()


def _summarize(rows: list[dict], complete: bool) -> dict:
    in_scope_ids = {row["id"] for row in rows if row.get("relevance") == "in_scope" and row.get("id")}
    decision = "go" if len(in_scope_ids) >= GO_THRESHOLD else "no-go"
    counts = {
        "n": len(rows),
        "complete": complete,
        "relevance": dict(Counter(row.get("relevance") or "" for row in rows)),
        "confidence": dict(Counter(row.get("confidence") or "" for row in rows)),
        "failure_type": dict(Counter(row.get("failure_type") or "" for row in rows if row.get("failure_type"))),
        "unique_in_scope": len(in_scope_ids),
        "threshold": GO_THRESHOLD,
        "decision": decision if complete else "incomplete",
    }
    return counts


def write_outputs(rows: list[dict], model_id: str, complete: bool) -> dict:
    ordered = list(rows)
    _write_csv(LABELED_CSV, ordered)
    relevant = [row for row in ordered if row.get("relevance") == "in_scope"]
    _write_csv(RELEVANT_CSV, relevant)
    counts = _summarize(ordered, complete)
    counts["csv_labeled"] = str(LABELED_CSV)
    counts["csv_relevant"] = str(RELEVANT_CSV)
    COUNTS_PATH.write_text(json.dumps(counts, indent=2), encoding="utf-8")
    if complete:
        note = (
            f"Unique in-scope ids = {counts['unique_in_scope']} (threshold {GO_THRESHOLD}). "
            "Phase 4 clustering waits on go. A no-go means collect more before ranking, "
            "not that users have no retrieval problem."
        )
        payload = {
            "decision": counts["decision"],
            "unique_in_scope": counts["unique_in_scope"],
            "threshold": GO_THRESHOLD,
            "relevance": counts["relevance"],
            "note": note,
        }
        GO_NO_GO_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _persist_sqlite(ordered, model_id)
        print(json.dumps(payload, indent=2), flush=True)
    return counts


def run_gate(limit: int = 0) -> dict:
    """Gate every corpus_all row. Extract every in_scope row and a small adjacent sample."""
    load_env()
    tax = load_taxonomy()
    write_corpus_all()
    with CORPUS_ALL.open(encoding="utf-8", newline="") as handle:
        corpus = list(csv.DictReader(handle))
    corpus = _order_for_gate(corpus)
    if limit > 0:
        corpus = corpus[:limit]

    probe = GroqClient()
    if not probe.api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Add it to env and re-run python src/cli.py gate.")
    model_id = probe.model_id

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    done = _load_done(LABELED_JSONL)
    state_lock = threading.Lock()
    adjacent_extracted = sum(
        1 for row in done.values() if row.get("relevance") == "adjacent" and row.get("failure_type")
    )
    local_client = threading.local()

    def worker_client() -> GroqClient:
        client = getattr(local_client, "client", None)
        if client is None:
            client = GroqClient()
            local_client.client = client
        return client

    def label_one(item: dict) -> dict | None:
        nonlocal adjacent_extracted
        client = worker_client()
        item_id = (item.get("id") or "").strip()
        live = not cache_has(client, item_id, RELEVANCE_PROMPT_VERSION)
        try:
            row = gate_item(client, item, tax)
        except Exception as exc:  # noqa: BLE001 — keep the run resumable
            print(f"  gate failed {item_id}: {exc}", flush=True)
            time.sleep(2)
            return None
        if live:
            time.sleep(0.25)
        relevance = row.get("relevance")
        with state_lock:
            do_extract = relevance == "in_scope" or (
                relevance == "adjacent" and adjacent_extracted < ADJACENT_EXTRACT_CAP
            )
            if do_extract and relevance == "adjacent":
                adjacent_extracted += 1
        if do_extract:
            live_extract = not cache_has(client, item_id, EXTRACT_PROMPT_VERSION)
            try:
                row = extract_item(client, row, tax)
            except Exception as exc:  # noqa: BLE001
                print(f"  extract failed, keeping the relevance label {item_id}: {exc}", flush=True)
                row["rationale"] = ((row.get("rationale") or "") + " Extract failed; relevance kept.").strip()
            if live_extract:
                time.sleep(0.25)
        return row

    pending = [item for item in corpus if (item.get("id") or "").strip() and (item.get("id") or "").strip() not in done]
    non_hits = [item for item in pending if not looks_like_retrieval(item.get("text") or "")]
    sample_ids = {(item.get("id") or "").strip() for item in non_hits[:40]}
    screened: list[dict] = []
    llm_pending: list[dict] = []
    for item in pending:
        item_id = (item.get("id") or "").strip()
        if item_id in sample_ids or looks_like_retrieval(item.get("text") or ""):
            llm_pending.append(item)
        else:
            screened.append(lexical_out_of_scope(item))
    if screened:
        for row in screened:
            done[row["id"]] = row
            _append(LABELED_JSONL, row)
        print(f"Lexical screen labeled {len(screened)} non-hits without Groq.", flush=True)
        write_outputs(list(done.values()), model_id, complete=False)
    pending = llm_pending
    total = len(corpus)
    print(f"Labeling {len(pending)} remaining of {total}", flush=True)
    finished = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(label_one, item) for item in pending]
        for future in as_completed(futures):
            row = future.result()
            if not row or not row.get("id"):
                continue
            with state_lock:
                if row["id"] in done:
                    continue
                done[row["id"]] = row
                _append(LABELED_JSONL, row)
                finished += 1
                if len(done) % 25 == 0:
                    write_outputs(list(done.values()), model_id, complete=False)
                if finished % 20 == 0:
                    print(f"  labeled {len(done)}/{total}", flush=True)

    missing = [item for item in corpus if (item.get("id") or "").strip() not in done]
    complete = not missing and (limit == 0 or len(corpus) == limit)
    # A debug --limit run is complete for that slice only when every selected id is labeled.
    if limit > 0:
        complete = not missing
    counts = write_outputs(list(done.values()), model_id, complete=complete and limit == 0)
    if limit > 0:
        print(f"Stopped after limit {limit}. Go/no-go is recorded only for a full run.", flush=True)
    elif missing:
        print(f"Incomplete: {len(missing)} rows still unlabeled. Re-run python src/cli.py gate.", flush=True)
    print(f"corpus_relevant.csv rows (in_scope only): {counts['relevance'].get('in_scope', 0)}", flush=True)
    return counts


if __name__ == "__main__":
    run_gate()
