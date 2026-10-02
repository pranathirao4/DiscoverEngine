"""PM Ask: BGE retrieve + Groq answer over the discovery corpus only.

Not a Google Photos product chatbot. Not a find-my-photo assistant.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone

from common import PROCESSED_DIR, load_env
from embed import BgeEmbedder, OUT_JSONL
from groq_client import GroqClient

ASK_PROMPT_VERSION = "ask_v1"
LABELED = PROCESSED_DIR / "thin_slice_labeled.csv"
ASK_LOG = PROCESSED_DIR / "ask_log.jsonl"
MIN_SCORE = 0.32
TOP_K = 8

SYSTEM = (
    "You are a PM research assistant for Google Photos incomplete-memory retrieval. "
    "Answer only from the retrieved evidence items. "
    "Do not invent product advice, success-rate impact, or Photos UI changes. "
    "If the question is unrelated or evidence is too thin, set enough_evidence=false "
    "and say there is not enough evidence. "
    "JSON keys: enough_evidence (bool), answer (string), citation_ids (array of ids), "
    "limitations (string). citation_ids must be ids from the evidence list."
)


def _load_labeled() -> dict[str, dict]:
    if not LABELED.exists():
        return {}
    with LABELED.open(encoding="utf-8", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle) if row.get("id")}


def _load_text_vectors() -> list[dict]:
    if not OUT_JSONL.exists():
        return []
    rows = []
    with OUT_JSONL.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("kind") == "text" and rec.get("vector"):
                rows.append(rec)
    return rows


_EMBEDDER: BgeEmbedder | None = None


def get_embedder() -> BgeEmbedder:
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = BgeEmbedder()
    return _EMBEDDER


def _dot(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


def retrieve(question: str, k: int = TOP_K) -> list[dict]:
    vectors = _load_text_vectors()
    by_id = _load_labeled()
    if not vectors or not by_id:
        return []
    embedder = get_embedder()
    qvec = embedder.encode([question], is_query=True)[0]
    scored = []
    for rec in vectors:
        item = by_id.get(rec["id"])
        if not item:
            continue
        score = _dot(qvec, rec["vector"])
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    hits = []
    for score, item in scored[:k]:
        if score < MIN_SCORE:
            continue
        hits.append({**item, "score": round(score, 4)})
    return hits


def ask(question: str) -> dict:
    load_env()
    question = (question or "").strip()
    if not question:
        return {
            "enough_evidence": False,
            "answer": "Ask a question about the retrieval evidence corpus.",
            "citation_ids": [],
            "hits": [],
        }
    hits = retrieve(question)
    evidence = [
        {
            "id": h.get("id"),
            "source": h.get("source"),
            "relevance": h.get("relevance"),
            "confidence": h.get("confidence"),
            "failure_type": h.get("failure_type"),
            "url": h.get("url"),
            "text": (h.get("text") or "")[:1200],
            "score": h.get("score"),
        }
        for h in hits
    ]
    payload = {"question": question, "evidence": evidence}
    if not evidence:
        result = {
            "enough_evidence": False,
            "answer": "Not enough evidence in the labeled corpus for this question.",
            "citation_ids": [],
            "limitations": "Ask is grounded only in harvested public feedback already labeled.",
            "hits": [],
        }
    else:
        client = GroqClient()
        qid = hashlib.sha256(question.encode("utf-8")).hexdigest()[:24]
        result = client.complete_json(
            item_id=f"ask:{qid}",
            prompt_version=ASK_PROMPT_VERSION,
            system=SYSTEM,
            user=json.dumps(payload, ensure_ascii=False),
        )
        allowed = {h["id"] for h in evidence}
        cites = [c for c in (result.get("citation_ids") or []) if c in allowed]
        result["citation_ids"] = cites
        result["hits"] = evidence
        if result.get("enough_evidence") is False and not result.get("answer"):
            result["answer"] = "Not enough evidence in the corpus."

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    log_row = {
        "asked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "question": question,
        "enough_evidence": result.get("enough_evidence"),
        "citation_ids": result.get("citation_ids"),
    }
    with ASK_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(log_row, ensure_ascii=False) + "\n")
    return result


if __name__ == "__main__":
    import sys

    print(json.dumps(ask(" ".join(sys.argv[1:]) or "What do people remember when they cannot find a photo?"), indent=2))
