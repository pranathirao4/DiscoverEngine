"""Parse docs/sources.md into config/sources.yaml (Phase 1 compile_sources)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import yaml

from common import SOURCES_MD, SOURCES_YAML


def _query_from_search_url(url: str) -> str:
    match = re.search(r"[?&]q=([^&]+)", url)
    if not match:
        return ""
    from urllib.parse import unquote_plus

    return unquote_plus(match.group(1)).replace("+", " ").strip()


def compile_sources(markdown: str | None = None) -> dict:
    text = markdown if markdown is not None else SOURCES_MD.read_text(encoding="utf-8")

    play_pkg = "com.google.android.apps.photos"
    play_url_match = re.search(
        r"https://play\.google\.com/store/apps/details\?id=[\w.]+", text
    )
    app_id_match = re.search(r"id(\d{6,})", text)
    app_url_match = re.search(r"https://apps\.apple\.com/[^\s)]+", text)

    reddit_queries: list[dict] = []
    for row in re.finditer(
        r"^\| ([^|]+) \| (https://www\.reddit\.com/[^\s|]+) \|$",
        text,
        flags=re.MULTILINE,
    ):
        label, url = row.group(1).strip(), row.group(2).strip()
        if "/comments/" in url:
            continue
        reddit_queries.append(
            {
                "label": label,
                "url": url,
                "query": _query_from_search_url(url),
                "subreddit_scoped": "/r/" in url.split("search")[0],
                "executed_via": "arctic_shift",
            }
        )

    threads: list[dict] = []
    for match in re.finditer(
        r"https://www\.reddit\.com/r/([^/]+)/comments/([^/]+)/", text
    ):
        sub, post_id = match.group(1), match.group(2)
        url = match.group(0)
        if any(item["id"] == post_id for item in threads):
            continue
        threads.append({"id": post_id, "subreddit": sub, "url": url})

    youtube: list[dict] = []
    for match in re.finditer(r"https://youtu\.be/([\w-]+)", text):
        video_id = match.group(1)
        url = match.group(0).split("?")[0]
        if any(item["id"] == video_id for item in youtube):
            continue
        youtube.append({"id": video_id, "url": url})

    arctic_subs = ["googlephotos", "GooglePixel", "AndroidQuestions"]
    arctic_queries = [
        "can't find photo",
        "search old photo",
        "find screenshot",
        "can't remember",
        "search not working",
        "find picture",
        "photos missing",
        "how do I find",
    ]
    queries_line = re.search(r"\*\*Queries:\*\*\s*(.+)", text)
    if queries_line:
        arctic_queries = [part.strip() for part in queries_line.group(1).split(";") if part.strip()]
    subs_line = re.search(r"\*\*Subreddits:\*\*\s*(.+)", text)
    if subs_line:
        arctic_subs = [part.strip() for part in subs_line.group(1).split(",") if part.strip()]

    registry = {
        "compiled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "play": {
            "package": play_pkg,
            "url": play_url_match.group(0) if play_url_match else "",
            "type": "play_review",
        },
        "app_store": {
            "app_id": app_id_match.group(1) if app_id_match else "962194608",
            "url": app_url_match.group(0).rstrip(")") if app_url_match else "",
            "type": "app_store_review",
        },
        "reddit": {
            "subreddit_of_record": "googlephotos",
            "search_queries": reddit_queries,
            "listed_threads": threads,
            "note": "Global reddit.com/search URLs are executed via Arctic Shift against allowed subreddits, not as live global search.",
        },
        "youtube": youtube,
        "arctic_shift": {
            "base": "https://arctic-shift.photon-reddit.com",
            "subreddits": arctic_subs,
            "queries": arctic_queries,
        },
    }
    return registry


def write_sources_yaml(registry: dict | None = None) -> None:
    data = registry if registry is not None else compile_sources()
    SOURCES_YAML.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_YAML.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_sources_yaml()
    print(f"Wrote {SOURCES_YAML}")
