#!/usr/bin/env python3
"""
Batch benchmark — freeze/run a SLATE of slides in one command, to build up the
corpus into a real dataset (one scored image is an anecdote; a spread of slides
across products is a distribution).

Each slate entry is `slideshow[:slide_index]` (prefix match on slideshow id). With
no index, slide 0 is used. Example — five different products, one slide each:

  python run_benchmark_batch.py \
    --slate a522518b:1 c2cf0e58:0 bd1f62a2:1 2ba6c7e4:1 2416fea4:0 \
    --candidates 2 --models gemini-3.1-flash-image-preview gemini-3-pro-image-preview \
    --notes "first 5-product dataset"

Add --freeze-only to stage every case with NO paid calls (freezing is free) — use
it to inspect the frozen requests + source slides before spending anything, then
re-run without --freeze-only to generate.

Runs are additive: re-running the same slate reuses each frozen request verbatim
and appends a new run, so the dataset accumulates over time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _parse_entry(entry: str):
    if ":" in entry:
        pfx, idx = entry.split(":", 1)
        return pfx, int(idx)
    return entry, 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch benchmark over a slate of slides")
    ap.add_argument("--slate", nargs="+", required=True,
                    help="entries 'slideshow[:index]' (repeatable)")
    ap.add_argument("--candidates", type=int, default=2)
    ap.add_argument("--models", nargs="+",
                    default=["gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"])
    ap.add_argument("--provider", default="nano_banana")
    ap.add_argument("--strategy", default="transformation_plan",
                    choices=["transformation_plan", "source_edit", "source_edit_grounded"],
                    help="source_edit: condition on the original slide, change only background+angle")
    ap.add_argument("--corpus", default="benchmark_corpus")
    ap.add_argument("--notes", default="")
    ap.add_argument("--max-attempts", type=int, default=4,
                    help="retries per candidate on transient errors (503/timeout/no-image)")
    ap.add_argument("--freeze-only", action="store_true",
                    help="stage every case with no paid generation")
    args = ap.parse_args()

    from app.db import SessionLocal
    from app.benchmark import corpus as corpuslib
    from app.benchmark.runner import resolve_slide, run_case

    repo = Path(__file__).resolve().parent
    corpus_root = Path(args.corpus)
    db = SessionLocal()

    summaries = []
    for entry in args.slate:
        pfx, idx = _parse_entry(entry)
        print("\n" + "=" * 70)
        print(f"SLATE ENTRY {entry}")
        slide = resolve_slide(db, slideshow=pfx, slide_index=idx)
        if slide is None:
            print(f"  no slide for {entry}")
            summaries.append({"entry": entry, "error": "no matching slide"})
            continue
        summary = run_case(
            db, slide, models=args.models, candidates=args.candidates,
            provider=args.provider, corpus_root=corpus_root, repo=repo,
            notes=args.notes, freeze_only=args.freeze_only, max_attempts=args.max_attempts,
            strategy=args.strategy,
        )
        summary["entry"] = entry
        summaries.append(summary)

    corpuslib.rebuild_index(corpus_root)

    print("\n" + "=" * 70)
    print("BATCH SUMMARY")
    for s in summaries:
        if s.get("error"):
            print(f"  {s['entry']}: ERROR — {s['error']}")
        elif s.get("frozen_only"):
            print(f"  {s['entry']}: frozen {s['case_id']} "
                  f"({'new' if s['created'] else 'reused'})")
        else:
            accepts = sum(
                1 for recs in (s.get("results") or {}).values()
                for r in recs if r.get("accepted")
            )
            gens = sum(
                1 for recs in (s.get("results") or {}).values()
                for r in recs if r.get("generated")
            )
            print(f"  {s['entry']}: case {s['case_id']} run {s.get('run_id')}  "
                  f"generated={gens} accepted={accepts}")
    print(f"\nCorpus: {corpus_root}/")
    if not args.freeze_only:
        print("Score with:  python score_benchmark.py --corpus "
              f"{corpus_root} analyze   (and `score` per candidate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
