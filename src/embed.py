"""Local BGE embeddings. Never OpenAI. Groq is LLM-only."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import yaml

from common import PROCESSED_DIR, ROOT, load_env

MODELS_YAML = ROOT / "config" / "models.yaml"
EMBED_DIR = PROCESSED_DIR / "embeddings"
OUT_JSONL = EMBED_DIR / "bge_vectors.jsonl"
META_PATH = EMBED_DIR / "bge_meta.json"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching: "


def load_embed_config() -> dict:
    data = yaml.safe_load(MODELS_YAML.read_text(encoding="utf-8"))
    return data.get("embeddings") or {}


def model_id() -> str:
    load_env()
    import os

    cfg = load_embed_config()
    return os.environ.get("BGE_MODEL") or cfg.get("model_id") or DEFAULT_MODEL


def query_prefix() -> str:
    cfg = load_embed_config()
    return str(cfg.get("query_prefix") or QUERY_PREFIX)


def structure_string(row: dict) -> str:
    parts = [
        f"failure_type={row.get('failure_type') or ''}",
        f"photo_type={row.get('photo_type') or ''}",
        f"memory_anchors={row.get('memory_anchors') or ''}",
        f"forgotten_anchors={row.get('forgotten_anchors') or ''}",
        f"retrieval_behaviors={row.get('retrieval_behaviors') or ''}",
    ]
    return ";".join(parts)


def cache_key(item_id: str, kind: str, text: str, mid: str) -> str:
    raw = f"{item_id}|{kind}|{mid}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class BgeEmbedder:
    """sentence-transformers wrapper around BAAI BGE. No OpenAI client."""

    def __init__(self, mid: str | None = None) -> None:
        self.model_id = mid or model_id()
        self._model = None
        self.normalize = True

    def _st(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            print(f"Loading BGE model {self.model_id} (local, not OpenAI)", flush=True)
            self._model = SentenceTransformer(self.model_id)
        return self._model

    def encode(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        prefix = query_prefix() if is_query else ""
        batch = [(prefix + t) if prefix else t for t in texts]
        vectors = self._st().encode(
            batch,
            normalize_embeddings=self.normalize,
            show_progress_bar=len(batch) > 8,
        )
        return [v.tolist() for v in vectors]


def _read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def embed_csv(input_csv: Path, *, queries: bool = False) -> dict:
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    rows = _read_rows(input_csv)
    embedder = BgeEmbedder()
    mid = embedder.model_id
    records: list[dict] = []

    texts = [(row.get("id") or "", (row.get("text") or "").strip()) for row in rows]
    texts = [(i, t) for i, t in texts if i and t]
    if texts:
        vectors = embedder.encode([t for _, t in texts], is_query=queries)
        for (item_id, text), vec in zip(texts, vectors):
            records.append(
                {
                    "id": item_id,
                    "kind": "text",
                    "model_id": mid,
                    "dim": len(vec),
                    "vector": vec,
                    "cache_key": cache_key(item_id, "text", text, mid),
                }
            )

    structured = []
    for row in rows:
        item_id = row.get("id") or ""
        blob = structure_string(row)
        if item_id and any(row.get(k) for k in ("failure_type", "photo_type", "memory_anchors")):
            structured.append((item_id, blob))
    if structured:
        vectors = embedder.encode([blob for _, blob in structured], is_query=False)
        for (item_id, blob), vec in zip(structured, vectors):
            records.append(
                {
                    "id": item_id,
                    "kind": "structure",
                    "model_id": mid,
                    "dim": len(vec),
                    "vector": vec,
                    "cache_key": cache_key(item_id, "structure", blob, mid),
                }
            )

    with OUT_JSONL.open("w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")

    meta = {
        "provider": "local_bge",
        "model_id": mid,
        "openai_used": False,
        "groq_used_for_embeddings": False,
        "input": str(input_csv),
        "n_vectors": len(records),
        "kinds": sorted({r["kind"] for r in records}),
        "dim": records[0]["dim"] if records else None,
        "path": str(OUT_JSONL),
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2), flush=True)
    return meta


def run_embed(input_csv: str | None = None) -> dict:
    path = Path(input_csv) if input_csv else PROCESSED_DIR / "thin_slice_labeled.csv"
    if not path.exists():
        raise FileNotFoundError(f"No labeled CSV at {path}. Run thin-slice first.")
    return embed_csv(path)


if __name__ == "__main__":
    run_embed()
