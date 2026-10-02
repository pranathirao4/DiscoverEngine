"""Phase 2 label rules that must hold without a live model call."""

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from common import load_taxonomy  # noqa: E402
from label import (  # noqa: E402
    coerce_extract,
    finalize_label,
    gate_item,
    is_generic_search_only,
    quotes_in_text,
)


def test_quotes_must_be_substrings():
    kept = quotes_in_text(["exact words", "paraphrased cafe"], "I only wrote exact words here")
    assert kept == ["exact words"]


def test_generic_search_sucks_is_other_and_low():
    assert is_generic_search_only("Search sucks. Google Photos search is useless.")
    row = finalize_label(
        {
            "text": "Search sucks. Google Photos search is useless.",
            "relevance": "in_scope",
            "confidence": "high",
            "failure_type": "cannot_express_query",
            "exclude_reason": "",
            "rationale": "",
        }
    )
    assert row["relevance"] in {"adjacent", "out_of_scope"}
    assert row["failure_type"] == "other"
    assert row["confidence"] == "low"


def test_low_confidence_in_scope_is_kept():
    row = finalize_label(
        {
            "text": "I remember the trip but forgot the date in Google Photos.",
            "relevance": "in_scope",
            "confidence": "low",
            "failure_type": "date_or_location_unknown",
            "exclude_reason": "",
            "rationale": "",
        }
    )
    assert row["relevance"] == "in_scope"
    assert row["confidence"] == "low"


def test_paraphrased_quote_is_dropped():
    tax = load_taxonomy()
    rer = coerce_extract(
        {
            "failure_type": "cannot_express_query",
            "photo_type": "travel",
            "memory_anchors": ["place"],
            "forgotten_anchors": ["exact_date"],
            "retrieval_behaviors": ["keyword_trial_and_error"],
            "quotes": ["a café in Goa that the user remembers"],
        },
        tax,
        "I cannot find the café photo from Goa.",
    )
    assert rer["quotes"] == []
    assert rer["photo_type"] == "travel"


def test_unknown_enum_is_not_stored_as_free_text():
    tax = load_taxonomy()
    rer = coerce_extract(
        {"failure_type": "made_up_type", "photo_type": "selfie", "memory_anchors": ["vibes"], "quotes": []},
        tax,
        "text",
    )
    assert rer["failure_type"] == "other"
    assert rer["photo_type"] == ""
    assert rer["memory_anchors"] == []


def test_sensitive_subreddit_skips_the_model():
    class Boom:
        model_id = "test"
        api_key = "present"

        def complete_json(self, **kwargs):
            raise AssertionError("Groq must not see a medical subreddit")

    tax = load_taxonomy()
    row = gate_item(
        Boom(),
        {
            "id": "med-1",
            "source": "reddit",
            "type": "reddit_post",
            "text": "I cannot find a photo.",
            "country_or_subreddit": "depression",
            "date": "",
            "url": "",
            "rating": "",
            "parent_post_id": "",
            "search_queries": "",
        },
        tax,
    )
    assert row["relevance"] == "out_of_scope"
    assert row["exclude_reason"] == "medical_or_mental_health_subreddit"


def test_relevant_csv_rule_drops_out_of_scope():
    rows = [
        {"id": "a", "relevance": "in_scope", "confidence": "low"},
        {"id": "b", "relevance": "out_of_scope", "confidence": "high"},
        {"id": "c", "relevance": "adjacent", "confidence": "medium"},
    ]
    relevant = [row for row in rows if row["relevance"] == "in_scope"]
    assert [row["id"] for row in relevant] == ["a"]
    assert json.dumps(relevant)
