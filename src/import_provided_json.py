"""Import data/raw/reddit_apify.json: filter, strip authors, map to common schema."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from common import COMMON_FIELDS, RAW_DIR, ALLOWED_REDDIT_SUBS, empty_utterance, strip_author_fields
from lexical import json_row_relevant

IN_PATH = RAW_DIR / "reddit_apify.json"
OUT_CSV = RAW_DIR / "reddit_provided_relevant.csv"
STATUS_PATH = RAW_DIR / "reddit_provided_import_status.json"
SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "samples" / "reddit_sample.json"


def _iso(created_utc) -> str:
    try:
        ts = float(created_utc)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _post_url(item: dict) -> str:
    permalink = item.get("permalink") or ""
    if permalink.startswith("http"):
        return permalink
    if permalink.startswith("/"):
        return "https://www.reddit.com" + permalink
    sub = item.get("subreddit") or ""
    post_id = (item.get("id") or "").removeprefix("t3_")
    if sub and post_id:
        return f"https://www.reddit.com/r/{sub}/comments/{post_id}/"
    return ""


def _walk_comments(node, post_id: str, subreddit: str, rows: list[dict]) -> None:
    if isinstance(node, list):
        for child in node:
            _walk_comments(child, post_id, subreddit, rows)
        return
    if not isinstance(node, dict):
        return
    kind = node.get("kind")
    data = node.get("data", node)
    if kind == "Listing" and isinstance(data, dict):
        _walk_comments(data.get("children"), post_id, subreddit, rows)
        return
    if not isinstance(data, dict):
        return
    body = (data.get("body") or "").strip()
    cid = str(data.get("id") or "").removeprefix("t1_")
    if body and cid and body not in {"[deleted]", "[removed]"}:
        text = body
        if json_row_relevant(text, subreddit):
            row = empty_utterance()
            row["source"] = "reddit"
            row["id"] = cid
            row["date"] = _iso(data.get("created_utc"))
            row["text"] = text
            row["url"] = _post_url({"subreddit": subreddit, "id": post_id, "permalink": data.get("permalink")})
            row["rating"] = "" if data.get("score") is None else str(data.get("score"))
            row["country_or_subreddit"] = subreddit
            row["type"] = "reddit_comment"
            row["parent_post_id"] = post_id
            rows.append(row)
    _walk_comments(data.get("replies"), post_id, subreddit, rows)
    _walk_comments(data.get("children"), post_id, subreddit, rows)


def load_json_array(path: Path) -> list:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, list) else [payload]
    except json.JSONDecodeError as exc:
        print(f"Provided JSON is truncated ({exc}); importing complete objects only.", flush=True)
        decoder = json.JSONDecoder()
        items: list = []
        i = text.find("[") + 1
        length = len(text)
        while i < length:
            while i < length and text[i] in " \r\n\t,":
                i += 1
            if i >= length or text[i] == "]":
                break
            try:
                obj, end = decoder.raw_decode(text, i)
            except json.JSONDecodeError:
                break
            items.append(obj)
            i = end
        return items


def import_provided_json() -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if IN_PATH.resolve() == SAMPLE_PATH.resolve():
        raise RuntimeError("Refusing to ingest the fake sample JSON.")

    payload = strip_author_fields(load_json_array(IN_PATH))

    kept: list[dict] = []
    seen: set[str] = set()
    scanned = 0
    for item in payload:
        scanned += 1
        if not isinstance(item, dict):
            continue
        subreddit = str(item.get("subreddit") or "")
        post_id = str(item.get("id") or "").removeprefix("t3_")
        title = (item.get("title") or "").strip()
        selftext = (item.get("selftext") or "").strip()
        text = f"{title}\n{selftext}".strip()
        if json_row_relevant(text, subreddit) and post_id and post_id not in seen:
            if (subreddit or "").lower() in ALLOWED_REDDIT_SUBS or json_row_relevant(text, subreddit):
                row = empty_utterance()
                row["source"] = "reddit"
                row["id"] = post_id
                row["date"] = _iso(item.get("created_utc"))
                row["text"] = text
                row["url"] = _post_url(item)
                row["rating"] = "" if item.get("score") is None else str(item.get("score"))
                row["country_or_subreddit"] = subreddit
                row["type"] = "reddit_post"
                kept.append(row)
                seen.add(post_id)
        comments = item.get("comments") or item.get("replies")
        _walk_comments(comments, post_id, subreddit, kept)

    # Dedup comments that failed the Google Photos + retrieval filter already in walker.
    unique: list[dict] = []
    ids: set[str] = set()
    for row in kept:
        if not row["id"] or row["id"] in ids:
            continue
        ids.add(row["id"])
        unique.append(row)

    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_FIELDS)
        writer.writeheader()
        writer.writerows(unique)

    status = {
        "status": "ok",
        "scanned_posts": scanned,
        "kept": len(unique),
        "note": "Expect few or zero rows: dump is mostly non-googlephotos threads.",
        "interpretation": (
            "Zero kept rows means the dump failed the Google Photos retrieval filter. "
            "It is not evidence that users have no Reddit problem."
        ),
        "sample_json_ingested": False,
        "csv": str(OUT_CSV),
    }
    STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"Provided JSON: scanned {scanned} posts, kept {len(unique)} relevant rows", flush=True)
    return status


if __name__ == "__main__":
    import_provided_json()
