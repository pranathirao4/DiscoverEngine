# Edge cases and corner scenarios

Catalog of failure modes, boundary labels, and “do not do this” cases for the discovery engine.

Sources of truth: [`Architecture.md`](Architecture.md), [`implementation-plan.md`](implementation-plan.md), [`problemStatement.md`](problemStatement.md), [`sources.md`](sources.md). Ask before changing working definitions.

**How to use:** each row is a test or a gate. Expected behavior is what jobs, gold sets, Overview empty states, and Ask must do. Empty harvests must never be shown as “users do not have this problem.”

**Note:** Phase 1 ingest (Play + Arctic Shift + provided JSON) is already in the repo. This file is still the checklist for auditing that ingest and for Phases 2–5.

---

## 1. Scope and definitions (must not leak)

Incomplete-memory retrieval: the user believes a specific photo/video/screenshot **exists**, tries to find it, and **cannot supply a precise query**.

| ID | Scenario | Expected |
| --- | --- | --- |
| DEF-01 | “Search sucks” with no memory story | `out_of_scope` or `adjacent`; if extracted, `failure_type=other` and `confidence=low` |
| DEF-02 | User typed the exact name/date/filename and search failed | `precise_query_failed` → not incomplete-memory (`adjacent` or `out_of_scope`) |
| DEF-03 | Photo missing because of sync, backup, deletion, or “not showing after restore” only | `sync_or_deletion_bug` / existence-doubt; **out of incomplete-memory** unless they also cannot formulate a query |
| DEF-04 | Storage quota, pricing, 15 GB, backup quality | `storage_quota_only`; keep in `corpus_all.csv`, never in `corpus_relevant.csv` |
| DEF-05 | Editor, Magic Eraser, crash, new tab UI with no find-story | `editor_feature` / `crash_bug` / out of scope |
| DEF-06 | Café / Goa trip remembered, date/album forgotten | `in_scope`; photo_type `travel`; memory `place` / `event_occasion`; forgotten `exact_date` and/or `location_name` |
| DEF-07 | Medicine when sick, cannot find the picture | `in_scope`; photo_type `medical` or `document` (gold), not invented extra story |
| DEF-08 | Screenshot of a chat/receipt they remember the *look* of, not the filename | `in_scope`; `photo_type=screenshot` or `receipt`; forgotten `keyword_filename` |
| DEF-09 | Face/person is the only cue | `in_scope` if they cannot name a precise query; behavior `search_by_person` |
| DEF-10 | Find-to-delete old photos (triage), not find-to-relive | May be `adjacent`; do not mix with incomplete-memory find-one without a flag |
| DEF-11 | Not Google Photos (Samsung gallery, iCloud, PixHunt ad, generic “Reddit find this image”) | Drop or `not_google_photos` / out of scope |
| DEF-12 | GooglePixel / AndroidQuestions post about camera or Messages, not Photos search | Exclude via lexical/gate; do not count as Photos retrieval |
| DEF-13 | Brief’s product success-rate goal vs engine output | Engine **never** claims a retrieval-rate or conversion impact from public stories |
| DEF-14 | Sentiment-only summary | Pipeline must still be useful if sentiment is dropped; sentiment is not the rank key |
| DEF-15 | Changing memory-anchor or failure-type definitions in prompts only | Forbidden; change `taxonomy.yaml` + problem statement together, after asking |

---

## 2. Source registry and URLs (Phase 1)

| ID | Scenario | Expected |
| --- | --- | --- |
| SRC-01 | URL not in `sources.md` | Collectors must not fetch it |
| SRC-02 | Global `reddit.com/search?q=…` | Do **not** run as live global search. Take query text; run via Arctic Shift on allowed subreddits only; record `executed_via: arctic_shift` |
| SRC-03 | Subreddit-scoped search (`/r/googlephotos/search`) | Same: archive query, not scraping reddit.com |
| SRC-04 | Listed thread ID never appears in keyword `discover` | Still harvest via `comments/tree` `link_id=t3_<id>` |
| SRC-05 | Mix listing URLs, search URLs, thread URLs, video URLs in one untyped table | Data-quality bug; compiler must type each row |
| SRC-06 | Play / App Store / YouTube listing returns HTTP non-200 | Registry status `blocked` or `error`; Overview shows blocker, not zero problems |
| SRC-07 | Arctic Shift query “does not open” as a browser search page | Not a failed URL check; queries are archive-executed |
| SRC-08 | Duplicate URLs in `sources.md` | Compiler dedupes by thread id / video id |
| SRC-09 | `compile_sources` re-run | Deterministic fields (package, app id, queries, thread ids); `compiled_at` may change |

---

## 3. Ingest — Play Store (Phase 1)

| ID | Scenario | Expected |
| --- | --- | --- |
| PLAY-01 | Only 1-star harvested | Forbidden; harvest **all** star ratings |
| PLAY-02 | Developer reply present | Context only; do not treat as user memory; do not put reply text in `text` as if the user wrote it |
| PLAY-03 | `userName` / `userImage` in scraper JSON | Strip before CSV/JSON persist |
| PLAY-04 | Email in review body | Do not keep emails from signatures in processed stores |
| PLAY-05 | Duplicate `reviewId` across star batches | Dedupe by `id` |
| PLAY-06 | Empty `content` | Skip utterance |
| PLAY-07 | Scraper 403 / ToS block | `harvest_status=blocked`; do not invent reviews |
| PLAY-08 | Helpfulness / thumbs | Optional sidecar; not a success-rate |
| PLAY-09 | Mixed-language reviews | Keep; gate in Groq; do not drop solely for language unless empty |
| PLAY-10 | Storage/pricing dominate the harvest | Expected bias; Overview must not rank by average stars |

---

## 4. Ingest — Arctic Shift Reddit (Phase 1)

| ID | Scenario | Expected |
| --- | --- | --- |
| RED-01 | PRAW, official Reddit API, reddit.com HTML scrape, live Apify, PullPush | Forbidden |
| RED-02 | `fields` includes `permalink` | HTTP 400; build `https://www.reddit.com/r/{sub}/comments/{id}/` |
| RED-03 | `comments/tree` with `fields` | May 400; omit `fields`, strip `author*` client-side |
| RED-04 | Comment payload is `{data:[{kind:t1,data:{body, replies:{kind:Listing,data:{children:[]}}}}]}` | Parser must walk Listing/`children`; not only dicts with top-level `body` |
| RED-05 | `kind=more` load-more stub | Skip; do not treat as a comment |
| RED-06 | Body `[deleted]` / `[removed]` / empty | Skip; count as skipped, not as evidence |
| RED-07 | 422 “Timeout. Maybe slow down” | Retry with backoff; do not mark “no Reddit problem” |
| RED-08 | 429 / 5xx / `Retry-After` | Honour headers; 2–3s between calls; stop after 5 consecutive failures |
| RED-09 | Status page down / archive lag (recent days missing, scores 0/1) | `blocked` or notes; scores may backfill later; not a product finding |
| RED-10 | Keyword hit is a gallery promo (e.g. PixHunt) | Keep in candidates; `selected` / gate filters; expected `--test` noise |
| RED-11 | Same post hit by two queries | One candidate row; `search_queries` lists both |
| RED-12 | `selected` empty and no `--all-with-comments-over` | Collect no-ops with a clear message |
| RED-13 | Medical / mental-health subreddit in results | Exclude from analysis even if a query returned it |
| RED-14 | Cache file already exists | Never overwrite; reuse JSON |
| RED-15 | `num_comments` high but tree returns 0 after parse | Treat as parser/API bug, not “thread had no comments” until verified |
| RED-16 | Comment `id` collides with a post `id` | Unlikely; still dedupe corpus by `id`; prefix if needed |
| RED-17 | Nested replies deeper than one level | Flatten full tree up to API limit |
| RED-18 | Five consecutive request failures | Stop harvest; persist `error`/`blocked` |

---

## 5. Ingest — provided JSON and sample fakes (Phase 1)

| ID | Scenario | Expected |
| --- | --- | --- |
| JSON-01 | `data/samples/reddit_sample.json` | Schema only; **never** ingest |
| JSON-02 | `reddit_apify.json` threads in r/ask, r/findareddit, etc. | Drop unless Google Photos + incomplete-memory retrieval |
| JSON-03 | Truncated / invalid JSON (unterminated string) | Import complete objects only; status notes truncation; do not crash the pipeline |
| JSON-04 | `author`, `author_fullname`, `author_flair_*` | Strip every `author*` key |
| JSON-05 | Same `id` as Arctic Shift | Dedupe; keep one utterance |
| JSON-06 | Nested comments under `comments` / `replies` / Listing | Walk tree; apply same relevance filter per comment |
| JSON-07 | Treating the dump as a live Apify harvest | Forbidden; one-time filtered import only |

---

## 6. Normalize, identity, privacy

| ID | Scenario | Expected |
| --- | --- | --- |
| NOR-01 | Missing common-schema field | Do not write the row to processed corpus |
| NOR-02 | Reddit post `text` = title + selftext; comment = body only | No mixing developer/mod boilerplate as user text |
| NOR-03 | `rating` on Reddit | Score/ups as string or empty; not stars |
| NOR-04 | `rating` on Play | Star 1–5 |
| NOR-05 | Child thread from a listed search | Allowed only with `parent_source_url` pointing at that search |
| NOR-06 | Arbitrary subreddit crawl | Forbidden |
| NOR-07 | Re-harvest same review | Append version / pin `corpus_version`; do not silently rewrite history |
| NOR-08 | Cross-post same story on Play and Reddit | Keep both; optional `duplicate_group_id`; intensity, not a delete |
| NOR-09 | Username in SQLite or `corpus_*.csv` | Fail privacy check |
| NOR-10 | Hash author id if a join is required | Store hash only, never plaintext |
| NOR-11 | YouTube `commentId` vs transcript chunk | Transcript keyed by video id + timestamp; type `youtube_transcript_segment` |
| NOR-12 | Empty date | Allow empty `date`; do not invent timestamps |
| NOR-13 | Analyzing from raw Play/Reddit files after `corpus_relevant.csv` exists | Forbidden for findings |

---

## 7. Relevance gate and extraction (Phase 0.5 / 2)

| ID | Scenario | Expected |
| --- | --- | --- |
| GATE-01 | Lexical screen miss, true incomplete-memory | LLM gate still sees a sample of non-hits if volume allows; audit `out_of_scope` |
| GATE-02 | Lexical hit, storage-only | LLM → `out_of_scope` |
| GATE-03 | `low` confidence in_scope | **Keep**; weight later; do not drop |
| GATE-04 | Only `in_scope` + small `adjacent` sample get RER extraction | `out_of_scope` stays in `corpus_all` for false-negative audit |
| GATE-05 | Quote not a substring of `text` | Drop that quote; citation integrity test fails if it ships |
| GATE-06 | Model paraphrases inside `quotes[]` | Reject; copy verbatim |
| GATE-07 | Invented Goa café when text never says Goa | Forbidden; use `unknown` / empty anchors |
| GATE-08 | Enum not in `taxonomy.yaml` | Coerce empty / `other`; do not persist free text as enum |
| GATE-09 | Remembered vs forgotten swapped | Extraction gold fails; tag separately |
| GATE-10 | Gold: storage-only, crash, precise-query-failed, sync/deletion | Must label out/adjacent with the right `exclude_reason` |
| GATE-11 | Groq 404 unknown model | Fail clearly; do not silently call OpenAI |
| GATE-12 | Groq 429 | Retry; cache `id` + `prompt_version` + `model_id` |
| GATE-13 | Re-run same ids | Cache hit; no second Groq call |
| GATE-14 | Prompt version bump | New cache keys; re-analysis, not new ingest |
| GATE-15 | Unique in-scope ids &lt; ~150 | **No-go** for Phase 4 clustering/ranking; collect more first |
| GATE-16 | Unique in-scope ids ≥ ~150 | Record **go** |
| GATE-17 | `corpus_relevant.csv` includes `out_of_scope` | Forbidden |
| GATE-18 | Play-only thin slice bias | Note bias if Reddit mix is missing |

---

## 8. Groq vs BGE vs OpenAI

| ID | Scenario | Expected |
| --- | --- | --- |
| MOD-01 | Chat/gate/extract/ask | Groq only |
| MOD-02 | Embeddings | Local `BAAI/bge-small-en-v1.5` (or `BGE_MODEL` BAAI checkpoint) |
| MOD-03 | OpenAI API key used for chat or `text-embedding-3-*` / ada-002 | Forbidden |
| MOD-04 | Groq `nomic-embed-*` | Forbidden |
| MOD-05 | Groq model id contains `openai/` (e.g. `openai/gpt-oss-20b`) | Allowed **on Groq**; it is not the OpenAI API |
| MOD-06 | Missing `GROQ_API_KEY` | Unlabeled sample / Ask disabled with a clear error; no fake labels |
| MOD-07 | BGE download / HF unauthenticated | Local cache after first load; still not OpenAI |
| MOD-08 | Query embedding without BGE search prefix | Use configured query prefix for Ask; document embeddings without query prefix |

---

## 9. App Store and YouTube (Phase 3)

| ID | Scenario | Expected |
| --- | --- | --- |
| P3-01 | YouTube API key missing | Status `blocked`/`empty`; skip comments; do not scrape youtube.com arbitrarily |
| P3-02 | Transcript available | Secondary; creator speech is not commenter evidence unless narrating a retrieval failure |
| P3-03 | Comments on videos **not** in `sources.md` | Forbidden |
| P3-04 | App Store RSS empty | `empty`; continue; do not treat as “iOS users have no retrieval pain” |
| P3-05 | Same user story on iOS and Android | Two utterances; `source_spread` counts both sources |
| P3-06 | Need more in-scope after go/no-go fail | Extra Arctic Shift pages or listed threads; still no reddit.com scrape |

---

## 10. Findings, clustering, severity (Phase 4)

| ID | Scenario | Expected |
| --- | --- | --- |
| FND-01 | Finding with &lt; ~5 supporting ids | Label **weak signal** |
| FND-02 | Count without `source_spread` | Incomplete evidence; must show how many sources |
| FND-03 | Severity presented as success-rate impact | Forbidden |
| FND-04 | Rank by average stars or sentiment | Forbidden |
| FND-05 | Weights hidden in a model | Forbidden; show each weight on Findings; sensitivity ±25% or drop-one |
| FND-06 | Cluster label overwrites Groq `failure_type` without human merge | Forbidden |
| FND-07 | Two clusters share anchors/failure type above merge threshold | Synthesizer proposes merge, does not silently fuse cards |
| FND-08 | Hypothesis rejected by data | Record add/reject; do not keep unused codes as if proven |
| FND-09 | Counter-evidence (search already worked) | Store on the card; do not delete |
| FND-10 | Optional cluster skipped | Still valid if Groq failure types + cards exist |
| FND-11 | Compare one opportunity only | Need two+ for compare job |
| FND-12 | Structure embedding of empty RER | Do not treat as a problem type |

---

## 11. Ask / RAG and Streamlit (Phase 5 UI)

| ID | Scenario | Expected |
| --- | --- | --- |
| ASK-01 | “How do I search Google Photos?” (product help) | Not enough evidence / refuse to invent help docs |
| ASK-02 | “Find my Goa café photo in my library” | Refuse; not a find-my-photo bot; no private libraries |
| ASK-03 | Unrelated question (weather, coding) | `enough_evidence=false` |
| ASK-04 | Answer without citation ids | Invalid; ids must be from retrieved hits |
| ASK-05 | Citation id not in retrieved set | Strip |
| ASK-06 | Fourth Streamlit page for Ask | Do not add; Ask stays on Evidence |
| ASK-07 | Overview shows average stars as the hero metric | Forbidden; in-scope counts, harvest health, failure-type histogram |
| ASK-08 | Empty in-scope set | Copy: **no evidence in corpus**, never “users don’t have this problem” |
| ASK-09 | Blocked source | Surface on Overview |
| ASK-10 | Ask over unlabeled corpus | Retrieve only labeled (or later RER) rows; do not hallucinate labels |
| ASK-11 | Repeated PM question | Log to `ask_log`; may become an analysis job later |
| ASK-12 | Export without limitations / URLs on quotes | Part 1 not done |

---

## 12. Security, ethics, non-goals

| ID | Scenario | Expected |
| --- | --- | --- |
| SEC-01 | Login to Google account / index private photos | Forbidden |
| SEC-02 | `env` / `.env` committed with keys | Forbidden |
| SEC-03 | Medical/mental-health subreddit text in analysis | Exclude |
| SEC-04 | Photos product UI / Lens / Memories implementation | Out of Part 1 |
| SEC-05 | n8n/Zapier as a second corpus | Forbidden; wrappers only |
| SEC-06 | Cache never overwrite vs stale wrong JSON | Immutable raw; fix parser and re-read cache; do not mutate Arctic JSON |

---

## 13. Gold-set mapping (Architecture §12)

Hand-labeled JSONL in `tests/gold/` should cover at least:

| Gold item | Pass if |
| --- | --- |
| Storage/pricing review | `out_of_scope` + `storage_quota_only` |
| Crash / editor | `out_of_scope` |
| Precise query failed | `precise_query_failed`, not incomplete-memory |
| Sync/deletion missing photos | not in_scope unless incomplete query also present |
| Café / Goa | `travel` + remembered place/occasion |
| Medicine / sick | `medical` and/or `document` |
| Generic search sucks | `other` + `confidence=low` |
| Weak signal card | flagged when &lt; ~5 ids |
| RAG abstain | unrelated question → insufficient evidence |
| Privacy | processed files have no `author*` |

---

## 14. Phase 1 audit (if re-checking ingest)

Before treating Phase 1 as closed for analysis:

1. No `author*` in `reddit_arctic.csv`, Play CSV, provided-JSON CSV, or Arctic cache.
2. Sample JSON not in `corpus_all.csv`.
3. Provided JSON kept count may be **zero** (expected).
4. Comments exist when cache JSON has `t1` bodies (parser).
5. Listing URLs verified; query URLs marked archive-executed.
6. If Arctic Shift is down on a run, status is `blocked` on Overview.

---

## Document control

| Doc | Role |
| --- | --- |
| This file | Corner cases and expected behavior |
| `implementation-plan.md` | Build order (filename on disk; not `implementationPlan.md`) |
| `Architecture.md` | Contracts, taxonomy, jobs, QA |
| `problemStatement.md` | Definitions and evidence standards |
| `sources.md` | Allowed URLs |
