"""Relevance gate and RER extraction shared by the thin slice and the full corpus."""

from __future__ import annotations

import json
import re

from common import COMMON_FIELDS
from groq_client import GroqClient, cache_path
from lexical import is_sensitive_subreddit
from prompts import (
    EXTRACT_PROMPT_VERSION,
    RELEVANCE_PROMPT_VERSION,
    extract_system,
    extract_user,
    relevance_system,
    relevance_user,
)

LABEL_FIELDS = [
    "relevance",
    "confidence",
    "exclude_reason",
    "rationale",
    "failure_type",
    "photo_type",
    "memory_anchors",
    "forgotten_anchors",
    "retrieval_behaviors",
    "quotes",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Generic search-quality complaints have no incomplete-memory story.
_GENERIC_PHRASES = (
    "search sucks",
    "search is useless",
    "search is terrible",
    "search is bad",
    "search is broken",
    "search is awful",
)
_MEMORY_CUES = (
    "remember",
    "forgot",
    "forgotten",
    "café",
    "cafe",
    "occasion",
    "album",
    "screenshot",
    "trip",
    "filename",
    "last year",
    "don't know the",
    "do not know the",
    "cannot remember",
    "can't remember",
)


def redact_emails(text: str) -> str:
    return EMAIL_RE.sub("[email]", text or "")


def normalize_item(item: dict) -> dict:
    """Stable id, user text only, Reddit type post or comment."""
    row = {field: (item.get(field) or "") for field in COMMON_FIELDS}
    row["id"] = str(row["id"]).strip()
    row["text"] = redact_emails(str(row["text"])).strip()
    row["source"] = str(row["source"]).strip()
    if row["source"] == "reddit" and row["type"] not in {"reddit_post", "reddit_comment"}:
        row["type"] = "reddit_comment" if str(row.get("parent_post_id") or "").strip() else "reddit_post"
    return row


def is_generic_search_only(text: str) -> bool:
    blob = (text or "").lower()
    if not any(phrase in blob for phrase in _GENERIC_PHRASES):
        return False
    return not any(cue in blob for cue in _MEMORY_CUES)


def _valid_enum(value: str, allowed: list) -> str:
    cleaned = str(value or "").strip()
    if cleaned.lower() in {"", "null", "none"}:
        return ""
    if cleaned in allowed:
        return cleaned
    return ""


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def quotes_in_text(quotes: list[str], text: str) -> list[str]:
    """Keep only verbatim spans. Paraphrases are dropped."""
    kept: list[str] = []
    for quote in quotes:
        if quote and quote in (text or ""):
            kept.append(quote)
    return kept


def empty_rer() -> dict:
    return {
        "failure_type": "",
        "photo_type": "",
        "memory_anchors": [],
        "forgotten_anchors": [],
        "retrieval_behaviors": [],
        "quotes": [],
    }


def coerce_extract(raw: dict, tax: dict, text: str) -> dict:
    rer = empty_rer()
    failure = _valid_enum(str(raw.get("failure_type") or ""), tax["failure_types"])
    rer["failure_type"] = failure or "other"
    photo = _valid_enum(str(raw.get("photo_type") or ""), tax["photo_types"])
    rer["photo_type"] = photo
    rer["memory_anchors"] = [v for v in _as_list(raw.get("memory_anchors")) if v in tax["memory_anchors"]]
    rer["forgotten_anchors"] = [
        v for v in _as_list(raw.get("forgotten_anchors")) if v in tax["forgotten_anchors"]
    ]
    rer["retrieval_behaviors"] = [
        v for v in _as_list(raw.get("retrieval_behaviors")) if v in tax["retrieval_behaviors"]
    ]
    rer["quotes"] = quotes_in_text(_as_list(raw.get("quotes")), text)
    return rer


def _row_from(item: dict, **labels) -> dict:
    out = {field: item.get(field, "") for field in COMMON_FIELDS}
    rer = labels.pop("rer", None) or empty_rer()
    out.update(
        {
            "relevance": labels.get("relevance") or "out_of_scope",
            "confidence": labels.get("confidence") or "low",
            "exclude_reason": labels.get("exclude_reason") or "",
            "rationale": labels.get("rationale") or "",
            "failure_type": rer["failure_type"],
            "photo_type": rer["photo_type"],
            "memory_anchors": json.dumps(rer["memory_anchors"], ensure_ascii=False),
            "forgotten_anchors": json.dumps(rer["forgotten_anchors"], ensure_ascii=False),
            "retrieval_behaviors": json.dumps(rer["retrieval_behaviors"], ensure_ascii=False),
            "quotes": json.dumps(rer["quotes"], ensure_ascii=False),
        }
    )
    return out


def finalize_label(row: dict) -> dict:
    """Generic search-quality text is other + low, and not in_scope."""
    if not is_generic_search_only(row.get("text") or ""):
        if row.get("failure_type") == "other":
            row["confidence"] = "low"
        return row
    if row.get("relevance") == "in_scope":
        row["relevance"] = "adjacent"
    row["confidence"] = "low"
    row["failure_type"] = "other"
    if not row.get("exclude_reason"):
        row["rationale"] = (row.get("rationale") or "Generic search complaint without an incomplete-memory story.")
    return row


def lexical_out_of_scope(item: dict) -> dict:
    """Non-hit kept out of Groq. A separate sample of non-hits is still gated by the model."""
    item = normalize_item(item)
    return finalize_label(
        _row_from(
            item,
            relevance="out_of_scope",
            confidence="low",
            rationale=(
                "Lexical screen: no retrieval wording. "
                "This is not evidence that users have no retrieval problem."
            ),
        )
    )


def gate_item(client: GroqClient, item: dict, tax: dict) -> dict:
    """Label relevance. Sensitive subreddits are not sent to Groq."""
    item = normalize_item(item)
    if is_sensitive_subreddit(item.get("country_or_subreddit") or ""):
        return finalize_label(
            _row_from(
                item,
                relevance="out_of_scope",
                confidence="high",
                exclude_reason="medical_or_mental_health_subreddit",
                rationale="Sensitive subreddit excluded before the model.",
            )
        )
    if not item["id"] or not item["text"]:
        return finalize_label(
            _row_from(item, relevance="out_of_scope", confidence="low", rationale="Empty id or text.")
        )
    raw = client.complete_json(
        item_id=item["id"],
        prompt_version=RELEVANCE_PROMPT_VERSION,
        system=relevance_system(),
        user=relevance_user(item),
    )
    relevance = _valid_enum(str(raw.get("relevance") or ""), tax["relevance"]) or "out_of_scope"
    confidence = _valid_enum(str(raw.get("confidence") or ""), tax["confidence"]) or "low"
    exclude = _valid_enum(str(raw.get("exclude_reason") or ""), tax["exclude_reasons"])
    return finalize_label(
        _row_from(
            item,
            relevance=relevance,
            confidence=confidence,
            exclude_reason=exclude,
            rationale=str(raw.get("rationale") or ""),
        )
    )


def extract_item(client: GroqClient, row: dict, tax: dict) -> dict:
    """Fill RER fields. Quotes that are not substrings of text are dropped."""
    raw = client.complete_json(
        item_id=row["id"],
        prompt_version=EXTRACT_PROMPT_VERSION,
        system=extract_system(),
        user=extract_user(row),
    )
    rer = coerce_extract(raw if isinstance(raw, dict) else {}, tax, row.get("text") or "")
    row = dict(row)
    row["failure_type"] = rer["failure_type"]
    row["photo_type"] = rer["photo_type"]
    row["memory_anchors"] = json.dumps(rer["memory_anchors"], ensure_ascii=False)
    row["forgotten_anchors"] = json.dumps(rer["forgotten_anchors"], ensure_ascii=False)
    row["retrieval_behaviors"] = json.dumps(rer["retrieval_behaviors"], ensure_ascii=False)
    row["quotes"] = json.dumps(rer["quotes"], ensure_ascii=False)
    return finalize_label(row)


def cache_has(client: GroqClient, item_id: str, prompt_version: str) -> bool:
    return cache_path(item_id, prompt_version, client.model_id).exists()
