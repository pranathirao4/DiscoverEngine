"""Three Streamlit pages: Overview, Evidence (includes Ask), Findings."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PROCESSED = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
HARVEST = PROCESSED / "harvest_status"
CORPUS_ALL = PROCESSED / "corpus_all.csv"
HARVEST_STATUS_FILES = (
    ("Play Store", HARVEST / "play_harvest_status.json", RAW / "play_harvest_status.json"),
    ("Arctic Shift", HARVEST / "reddit_arctic_harvest_status.json", RAW / "reddit_arctic_harvest_status.json"),
    ("Provided JSON", HARVEST / "reddit_provided_import_status.json", RAW / "reddit_provided_import_status.json"),
)
SLICE_CSV = PROCESSED / "thin_slice_labeled.csv"
SLICE_COUNTS = PROCESSED / "thin_slice_counts.json"
LABELED_CSV = PROCESSED / "corpus_labeled.csv"
RELEVANT_CSV = PROCESSED / "corpus_relevant.csv"
GATE_COUNTS = PROCESSED / "gate_counts.json"
GO_NO_GO = PROCESSED / "go_nogo.json"
URL_REPORT = PROCESSED / "url_verification.json"
EVIDENCE_COLUMNS = [
    "id",
    "source",
    "type",
    "relevance",
    "confidence",
    "failure_type",
    "photo_type",
    "memory_anchors",
    "forgotten_anchors",
    "retrieval_behaviors",
    "quotes",
    "url",
    "text",
]


def _existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def page_overview() -> None:
    st.title("Overview")
    st.caption("Harvest health and in-scope counts. Not average stars. No success-rate claims.")
    st.subheader("Harvest status")
    for label, *candidates in HARVEST_STATUS_FILES:
        path = _existing(*candidates)
        if path is None:
            st.warning(f"{label}: no status recorded yet.")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        status = payload.get("status") or "unknown"
        st.write(f"**{label}:** {status}")
        if status in {"blocked", "error", "empty"}:
            st.error(
                payload.get("interpretation")
                or "This harvest did not complete. That is not evidence that users have no problem."
            )
        elif payload.get("interpretation") and payload.get("kept") == 0:
            st.info(payload["interpretation"])
    corpus = _read(CORPUS_ALL)
    st.metric("corpus_all rows", len(corpus))
    if corpus:
        st.bar_chart(dict(Counter(row.get("source") or "unknown" for row in corpus)))
        st.bar_chart(dict(Counter(row.get("type") or "unknown" for row in corpus)))
    if GATE_COUNTS.exists():
        counts = json.loads(GATE_COUNTS.read_text(encoding="utf-8"))
        st.subheader("Failure types")
        st.caption("Counts of LLM failure-type labels. Not a success rate and not average stars.")
        failure = {key: value for key, value in (counts.get("failure_type") or {}).items() if key}
        if failure:
            st.bar_chart(failure)
        st.write(
            f"In-scope unique ids: {counts.get('unique_in_scope', 0)} "
            f"of {counts.get('n', 0)} gated rows."
        )
    elif SLICE_COUNTS.exists():
        counts = json.loads(SLICE_COUNTS.read_text(encoding="utf-8"))
        st.subheader("Thin-slice gate")
        st.json(counts)
    else:
        st.info("Full-corpus counts appear here after `python src/cli.py gate`.")
    st.subheader("Go / no-go")
    if GO_NO_GO.exists():
        decision = json.loads(GO_NO_GO.read_text(encoding="utf-8"))
        label = decision.get("decision") or "incomplete"
        st.write(
            f"**{label}** — {decision.get('unique_in_scope')} unique in-scope ids "
            f"(threshold {decision.get('threshold')})."
        )
        if label == "incomplete":
            st.warning(decision.get("note") or "The full gate has not finished.")
        else:
            st.caption(decision.get("note") or "")
    else:
        st.write("Recorded when `python src/cli.py gate` finishes the full corpus. Threshold is about 150 unique in-scope ids.")


def page_evidence() -> None:
    st.title("Evidence")
    st.caption("Hand-check ids, quotes, relevance, confidence. Ask is over this corpus only.")

    st.subheader("Ask the corpus")
    st.caption(
        "PM questions about incomplete-memory retrieval in the harvested evidence. "
        "Not a Google Photos help bot. Groq answers; BGE retrieves; citations required."
    )
    question = st.text_area(
        "Question",
        placeholder="Example: What do people say they remember when they cannot find a photo?",
        height=80,
    )
    if st.button("Ask", type="primary"):
        from ask import ask as ask_corpus
        from common import load_env

        load_env()
        with st.spinner("Retrieving evidence and asking Groq…"):
            try:
                result = ask_corpus(question)
            except Exception as exc:
                message = str(exc)
                if "GROQ_API_KEY" in message:
                    st.error(
                        "Ask needs GROQ_API_KEY. Locally it belongs in `env`. "
                        "On Streamlit Community Cloud, add it under Settings → Secrets."
                    )
                else:
                    st.error("Ask failed. The corpus answer was not produced.")
                result = None
        if result is not None and result.get("enough_evidence"):
            st.success(result.get("answer") or "")
        elif result is not None:
            st.warning(result.get("answer") or "Not enough evidence.")
        cites = (result or {}).get("citation_ids") or []
        if cites:
            st.write("Citations: " + ", ".join(cites))
        hits = (result or {}).get("hits") or []
        if hits:
            st.dataframe(
                [
                    {
                        "id": h.get("id"),
                        "score": h.get("score"),
                        "relevance": h.get("relevance"),
                        "failure_type": h.get("failure_type"),
                        "url": h.get("url"),
                        "text": (h.get("text") or "")[:280],
                    }
                    for h in hits
                ],
                use_container_width=True,
            )
        if result and result.get("limitations"):
            st.caption(result["limitations"])

    st.divider()
    rows = _read(RELEVANT_CSV) or _read(LABELED_CSV) or _read(SLICE_CSV) or _read(CORPUS_ALL)
    if not rows:
        st.warning("No corpus yet. Run compile-sources, harvests, and write-corpus.")
        return
    st.caption("Anchors and confidence are on each row. Low confidence stays in the corpus.")
    sources = sorted({row.get("source") or "" for row in rows})
    source = st.multiselect("source", sources, default=sources)
    filtered = [row for row in rows if row.get("source") in source]
    if "relevance" in (rows[0] or {}):
        rels = sorted({row.get("relevance") or "" for row in rows})
        chosen = st.multiselect("relevance", rels, default=["in_scope"] if "in_scope" in rels else rels)
        filtered = [row for row in filtered if row.get("relevance") in chosen]
    if "confidence" in (rows[0] or {}):
        confs = sorted({row.get("confidence") or "" for row in rows})
        chosen_conf = st.multiselect("confidence", confs, default=confs)
        filtered = [row for row in filtered if row.get("confidence") in chosen_conf]
    st.write(f"{len(filtered)} rows")
    columns = [name for name in EVIDENCE_COLUMNS if rows and name in rows[0]]
    st.dataframe([{key: row.get(key, "") for key in columns} for row in filtered[:200]], use_container_width=True)


def page_findings() -> None:
    st.title("Findings")
    st.caption("Opportunity compare lands in Phase 4. Weights will be explained here.")
    counts_path = GATE_COUNTS if GATE_COUNTS.exists() else SLICE_COUNTS
    if counts_path.exists():
        counts = json.loads(counts_path.read_text(encoding="utf-8"))
        st.write("Failure types so far (not a ranking, not a success rate). Compare lands in Phase 4.")
        st.json(counts.get("failure_type") or {})
    else:
        st.info("No labeled corpus yet.")
    if URL_REPORT.exists():
        st.subheader("URL verification")
        st.json(json.loads(URL_REPORT.read_text(encoding="utf-8")))


st.set_page_config(page_title="AI Discovery", layout="wide")
page = st.navigation(
    [
        st.Page(page_overview, title="Overview", default=True),
        st.Page(page_evidence, title="Evidence"),
        st.Page(page_findings, title="Findings"),
    ]
)
page.run()
