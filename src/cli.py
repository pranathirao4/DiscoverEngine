"""Phase runner: compile sources, harvest Play, import JSON, write corpus, thin slice."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import load_env  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(description="AI_Discovery phase jobs")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Create empty SQLite from schema.sql")
    sub.add_parser("compile-sources", help="docs/sources.md -> config/sources.yaml")
    play = sub.add_parser("harvest-play", help="Fetch Play Store reviews (all stars)")
    play.add_argument("--count-per-star", type=int, default=40)
    sub.add_parser("import-json", help="Filter reddit_apify.json into common schema")
    sub.add_parser("write-corpus", help="Union raw CSVs into corpus_all.csv")
    sub.add_parser("verify-urls", help="Check listing/thread/video URLs")
    gate = sub.add_parser("gate", help="Phase 2: gate + extract the full corpus (Groq)")
    gate.add_argument("--limit", type=int, default=0, help="Label only the first N rows (0 = full corpus)")
    slice_p = sub.add_parser("thin-slice", help="Phase 0.5: gate+extract ~100 items (Groq)")
    slice_p.add_argument("--n", type=int, default=100)
    emb = sub.add_parser("embed", help="BGE embeddings (local; not OpenAI)")
    emb.add_argument(
        "--input",
        default="",
        help="Labeled CSV (default: data/processed/thin_slice_labeled.csv)",
    )

    ask_p = sub.add_parser("ask", help="Ask the labeled corpus (BGE + Groq)")
    ask_p.add_argument("question", nargs="+", help="PM question about the evidence")

    args = parser.parse_args(argv)

    if args.cmd == "init-db":
        from init_db import init_db

        print(f"Empty database ready: {init_db()}")
        return 0
    if args.cmd == "compile-sources":
        from compile_sources import write_sources_yaml

        write_sources_yaml()
        return 0
    if args.cmd == "harvest-play":
        from harvest_play import harvest_play

        harvest_play(count_per_star=args.count_per_star)
        return 0
    if args.cmd == "import-json":
        from import_provided_json import import_provided_json

        import_provided_json()
        return 0
    if args.cmd == "write-corpus":
        from write_corpus import write_corpus_all

        write_corpus_all()
        return 0
    if args.cmd == "verify-urls":
        from verify_urls import verify_urls

        verify_urls()
        return 0
    if args.cmd == "gate":
        from gate_corpus import run_gate

        run_gate(limit=args.limit)
        return 0
    if args.cmd == "thin-slice":
        from thin_slice import run_thin_slice

        run_thin_slice(n=args.n)
        return 0
    if args.cmd == "embed":
        from embed import run_embed

        run_embed(args.input or None)
        return 0
    if args.cmd == "ask":
        from ask import ask as ask_corpus
        import json

        result = ask_corpus(" ".join(args.question))
        out = json.dumps(result, indent=2, ensure_ascii=False)
        (Path(__file__).resolve().parent.parent / "data" / "processed" / "last_ask.json").write_text(
            out, encoding="utf-8"
        )
        try:
            print(out)
        except UnicodeEncodeError:
            print(out.encode("utf-8", errors="replace").decode("ascii", errors="replace"))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
