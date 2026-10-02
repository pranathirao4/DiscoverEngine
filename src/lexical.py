"""Cheap retrieval lexicon used before Groq and when filtering provided JSON."""

from __future__ import annotations

import re

PHOTOS_MARKERS = (
    "google photos",
    "googlephotos",
    "photos app",
    "google photo",
)

RETRIEVAL_MARKERS = (
    "can't find",
    "cannot find",
    "cant find",
    "could not find",
    "couldn't find",
    "can't remember",
    "cannot remember",
    "don't remember",
    "dont remember",
    "forgot",
    "forgotten",
    "search",
    "find photo",
    "find picture",
    "find screenshot",
    "old photo",
    "old picture",
    "missing photo",
    "photos missing",
    "not showing",
    "keyword",
    "album",
    "timeline",
    "occasion",
    "screenshot",
    "thousands of",
    "large library",
    "face",
    "people",
    "place",
    "location",
    "date search",
    "search by date",
)

MEDICAL_SUBS = (
    "depression",
    "anxiety",
    "mentalhealth",
    "suicidewatch",
    "askdocs",
    "medical",
    "chronicillness",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def mentions_google_photos(text: str, subreddit: str = "") -> bool:
    blob = _norm(text)
    sub = (subreddit or "").lower()
    if sub == "googlephotos":
        return True
    return any(marker in blob for marker in PHOTOS_MARKERS)


def looks_like_retrieval(text: str) -> bool:
    blob = _norm(text)
    return any(marker in blob for marker in RETRIEVAL_MARKERS)


def is_sensitive_subreddit(subreddit: str) -> bool:
    sub = (subreddit or "").lower().replace("r/", "")
    return sub in MEDICAL_SUBS


def json_row_relevant(text: str, subreddit: str) -> bool:
    """Keep provided-JSON rows only if Google Photos retrieval + incomplete memory."""
    if is_sensitive_subreddit(subreddit):
        return False
    if not mentions_google_photos(text, subreddit):
        return False
    return looks_like_retrieval(text)
