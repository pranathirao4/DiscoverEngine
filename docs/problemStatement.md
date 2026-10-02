# Problem statement: AI-powered discovery for incomplete-memory photo retrieval

## How to use this file

Read this file and [`docs/sources.md`](sources.md) first before changing the engine, prompts, taxonomy, or harvest list. Ask before changing working definitions, evidence standards, or constraints. Fetch URLs live only in `docs/sources.md`.

This document is the working brief for **AI_Discovery**. It captures the product context, the problem to solve, and the first deliverable: an AI-powered discovery engine that turns public user conversations about Google Photos retrieval into comparable opportunity areas.

Source: `docs/problemStatement.txt`.

---

## Role and setting

You are a Product Manager on the **Core Experience** team at **Google Photos**.

Over years of usage, people accumulate thousands of photos, videos, screenshots, documents, and other visual memories in Google Photos.

Search works well when the user already knows what they are looking for. Retrieval fails when memory is incomplete: the user is sure the photo exists, but cannot name the query that would find it.

---

## The user problem

A person may remember a scene, not a search term. For example:

- “That small café we went to during our Goa trip.”
- “The picture of the medicine I took when I was sick last year.”

They know the photo exists. They often do **not** remember:

- when it was taken
- where it was taken
- which album it belongs to
- the exact words needed to search for it

The product gap is not “search is weak in general.” It is **failed retrieval under incomplete memory**.

---

## Strategic goal

Increase the percentage of users who successfully retrieve a photo they remember but cannot precisely describe when they start searching.

---

## What this project is (and is not)

| In scope                                              | Out of scope (for this phase)                                      |
| :---------------------------------------------------- | :----------------------------------------------------------------- |
| How people remember old visual information            | Generic search-quality improvements                                |
| Where the current retrieval experience breaks down    | Shipping a new Photos search UI before evidence exists             |
| Identifying opportunity areas with evidence from real users | Sentiment summaries that do not distinguish retrieval problems |

The immediate task is **not** to propose a solution first. The immediate task is to **understand the problem at scale**, then identify an opportunity that can meaningfully improve successful retrieval.

---

## Part 1: Build an AI-powered discovery engine

Before proposing any product solution, build a system that analyzes user feedback and conversations about photo retrieval at scale.

### Allowed stack

Use any AI-native stack, including:

- Claude, GPTs, agents, workflows, RAG
- n8n, Zapier, Perplexity
- any other AI-native tooling of choice

The implementation stack for this repo is specified under **Constraints** (Python, Groq API, Streamlit, built in Cursor).

### Public evidence sources

Analyze publicly available sources such as:

- Google Play Store reviews
- App Store reviews
- Reddit discussions
- Google Photos community / support discussions
- social media conversations
- YouTube comments
- forums and other relevant public discussions

To **fetch** this data, use the listing, search, thread, and video URLs in [`docs/sources.md`](sources.md). Do not invent additional store or discussion links unless they are added there.

### Questions the engine should help answer

These are sample questions, not a closed list:

1. What kinds of old photos do users struggle to retrieve?
2. What information do people actually remember about a photo?
3. What information have they forgotten?
4. How do users formulate searches when their memory is incomplete?

### Quality bar

The workflow must go **beyond** summarizing reviews or performing sentiment analysis.

It should enable identification and comparison of **different retrieval problems and opportunity areas**, each grounded in evidence from real users.

---

## Project context for later work

Use this brief as the north star for design, data collection, clustering, and opportunity ranking.

- **User job:** Find a photo I know I have, using only the fragments I still remember.
- **Failure mode:** The library is large; memory is partial; search requires more precision than the user can provide.
- **Success signal (product):** Higher rate of successful retrieval for “I remember it, I cannot describe it precisely.”
- **Success signal (discovery engine):** Distinct retrieval-problem types, compared with evidence, not a single mixed sentiment dump.

This document should stay aligned with `docs/problemStatement.txt`. Update both if the brief changes.

---

## Working definitions

- **Incomplete-memory retrieval:** the user believes a specific photo/video/screenshot exists and tries to find it, but cannot supply a precise query (name, date, place, album, exact keyword). Counts: "I remember it but don't know what to search." Does not count: pure bugs (photo missing because of sync or deletion), storage/pricing complaints, or cases where the user knew exactly what to type and the app failed.
- **Memory anchors (what users may still remember):** person, place, event/occasion, rough time, purpose/context (why it was taken), emotion, visual appearance, photo type (screenshot, document, receipt, medical, travel, kids).
- **Forgotten anchors:** exact date, location name, album, keyword/filename.
- **Retrieval behaviors:** keyword trial and error, scrolling the timeline, searching by person, searching by place, asking others or other apps, giving up.
- **Confidence label:** each analyzed item gets high / medium / low confidence of being a true incomplete-memory case, so broad evidence is kept but weighted.

## Starting hypotheses on failure types (to test, extend, or reject)

Not indexed / not found, wrong results, too many results, user cannot express the query, date or location unknown, photo type mismatch (e.g. screenshot vs camera photo), search by purpose or context unsupported. These are hypotheses only. The data may add new types or reject these.

## Evidence standards

- Every finding cites item ids and short quotes, with counts and the number of sources it appears in.
- Findings supported by fewer than ~5 items are labeled "weak signal".
- Public data shows failure stories and workarounds, not rates. Never claim a success-rate impact.
- Known biases: frustrated users are over-represented; most Play Store reviews are about storage and pricing; few users describe what they remember; the first Reddit export was mostly off-topic and needs scoped re-runs.

## Constraints

- Stack: Python, Groq API, Streamlit, built in Cursor.
- Common schema for every source: source, id, date, text, url, rating, country_or_subreddit, type.
- Privacy: drop or hash usernames and author ids; store only text, date, source, URL; exclude sensitive or unrelated subreddits (medical, mental health) from analysis.
- Use only sources listed in docs/sources.md. Add a source there before using it.

## Part 1 done when

Pipeline diagram; extraction schema and prompts; taxonomy of memory anchors and failure types; findings comparing problem types with quotes and counts; prioritization rationale; limitations section.
