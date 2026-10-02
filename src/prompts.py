"""Versioned Groq prompts. Enums come only from config/taxonomy.yaml."""

from __future__ import annotations

import json

from common import load_taxonomy

RELEVANCE_PROMPT_VERSION = "relevance_v1"
EXTRACT_PROMPT_VERSION = "extract_rer_v2"


def _enums() -> dict:
    tax = load_taxonomy()
    return {
        "relevance": tax["relevance"],
        "confidence": tax["confidence"],
        "failure_types": tax["failure_types"],
        "memory_anchors": tax["memory_anchors"],
        "forgotten_anchors": tax["forgotten_anchors"],
        "retrieval_behaviors": tax["retrieval_behaviors"],
        "photo_types": tax["photo_types"],
        "exclude_reasons": tax["exclude_reasons"],
    }


def relevance_system() -> str:
    e = _enums()
    return (
        "You label public Google Photos user text for a PM research corpus.\n"
        "Working definition: incomplete-memory retrieval means the user believes a photo/video/"
        "screenshot exists in Google Photos but cannot supply a precise query (missing date, "
        "filename, album, or exact place), and they are trying to find it.\n"
        "Not in scope: storage quota only, editor features, crashes, sync/deletion bugs, "
        "precise-query-failed (they typed the exact name/date and it failed), or not Google Photos.\n"
        "Reply JSON only with keys: relevance, confidence, exclude_reason, rationale.\n"
        f"relevance must be one of {e['relevance']}.\n"
        f"confidence must be one of {e['confidence']} (that this is a true incomplete-memory case).\n"
        f"exclude_reason is null or one of {e['exclude_reasons']}.\n"
        "Keep low-confidence in_scope items; do not drop them.\n"
        "Generic 'search sucks' without incomplete memory is relevance=out_of_scope or adjacent "
        "with failure later as other and confidence low.\n"
        "Never invent usernames. Never claim a success-rate impact."
    )


def relevance_user(item: dict) -> str:
    return json.dumps(
        {
            "id": item.get("id"),
            "source": item.get("source"),
            "type": item.get("type"),
            "country_or_subreddit": item.get("country_or_subreddit"),
            "text": item.get("text"),
        },
        ensure_ascii=False,
    )


def extract_system() -> str:
    e = _enums()
    return (
        "Extract a Retrieval Evidence Record from Google Photos incomplete-memory text.\n"
        "quotes must be exact substrings of the provided text.\n"
        "Use only these enums:\n"
        f"memory_anchors: {e['memory_anchors']}\n"
        f"forgotten_anchors: {e['forgotten_anchors']}\n"
        f"retrieval_behaviors: {e['retrieval_behaviors']}\n"
        f"photo_type: {e['photo_types']}\n"
        f"failure_type: {e['failure_types']}\n"
        f"confidence: {e['confidence']}\n"
        "JSON keys: photo_type, failure_type, memory_anchors, forgotten_anchors, "
        "retrieval_behaviors, quotes, confidence.\n"
        "memory_anchors, forgotten_anchors, retrieval_behaviors, quotes are arrays.\n"
        "If the complaint is only generic search quality, failure_type=other and confidence=low.\n"
        "Brief examples (do not invent these details unless the text says them):\n"
        "- A café or trip they remember, with the date or place name forgotten: "
        "photo_type=travel, memory_anchors include place and/or event_occasion, "
        "forgotten_anchors include exact_date and/or location_name.\n"
        "- A picture of medicine from when they were sick, filename forgotten: "
        "photo_type=medical or document, forgotten_anchors include keyword_filename.\n"
        "If the text never names a place, do not add place."
    )


def extract_user(item: dict) -> str:
    return json.dumps(
        {
            "id": item.get("id"),
            "text": item.get("text"),
        },
        ensure_ascii=False,
    )
