"""Harvest Google Play reviews for com.google.android.apps.photos (all star ratings)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone

from common import COMMON_FIELDS, RAW_DIR, empty_utterance, strip_author_fields

PACKAGE = "com.google.android.apps.photos"
LISTING_URL = f"https://play.google.com/store/apps/details?id={PACKAGE}"
OUT_CSV = RAW_DIR / "play_reviews.csv"
OUT_JSON = RAW_DIR / "play_reviews.json"
STATUS_PATH = RAW_DIR / "play_harvest_status.json"


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def review_to_utterance(review: dict, country: str) -> dict:
    row = empty_utterance()
    row["source"] = "play"
    row["id"] = str(review.get("reviewId") or "")
    row["date"] = _iso(review.get("at"))
    row["text"] = (review.get("content") or "").strip()
    row["url"] = LISTING_URL
    score = review.get("score")
    row["rating"] = "" if score is None else str(score)
    row["country_or_subreddit"] = country
    row["type"] = "play_review"
    return row


def harvest_play(count_per_star: int = 40, lang: str = "en", country: str = "us") -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from google_play_scraper import Sort, reviews as fetch_reviews
    except ImportError as exc:
        status = {
            "status": "blocked",
            "reason": "google-play-scraper is not installed",
            "error": str(exc),
        }
        STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
        return status

    collected: list[dict] = []
    errors: list[str] = []
    for star in (1, 2, 3, 4, 5):
        try:
            batch, _token = fetch_reviews(
                PACKAGE,
                lang=lang,
                country=country,
                sort=Sort.NEWEST,
                count=count_per_star,
                filter_score_with=star,
            )
            collected.extend(batch)
            print(f"Play star {star}: {len(batch)} reviews", flush=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"star {star}: {exc}")
            print(f"Play star {star} failed: {exc}", flush=True)

    cleaned = [strip_author_fields(item) for item in collected]
    for item in cleaned:
        item.pop("userName", None)
        item.pop("userImage", None)

    utterances: list[dict] = []
    seen: set[str] = set()
    for review in cleaned:
        row = review_to_utterance(review, country)
        if not row["id"] or not row["text"] or row["id"] in seen:
            continue
        seen.add(row["id"])
        utterances.append(row)

    OUT_JSON.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_FIELDS)
        writer.writeheader()
        writer.writerows(utterances)

    blob = " ".join(errors).lower()
    if utterances and not errors:
        harvest_status = "ok"
    elif not utterances and any(token in blob for token in ("403", "429", "forbidden", "blocked", "timeout")):
        harvest_status = "blocked"
    elif errors and not utterances:
        harvest_status = "error"
    elif errors:
        harvest_status = "error"
    else:
        harvest_status = "empty"
    status = {
        "status": harvest_status,
        "package": PACKAGE,
        "count": len(utterances),
        "errors": errors,
        "csv": str(OUT_CSV),
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "interpretation": (
            "A blocked or empty Play harvest means the listing could not be read. "
            "It is not evidence that users have no retrieval problem."
        ),
    }
    STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"Play harvest {status['status']}: {len(utterances)} reviews -> {OUT_CSV}", flush=True)
    return status


if __name__ == "__main__":
    harvest_play()
