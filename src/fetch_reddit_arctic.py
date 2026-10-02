"""
Free Reddit fetcher using the Arctic Shift public archive.

This is NOT the official Reddit API. No PRAW, no login, no scraping reddit.com.

API docs (re-checked): https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md
Base URL: https://arctic-shift.photon-reddit.com

Run from the project root, for example:
    python src/fetch_reddit_arctic.py discover --test
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests

# --- Paths (project root is one folder above src/) ---
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CACHE_DIR = RAW_DIR / "reddit_arctic"
CANDIDATES_CSV = RAW_DIR / "reddit_candidates.csv"
COLLECTED_CSV = RAW_DIR / "reddit_arctic.csv"
HARVEST_STATUS_PATH = RAW_DIR / "reddit_arctic_harvest_status.json"
NOT_A_FINDING = (
    "A blocked or empty Arctic Shift harvest means the archive did not answer. "
    "It is not evidence that users have no Reddit problem."
)

BASE_URL = "https://arctic-shift.photon-reddit.com"
STATUS_URL = "https://status.arctic-shift.photon-reddit.com"
USER_AGENT = "photos-research-script (student PM case study)"

# README: keyword search (query) only works together with a subreddit (or author) filter.
DEFAULT_SUBREDDITS = ["googlephotos", "GooglePixel", "AndroidQuestions"]
DEFAULT_QUERIES = [
    "can't find photo",
    "search old photo",
    "find screenshot",
    "can't remember",
    "search not working",
    "find picture",
    "photos missing",
    "how do I find",
]

# README selectable fields for posts do NOT include permalink. Verified HTTP 400:
# {"error": "'permalink' is not a valid field"} — we build the URL from subreddit + id.
POST_FIELDS = "id,created_utc,subreddit,title,selftext,score,num_comments"
# comments/tree README table does not list `fields`; we try COMMENT_FIELDS, then omit if rejected.
# comments/tree README table does not list `fields`; we try, then omit if rejected.
COMMENT_FIELDS = "id,created_utc,body,score,parent_id,link_id"

EMPTY_MARKERS = {"", "[deleted]", "[removed]"}

# Privacy: never persist these keys, even if the API sends them.
AUTHOR_KEY_PREFIX = "author"


def log(message: str) -> None:
    """Print progress so a beginner can follow what the script is doing."""
    print(message, flush=True)


def is_blank_or_removed(text: Any) -> bool:
    value = "" if text is None else str(text).strip()
    return value.lower() in EMPTY_MARKERS or value == ""


def strip_author_fields(obj: Any) -> Any:
    """Walk JSON and drop any key that starts with 'author' (author, author_fullname, ...)."""
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            if str(key).lower().startswith(AUTHOR_KEY_PREFIX):
                continue
            cleaned[key] = strip_author_fields(value)
        return cleaned
    if isinstance(obj, list):
        return [strip_author_fields(item) for item in obj]
    return obj


def to_iso8601(created_utc: Any) -> str:
    """Turn Arctic Shift created_utc (unix seconds or a date string) into ISO 8601 UTC."""
    if created_utc is None or created_utc == "":
        return ""
    if isinstance(created_utc, (int, float)):
        return datetime.fromtimestamp(float(created_utc), tz=timezone.utc).isoformat()
    text = str(created_utc).strip()
    if text.isdigit():
        return datetime.fromtimestamp(float(text), tz=timezone.utc).isoformat()
    return text


def post_url(subreddit: str, post_id: str, permalink: Any = None) -> str:
    """Build a reddit.com link. README has no permalink field; we construct it from id."""
    if permalink:
        path = str(permalink)
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return "https://www.reddit.com" + path
    sub = (subreddit or "").lstrip("r/")
    pid = str(post_id).removeprefix("t3_")
    return f"https://www.reddit.com/r/{sub}/comments/{pid}/"


def cache_filename(endpoint: str, params: dict[str, Any]) -> Path:
    """Stable file name from endpoint + params. Never overwrite: we read if it exists."""
    parts = [endpoint.strip("/").replace("/", "_")]
    for key in sorted(params.keys()):
        raw = "" if params[key] is None else str(params[key])
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)[:80]
        parts.append(f"{key}={safe}")
    name = "__".join(parts) + ".json"
    return CACHE_DIR / name


def check_status() -> dict[str, Any]:
    """Hit the public status page. Return status_page: up, down, or unreachable."""
    log(f"Checking Arctic Shift status: {STATUS_URL}")
    try:
        response = requests.get(
            STATUS_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        if response.status_code == 200:
            body = response.text.lower()
            # Status page lists components; treat HTTP 200 as "up" unless it clearly says down.
            looks_down = "major outage" in body or "service down" in body
            if looks_down:
                log("Status page loaded: service may be DOWN. Requests might fail.")
                return {
                    "status_page": "down",
                    "http": 200,
                    "detail": "status page reports an outage",
                }
            log("Status page loaded: service appears UP (HTTP 200). No uptime guarantee.")
            return {"status_page": "up", "http": 200, "detail": "HTTP 200"}
        log(
            f"Status page returned HTTP {response.status_code}. "
            "The archive might still work; we will try the API next."
        )
        return {
            "status_page": "unreachable",
            "http": response.status_code,
            "detail": f"HTTP {response.status_code}",
        }
    except requests.RequestException as exc:
        log(
            f"Could not reach the status page ({exc}). "
            "We will still try the API. Plain language: the status site did not answer."
        )
        return {"status_page": "unreachable", "http": None, "detail": str(exc)}


def count_data_rows(path: Path) -> int:
    """Count CSV records, not physical lines (text fields contain newlines)."""
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def decide_reddit_status(
    *,
    status_page: str,
    rows_this_run: int,
    previous_rows: int,
    error_count: int,
    stopped: bool,
) -> tuple[str, bool]:
    """Return (status, preserve_previous_file).

    Five failures in a row, or a down archive with nothing new, is `blocked`.
    Never replace a larger existing harvest with a smaller failed run.
    """
    preserve = previous_rows > rows_this_run and (
        stopped or error_count > 0 or rows_this_run == 0 or status_page == "down"
    )
    if stopped and rows_this_run == 0:
        return "blocked", previous_rows > 0
    if status_page == "down" and rows_this_run == 0:
        return "blocked", previous_rows > 0
    if error_count and rows_this_run == 0 and status_page != "up":
        return "blocked", previous_rows > 0
    if stopped:
        return "error", previous_rows > rows_this_run
    if rows_this_run == 0 and error_count:
        return "error", previous_rows > 0
    if rows_this_run == 0:
        return "empty", previous_rows > 0
    if error_count:
        return "error", preserve
    return "ok", False


def write_harvest_status(update: dict[str, Any]) -> dict[str, Any]:
    """Merge a job result into the Reddit harvest status file.

    Overall status is the worst of discover and collect: blocked, then error, then empty, then ok.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    if HARVEST_STATUS_PATH.exists():
        try:
            loaded = json.loads(HARVEST_STATUS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except json.JSONDecodeError:
            current = {}
    for key in ("discover", "collect"):
        incoming = update.get(key)
        if isinstance(incoming, dict):
            previous = current.get(key) if isinstance(current.get(key), dict) else {}
            merged = dict(previous)
            merged.update(incoming)
            current[key] = merged
    for key, value in update.items():
        if key not in {"discover", "collect"}:
            current[key] = value
    current["source"] = "reddit_arctic_shift"
    current["interpretation"] = NOT_A_FINDING
    current["recorded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job_statuses = []
    for key in ("discover", "collect"):
        job = current.get(key)
        if isinstance(job, dict) and job.get("status"):
            job_statuses.append(job["status"])
    if any(item == "blocked" for item in job_statuses):
        current["status"] = "blocked"
    elif any(item == "error" for item in job_statuses):
        current["status"] = "error"
    elif any(item == "ok" for item in job_statuses):
        current["status"] = "ok"
    elif job_statuses:
        current["status"] = "empty"
    elif current.get("status") not in {"ok", "empty", "error", "blocked"}:
        current["status"] = "empty"
    HARVEST_STATUS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    log(f"Harvest status {current.get('status')} -> {HARVEST_STATUS_PATH.name}")
    log(NOT_A_FINDING)
    return current


class ArcticClient:
    """Small HTTP helper: User-Agent, cache, 2–3s pause, retries on 429/5xx/timeouts."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.consecutive_failures = 0
        self.errors: list[str] = []
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def get(self, endpoint: str, params: dict[str, Any]) -> Any | None:
        """Return parsed JSON, or None if we must stop. Reuses cache when present."""
        cache_path = cache_filename(endpoint, params)
        if cache_path.exists():
            log(f"  Cache hit: {cache_path.name}")
            with cache_path.open(encoding="utf-8") as handle:
                return json.load(handle)

        url = BASE_URL + endpoint
        data = self._request_with_retries(url, params)
        if data is None:
            return None

        cleaned = strip_author_fields(data)
        # Never overwrite: only write if still missing (another process could have created it).
        if not cache_path.exists():
            with cache_path.open("w", encoding="utf-8") as handle:
                json.dump(cleaned, handle, ensure_ascii=False, indent=2)
            log(f"  Cached: {cache_path.name}")
        return cleaned

    def _request_with_retries(self, url: str, params: dict[str, Any]) -> Any | None:
        max_tries = 6
        delay = 2.0
        for attempt in range(1, max_tries + 1):
            try:
                # Be kind to a free archive (README: a couple of requests per second is fine;
                # we wait 2–3 seconds anyway).
                pause = random.uniform(2.0, 3.0)
                log(f"  Waiting {pause:.1f}s before request…")
                time.sleep(pause)

                log(f"  GET {url} params={params}")
                response = self.session.get(url, params=params, timeout=60)

                if response.status_code == 429:
                    wait = self._retry_wait_seconds(response, delay)
                    log(
                        f"  Rate limited (HTTP 429). Plain language: too many requests. "
                        f"Waiting {wait:.1f}s (attempt {attempt}/{max_tries})."
                    )
                    time.sleep(wait)
                    delay *= 2
                    continue

                if response.status_code == 422:
                    # README: "Query timed out" / "Maybe slow down a bit" — retry, do not abort.
                    log(
                        f"  HTTP 422: {response.text[:300]}. "
                        "Plain language: the archive was busy or the search was heavy. "
                        f"Waiting longer, then retry {attempt}/{max_tries}."
                    )
                    time.sleep(max(delay, 10.0))
                    delay *= 2
                    continue

                if 500 <= response.status_code < 600:
                    log(
                        f"  Server error HTTP {response.status_code}. "
                        f"Plain language: Arctic Shift had a problem. Retry {attempt}/{max_tries}."
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue

                if response.status_code >= 400:
                    # Maybe a field name is wrong — caller may retry with fewer fields.
                    raise requests.HTTPError(
                        f"HTTP {response.status_code}: {response.text[:500]}",
                        response=response,
                    )

                self.consecutive_failures = 0
                return response.json()

            except requests.Timeout:
                log(
                    f"  Timeout. Plain language: the server was too slow. "
                    f"Retry {attempt}/{max_tries}."
                )
                time.sleep(delay)
                delay *= 2
            except requests.HTTPError:
                raise
            except requests.RequestException as exc:
                log(f"  Network error: {exc}. Retry {attempt}/{max_tries}.")
                time.sleep(delay)
                delay *= 2

        self.consecutive_failures += 1
        self.errors.append(f"Gave up after retries: {url} {params}")
        log("  Stopped retrying this request.")
        if self.consecutive_failures >= 5:
            log("  Five requests in a row failed. Stopping so we do not hammer the free API.")
        return None

    def _retry_wait_seconds(self, response: requests.Response, fallback: float) -> float:
        """README uses X-RateLimit-Reset; also honour Retry-After if present."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                pass
        reset = response.headers.get("X-RateLimit-Reset")
        if reset:
            try:
                return max(float(reset), 1.0)
            except ValueError:
                pass
        return fallback

    def should_stop(self) -> bool:
        return self.consecutive_failures >= 5


def extract_post_list(payload: Any) -> list[dict[str, Any]]:
    """Arctic Shift usually returns {\"data\": [...]} but we accept a bare list too."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data", payload.get("results", []))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and "children" in data:
            rows = []
            for child in data["children"]:
                if isinstance(child, dict):
                    rows.append(child.get("data", child))
            return rows
    return []


def flatten_comment_tree(payload: Any) -> list[dict[str, Any]]:
    """Walk the comment tree. Skip Reddit-style {\"kind\": \"more\"} stubs (collapsed IDs)."""
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        kind = node.get("kind")
        if kind == "more":
            return
        # Listing wrapper: {"kind": "Listing", "data": {"children": [...]}}
        # or a bare {"data": [ comments ]}.
        inner = node.get("data")
        if kind in (None, "Listing") and isinstance(inner, list):
            walk(inner)
            return
        if kind == "Listing" and isinstance(inner, dict):
            walk(inner.get("children"))
            return
        data = inner if isinstance(inner, dict) else node
        if not isinstance(data, dict):
            return
        # A real comment has a body (or empty body we will filter later) and an id.
        if "body" in data and "id" in data:
            found.append(data)
            walk(data.get("replies"))
            walk(data.get("children"))
            return
        for value in node.values():
            if isinstance(value, (list, dict)):
                walk(value)

    walk(payload)
    return found


def search_posts(
    client: ArcticClient,
    subreddit: str,
    query: str,
    limit: int,
    pages: int,
) -> list[dict[str, Any]]:
    """Newest-first search. Extra pages use `before` = created_utc of the last row (README)."""
    all_posts: list[dict[str, Any]] = []
    before: str | None = None
    fields = POST_FIELDS

    for page in range(1, pages + 1):
        if client.should_stop():
            break
        params: dict[str, Any] = {
            "subreddit": subreddit,
            "query": query,
            "sort": "desc",
            "limit": limit,
            "fields": fields,
        }
        if before:
            params["before"] = before

        log(f"Searching r/{subreddit} query={query!r} page={page}/{pages}")
        try:
            payload = client.get("/api/posts/search", params)
        except requests.HTTPError as exc:
            text = str(exc)
            log(f"  API error: {text}")
            # README selectable fields do not include permalink; drop it and retry.
            if "not a valid field" in text.lower() or (
                "permalink" in fields and "400" in text
            ):
                log(
                    "  Plain language: a requested field was rejected. "
                    "Retrying with README-only fields (no permalink)."
                )
                fields = POST_FIELDS
                params["fields"] = fields
                try:
                    payload = client.get("/api/posts/search", params)
                except requests.HTTPError as exc2:
                    log(f"  Still failing after dropping permalink: {exc2}")
                    client.consecutive_failures += 1
                    client.errors.append(str(exc2))
                    break
            else:
                client.consecutive_failures += 1
                client.errors.append(text)
                break

        if payload is None:
            break

        page_posts = extract_post_list(payload)
        log(f"  Got {len(page_posts)} posts on this page.")
        if not page_posts:
            break
        all_posts.extend(page_posts)
        last = page_posts[-1]
        before = last.get("created_utc")
        if before is None:
            break
        # Next page: older than the last post we just saw (sort=desc).
        before = to_iso8601(before) or str(before)

    return all_posts


def fetch_comment_tree(client: ArcticClient, post_id: str, limit: int) -> list[dict[str, Any]]:
    link_id = post_id if str(post_id).startswith("t3_") else f"t3_{post_id}"
    # README comments/tree table has no `fields`. Verified HTTP 400:
    # {"error": "Unknown query parameter: 'fields'"}.
    params: dict[str, Any] = {"link_id": link_id, "limit": limit}
    log(f"Fetching comment tree for {link_id} (limit={limit})")
    try:
        payload = client.get("/api/comments/tree", params)
    except requests.HTTPError as exc:
        text = str(exc)
        log(f"  API error: {text}")
        log(
            "  Plain language: /api/comments/tree may not support `fields` (not in the README table). "
            "Retrying without fields, then stripping any author keys."
        )
        params.pop("fields", None)
        try:
            payload = client.get("/api/comments/tree", params)
        except requests.HTTPError as exc2:
            log(f"  Comment tree still failed: {exc2}")
            client.errors.append(str(exc2))
            client.consecutive_failures += 1
            return []
    if payload is None:
        return []
    return flatten_comment_tree(payload)


def cmd_discover(args: argparse.Namespace) -> int:
    page = check_status()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    client = ArcticClient()

    if args.test:
        subreddits = ["googlephotos"]
        queries = [DEFAULT_QUERIES[0]]
        limit = 20
        pages = 1
        log("TEST MODE: r/googlephotos, one query, up to 20 posts, 1 page.")
    else:
        subreddits = [args.subreddit] if args.subreddit else DEFAULT_SUBREDDITS
        queries = [args.query] if args.query else DEFAULT_QUERIES
        limit = 100
        pages = args.pages

    posts_found = 0
    skipped = 0
    by_id: dict[str, dict[str, Any]] = {}

    for subreddit in subreddits:
        if client.should_stop():
            log("Stopping discover because too many requests failed.")
            break
        for query in queries:
            if client.should_stop():
                log("Stopping discover because too many requests failed.")
                break
            rows = search_posts(client, subreddit, query, limit=limit, pages=pages)
            posts_found += len(rows)
            for post in rows:
                post_id = str(post.get("id") or "").removeprefix("t3_")
                title = post.get("title") or ""
                selftext = post.get("selftext") or ""
                if not post_id:
                    skipped += 1
                    continue
                if is_blank_or_removed(title) and is_blank_or_removed(selftext):
                    skipped += 1
                    continue
                if post_id in by_id:
                    existing = by_id[post_id]["search_queries"]
                    if query not in existing:
                        existing.append(query)
                    continue
                by_id[post_id] = {
                    "post": post,
                    "search_queries": [query],
                }

    duplicates_removed = posts_found - skipped - len(by_id)
    if duplicates_removed < 0:
        duplicates_removed = 0

    previous_rows = count_data_rows(CANDIDATES_CSV)
    status, preserve = decide_reddit_status(
        status_page=page["status_page"],
        rows_this_run=len(by_id),
        previous_rows=previous_rows,
        error_count=len(client.errors),
        stopped=client.should_stop(),
    )
    if preserve:
        log(
            f"Keeping existing {CANDIDATES_CSV.name} ({previous_rows} rows). "
            f"This run status is {status} and would have written {len(by_id)}."
        )
    else:
        previous_selected: dict[str, str] = {}
        if CANDIDATES_CSV.exists():
            with CANDIDATES_CSV.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    mark = (row.get("selected") or "").strip()
                    if mark:
                        previous_selected[row.get("post_id") or ""] = mark
        fieldnames = [
            "post_id",
            "subreddit",
            "created_date",
            "title",
            "selftext_preview",
            "score",
            "num_comments",
            "url",
            "search_queries",
            "selected",
        ]
        with CANDIDATES_CSV.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for post_id, bundle in by_id.items():
                post = bundle["post"]
                subreddit = post.get("subreddit") or ""
                selftext = post.get("selftext") or ""
                writer.writerow(
                    {
                        "post_id": post_id,
                        "subreddit": subreddit,
                        "created_date": to_iso8601(post.get("created_utc")),
                        "title": post.get("title") or "",
                        "selftext_preview": selftext[:300],
                        "score": post.get("score", ""),
                        "num_comments": post.get("num_comments", ""),
                        "url": post_url(subreddit, post_id, post.get("permalink")),
                        "search_queries": " | ".join(bundle["search_queries"]),
                        "selected": previous_selected.get(post_id, ""),
                    }
                )

    log("")
    log("=== discover summary ===")
    log(f"Posts found (raw hits): {posts_found}")
    log(f"Duplicates removed: {duplicates_removed}")
    log(f"Skipped empty/deleted/removed: {skipped}")
    log(f"Unique candidates written: {previous_rows if preserve else len(by_id)}")
    log(f"Comments saved: 0 (discover does not fetch comments)")
    log(f"Errors: {len(client.errors)}")
    for err in client.errors:
        log(f"  - {err}")
    log(f"Discover status: {status}")
    if not preserve:
        log(f"Saved: {CANDIDATES_CSV}")
    write_harvest_status(
        {
            "status_page": page,
            "discover": {
                "status": status,
                "unique_candidates": previous_rows if preserve else len(by_id),
                "raw_hits": posts_found,
                "errors": client.errors,
                "preserved_previous": preserve,
                "stopped_after_consecutive_failures": client.should_stop(),
            },
        }
    )
    return 2 if status == "blocked" else (1 if status == "error" else 0)


def cmd_collect(args: argparse.Namespace) -> int:
    page = check_status()
    if not CANDIDATES_CSV.exists():
        log(f"Missing {CANDIDATES_CSV}. Run discover first.")
        write_harvest_status(
            {
                "status_page": page,
                "collect": {
                    "status": "error",
                    "rows": 0,
                    "errors": [f"Missing {CANDIDATES_CSV.name}"],
                    "note": "Collect did not run. This is not a finding about users.",
                },
            }
        )
        return 1

    with CANDIDATES_CSV.open(encoding="utf-8", newline="") as handle:
        candidates = list(csv.DictReader(handle))

    if args.all_with_comments_over is not None:
        threshold = args.all_with_comments_over
        selected = []
        for row in candidates:
            try:
                n = int(row.get("num_comments") or 0)
            except ValueError:
                n = 0
            if n >= threshold:
                selected.append(row)
        log(f"Selecting {len(selected)} posts with num_comments >= {threshold}.")
    else:
        selected = [row for row in candidates if (row.get("selected") or "").strip().lower() == "y"]
        log(f"Selecting {len(selected)} posts marked selected=y.")

    if not selected:
        log("No posts selected. Mark selected=y in the CSV, or pass --all-with-comments-over N.")
        return 1

    client = ArcticClient()
    seen_ids: set[str] = set()
    comments_saved = 0
    posts_saved = 0
    skipped = 0
    fieldnames = [
        "source",
        "id",
        "date",
        "text",
        "url",
        "rating",
        "country_or_subreddit",
        "type",
        "parent_post_id",
        "search_queries",
    ]
    collected_rows: list[dict[str, Any]] = []

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for row in selected:
        if client.should_stop():
            log("Stopping collect because too many requests failed.")
            break
        post_id = (row.get("post_id") or "").removeprefix("t3_")
        if not post_id or post_id in seen_ids:
            continue
        seen_ids.add(post_id)
        title = row.get("title") or ""
        selftext = row.get("selftext_preview") or ""
        full_selftext = _load_full_selftext(post_id) or selftext
        text = title if not full_selftext else f"{title}\n{full_selftext}".strip()
        url = row.get("url") or post_url(row.get("subreddit") or "", post_id)
        collected_rows.append(
            {
                "source": "reddit",
                "id": post_id,
                "date": row.get("created_date") or "",
                "text": text,
                "url": url,
                "rating": row.get("score") or "",
                "country_or_subreddit": row.get("subreddit") or "",
                "type": "reddit_post",
                "parent_post_id": "",
                "search_queries": row.get("search_queries") or "",
            }
        )
        posts_saved += 1

        comments = fetch_comment_tree(client, post_id, limit=args.max_comments)
        for comment in comments:
            cid = str(comment.get("id") or "").removeprefix("t1_")
            body = comment.get("body") or ""
            if not cid or cid in seen_ids:
                skipped += 1
                continue
            if is_blank_or_removed(body):
                skipped += 1
                continue
            seen_ids.add(cid)
            collected_rows.append(
                {
                    "source": "reddit",
                    "id": cid,
                    "date": to_iso8601(comment.get("created_utc")),
                    "text": body,
                    "url": url,
                    "rating": comment.get("score", ""),
                    "country_or_subreddit": row.get("subreddit") or "",
                    "type": "reddit_comment",
                    "parent_post_id": post_id,
                    "search_queries": row.get("search_queries") or "",
                }
            )
            comments_saved += 1

    previous_rows = count_data_rows(COLLECTED_CSV)
    status, preserve = decide_reddit_status(
        status_page=page["status_page"],
        rows_this_run=len(collected_rows),
        previous_rows=previous_rows,
        error_count=len(client.errors),
        stopped=client.should_stop(),
    )
    if preserve:
        log(
            f"Keeping existing {COLLECTED_CSV.name} ({previous_rows} rows). "
            f"This run status is {status} and would have written {len(collected_rows)}."
        )
    else:
        with COLLECTED_CSV.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(collected_rows)

    log("")
    log("=== collect summary ===")
    log(f"Posts found (selected): {len(selected)}")
    log(f"Posts saved: {posts_saved}")
    log(f"Duplicates removed / skipped ids: {skipped}")
    log(f"Skipped empty/deleted comments counted in skipped above.")
    log(f"Comments saved: {comments_saved}")
    log(f"Errors: {len(client.errors)}")
    for err in client.errors:
        log(f"  - {err}")
    log(f"Collect status: {status}")
    if not preserve:
        log(f"Saved: {COLLECTED_CSV}")
    write_harvest_status(
        {
            "status_page": page,
            "collect": {
                "status": status,
                "rows": previous_rows if preserve else len(collected_rows),
                "posts_saved": posts_saved,
                "comments_saved": comments_saved,
                "errors": client.errors,
                "preserved_previous": preserve,
                "stopped_after_consecutive_failures": client.should_stop(),
            },
        }
    )
    return 2 if status == "blocked" else (1 if status == "error" else 0)


def _load_full_selftext(post_id: str) -> str | None:
    """If a cached search JSON contains this post, reuse full selftext (no extra request)."""
    if not CACHE_DIR.exists():
        return None
    needle = post_id.removeprefix("t3_")
    for path in CACHE_DIR.glob("api_posts_search*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for post in extract_post_list(payload):
            pid = str(post.get("id") or "").removeprefix("t3_")
            if pid == needle:
                return post.get("selftext") or ""
    return None


def cmd_status(_args: argparse.Namespace) -> int:
    """Record harvest status from the status page plus files already on disk. No search."""
    page = check_status()
    candidates = count_data_rows(CANDIDATES_CSV)
    collected = count_data_rows(COLLECTED_CSV)
    posts = comments = 0
    if COLLECTED_CSV.exists():
        with COLLECTED_CSV.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("type") == "reddit_comment":
                    comments += 1
                elif row.get("type") == "reddit_post":
                    posts += 1
    if candidates == 0 and collected == 0 and page["status_page"] in {"down", "unreachable"}:
        discover_status = "blocked"
        collect_status = "blocked"
    elif candidates == 0 and collected == 0:
        discover_status = "empty"
        collect_status = "empty"
    else:
        discover_status = "ok" if candidates else "empty"
        collect_status = "ok" if collected else "empty"
    if page["status_page"] != "up" and (candidates or collected):
        log(
            "Status page is not up, but a previous harvest is on disk. "
            "Keeping those rows. " + NOT_A_FINDING
        )
    write_harvest_status(
        {
            "status_page": page,
            "rows_on_disk": candidates + collected,
            "discover": {
                "status": discover_status,
                "unique_candidates": candidates,
                "preserved_previous": True,
            },
            "collect": {
                "status": collect_status,
                "rows": collected,
                "posts_saved": posts,
                "comments_saved": comments,
                "preserved_previous": True,
            },
        }
    )
    overall = "blocked" if discover_status == "blocked" else discover_status
    if collect_status == "blocked":
        overall = "blocked"
    return 2 if overall == "blocked" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch Reddit posts/comments from Arctic Shift (no Reddit API key)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="Search posts and write reddit_candidates.csv")
    discover.add_argument("--test", action="store_true", help="1 subreddit, 1 query, 20 posts")
    discover.add_argument("--subreddit", help="Only this subreddit")
    discover.add_argument("--query", help="Only this keyword query")
    discover.add_argument("--pages", type=int, default=1, help="Pages of up to 100 posts (default 1)")
    discover.set_defaults(func=cmd_discover)

    collect = sub.add_parser("collect", help="Fetch comments for selected candidate posts")
    collect.add_argument(
        "--all-with-comments-over",
        type=int,
        metavar="N",
        dest="all_with_comments_over",
        help="Select posts with num_comments >= N instead of selected=y",
    )
    collect.add_argument(
        "--max-comments",
        type=int,
        default=50,
        help="limit for /api/comments/tree (default 50)",
    )
    collect.set_defaults(func=cmd_collect)

    status = sub.add_parser(
        "status",
        help="Record Arctic Shift harvest status without fetching posts",
    )
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
