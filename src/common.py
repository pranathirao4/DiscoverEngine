"""Shared paths, env loading, taxonomy, and the common utterance schema."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
TAXONOMY_PATH = CONFIG_DIR / "taxonomy.yaml"
SOURCES_MD = ROOT / "docs" / "sources.md"
SOURCES_YAML = CONFIG_DIR / "sources.yaml"

COMMON_FIELDS = [
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

AUTHOR_KEY_PREFIX = "author"

ALLOWED_REDDIT_SUBS = {"googlephotos", "googlepixel", "androidquestions"}


def load_env() -> None:
    """Load `env` or `.env` from the project root without extra dependencies."""
    for name in ("env", ".env"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            existing = os.environ.get(key, "")
            if not existing.strip():
                os.environ[key] = value
    _load_streamlit_secrets()


def _load_streamlit_secrets() -> None:
    """Streamlit Cloud injects keys via st.secrets, not the local env file."""
    try:
        import streamlit as st

        secrets = st.secrets
    except Exception:
        return
    for key in ("GROQ_API_KEY", "GROQ_MODEL", "BGE_MODEL", "YOUTUBE_API_KEY"):
        try:
            value = secrets[key]
        except Exception:
            continue
        if value and not os.environ.get(key, "").strip():
            os.environ[key] = str(value)


def load_taxonomy() -> dict:
    with TAXONOMY_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("taxonomy.yaml must be a mapping")
    return data


def empty_utterance() -> dict:
    return {field: "" for field in COMMON_FIELDS}


def strip_author_fields(obj):
    if isinstance(obj, dict):
        return {
            key: strip_author_fields(value)
            for key, value in obj.items()
            if not str(key).lower().startswith(AUTHOR_KEY_PREFIX)
        }
    if isinstance(obj, list):
        return [strip_author_fields(item) for item in obj]
    return obj
