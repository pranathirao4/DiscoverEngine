"""Record whether listing / thread / video URLs in sources.yaml respond."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import requests
import yaml

from common import PROCESSED_DIR, SOURCES_YAML

OUT_PATH = PROCESSED_DIR / "url_verification.json"
HEADERS = {"User-Agent": "photos-research-script (student PM case study)"}


def _check(url: str) -> dict:
    try:
        response = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        return {"url": url, "status_code": response.status_code, "ok": response.ok}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "status_code": None, "ok": False, "error": str(exc)}


def verify_urls() -> dict:
    registry = yaml.safe_load(SOURCES_YAML.read_text(encoding="utf-8"))
    checks: list[dict] = []
    play_url = (registry.get("play") or {}).get("url")
    app_url = (registry.get("app_store") or {}).get("url")
    if play_url:
        item = _check(play_url)
        item["kind"] = "play_listing"
        checks.append(item)
    if app_url:
        item = _check(app_url)
        item["kind"] = "app_store_listing"
        checks.append(item)
    for thread in (registry.get("reddit") or {}).get("listed_threads") or []:
        item = _check(thread["url"])
        item["kind"] = "reddit_thread"
        item["id"] = thread.get("id")
        item["note"] = "Live page check only; corpus fetch uses Arctic Shift comments/tree."
        checks.append(item)
    for video in registry.get("youtube") or []:
        item = _check(video["url"])
        item["kind"] = "youtube"
        item["id"] = video.get("id")
        checks.append(item)
    for query in (registry.get("reddit") or {}).get("search_queries") or []:
        checks.append(
            {
                "url": query.get("url"),
                "kind": "reddit_query",
                "ok": None,
                "note": "Not opened as live search; executed via Arctic Shift against allowed subreddits.",
                "query": query.get("query"),
            }
        )

    report = {
        "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": checks,
    }
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"URL verification wrote {OUT_PATH}", flush=True)
    return report


if __name__ == "__main__":
    verify_urls()
