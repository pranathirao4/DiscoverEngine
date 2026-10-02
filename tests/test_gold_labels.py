"""Gold relevance and extraction against Groq. Cached after the first run."""

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))

from common import load_env, load_taxonomy  # noqa: E402
from groq_client import GroqClient  # noqa: E402
from label import extract_item, gate_item  # noqa: E402

GOLD = ROOT / "tests" / "gold"


def _read_jsonl(name: str) -> list[dict]:
    rows = []
    for line in (GOLD / name).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _utterance(spec: dict) -> dict:
    return {
        "id": spec["id"],
        "source": spec.get("source") or "play",
        "type": spec.get("type") or "play_review",
        "date": "",
        "text": spec["text"],
        "url": "https://example.invalid/gold",
        "rating": "",
        "country_or_subreddit": spec.get("country_or_subreddit") or "",
        "parent_post_id": "",
        "search_queries": "",
    }


def test_relevance_gold():
    load_env()
    tax = load_taxonomy()
    client = GroqClient()
    failures = []
    for spec in _read_jsonl("relevance.jsonl"):
        row = gate_item(client, _utterance(spec), tax)
        allowed = spec.get("expect_relevance_any") or [spec["expect_relevance"]]
        if row["relevance"] not in allowed:
            failures.append(f"{spec['id']} relevance {row['relevance']} not in {allowed}")
        if spec.get("expect_exclude_reason") and row["exclude_reason"] != spec["expect_exclude_reason"]:
            failures.append(
                f"{spec['id']} exclude_reason {row['exclude_reason']!r} != {spec['expect_exclude_reason']}"
            )
        allowed_exclude = spec.get("expect_exclude_any")
        if allowed_exclude and row["exclude_reason"] not in allowed_exclude:
            failures.append(f"{spec['id']} exclude_reason {row['exclude_reason']!r} not in {allowed_exclude}")
        if spec.get("expect_failure_type") and row["failure_type"] != spec["expect_failure_type"]:
            failures.append(f"{spec['id']} failure_type {row['failure_type']!r}")
        if spec.get("expect_confidence") and row["confidence"] != spec["expect_confidence"]:
            failures.append(f"{spec['id']} confidence {row['confidence']!r}")
        quotes = json.loads(row.get("quotes") or "[]")
        for quote in quotes:
            if quote not in row["text"]:
                failures.append(f"{spec['id']} quote not in text: {quote!r}")
    assert not failures, "\n".join(failures)


def test_extraction_gold():
    load_env()
    tax = load_taxonomy()
    client = GroqClient()
    failures = []
    for spec in _read_jsonl("extraction.jsonl"):
        row = gate_item(client, _utterance(spec), tax)
        if row["relevance"] in {"in_scope", "adjacent"}:
            row = extract_item(client, row, tax)
        if row["relevance"] != spec["expect_relevance"]:
            failures.append(f"{spec['id']} relevance {row['relevance']} rationale={row.get('rationale')}")
        photo_any = spec.get("expect_photo_type_any")
        if spec.get("expect_photo_type") and row["photo_type"] != spec["expect_photo_type"]:
            failures.append(f"{spec['id']} photo_type {row['photo_type']!r}")
        if photo_any and row["photo_type"] not in photo_any:
            failures.append(f"{spec['id']} photo_type {row['photo_type']!r} not in {photo_any}")
        memory = json.loads(row.get("memory_anchors") or "[]")
        forgotten = json.loads(row.get("forgotten_anchors") or "[]")
        if spec.get("expect_memory_any") and not set(spec["expect_memory_any"]) & set(memory):
            failures.append(f"{spec['id']} memory {memory}")
        if spec.get("expect_forgotten_any") and not set(spec["expect_forgotten_any"]) & set(forgotten):
            failures.append(f"{spec['id']} forgotten {forgotten}")
        for quote in json.loads(row.get("quotes") or "[]"):
            if quote not in row["text"]:
                failures.append(f"{spec['id']} quote not in text: {quote!r}")
    assert not failures, "\n".join(failures)
