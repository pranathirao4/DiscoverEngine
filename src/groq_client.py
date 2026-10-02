"""
Groq client for LLM jobs only (gate, extract, synthesis).

Embeddings are local BGE (`src/embed.py`). Do not call OpenAI.
Cache key is item id + prompt_version + model_id.
On a re-run, a cache hit must not call Groq again.
Never send or store Reddit author names.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from common import ROOT, load_env

CACHE_DIR = ROOT / "data" / "processed" / "groq_cache"


def cache_key(item_id: str, prompt_version: str, model_id: str) -> str:
    raw = f"{item_id}|{prompt_version}|{model_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(item_id: str, prompt_version: str, model_id: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{cache_key(item_id, prompt_version, model_id)}.json"


class GroqClient:
    """Thin wrapper: retries on 429/5xx, reuses disk cache."""

    def __init__(self, model_id: str | None = None) -> None:
        load_env()
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.model_id = model_id or os.environ.get("GROQ_MODEL") or "openai/gpt-oss-20b"
        self._client = None

    def _sdk(self):
        if self._client is None:
            if not self.api_key:
                raise RuntimeError(
                    "GROQ_API_KEY is missing. Copy .env.example to env and add your key."
                )
            from groq import Groq

            self._client = Groq(api_key=self.api_key)
        return self._client

    def complete_json(
        self,
        *,
        item_id: str,
        prompt_version: str,
        system: str,
        user: str,
    ) -> dict:
        path = cache_path(item_id, prompt_version, self.model_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

        delay = 2.0
        last_error: Exception | None = None
        for attempt in range(1, 6):
            try:
                data = self._complete_once(system, user, response_format=True)
                if not path.exists():
                    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                return data
            except Exception as exc:  # noqa: BLE001 — Groq SDK errors vary by version
                last_error = exc
                message = str(exc).lower()
                if "json_validate_failed" in message or "failed to validate json" in message:
                    try:
                        data = self._complete_once(system, user, response_format=False)
                        if not path.exists():
                            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                        return data
                    except Exception as fallback_exc:  # noqa: BLE001
                        last_error = fallback_exc
                        message = str(fallback_exc).lower()
                retryable = (
                    "429" in message
                    or "rate" in message
                    or "timeout" in message
                    or "500" in message
                    or "502" in message
                    or "503" in message
                    or "504" in message
                )
                if not retryable or attempt == 5:
                    break
                wait = _retry_seconds(message, delay)
                if wait >= 5:
                    print(f"  Groq rate limit; waiting {wait:.0f}s", flush=True)
                time.sleep(wait)
                delay = min(delay * 2, 120)
        raise RuntimeError(f"Groq call failed after retries: {last_error}") from last_error

    def _complete_once(self, system: str, user: str, *, response_format: bool) -> dict:
        kwargs: dict = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 512,
        }
        if response_format:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._sdk().chat.completions.create(**kwargs)
        text = response.choices[0].message.content or "{}"
        return _parse_json_object(text)


def _retry_seconds(message: str, fallback: float) -> float:
    """Honour Groq's 'try again in 7m27s' hint instead of a short backoff."""
    minutes = re.search(r"try again in (\d+)m([\d.]+)s", message)
    if minutes:
        return int(minutes.group(1)) * 60 + float(minutes.group(2)) + 2
    seconds = re.search(r"try again in ([\d.]+)s", message)
    if seconds:
        return float(seconds.group(1)) + 1
    return fallback


def _parse_json_object(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Groq JSON response was not an object")
    return data
