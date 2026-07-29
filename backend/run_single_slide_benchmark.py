#!/usr/bin/env python3
"""
Single-slide model benchmark — isolate the IMAGE MODEL as the only variable,
and deposit a PERMANENT, REPLAYABLE record into the benchmark corpus.

Runs REAL, PAID calls, so it lives outside the deterministic suite and is
invoked by hand on the Mac (Gemini image key for generation; OpenAI key for
validation). It answers one narrow question with everything else frozen: for
one specific slide, is the bottleneck the image model's fidelity, or something
downstream?

What it does:
  1. FREEZE one request into the corpus — Transformation Plan, Generation
     Specification, final provider prompt, reference set (copied images),
     source slide, analysis snapshot, aspect, provider settings and provenance
     (git commit, model ids, schema versions, timestamps). Built ONCE per
     (slideshow, slide). Re-running the same slide REUSES the frozen request
     verbatim so every run is evaluated against identical input; any drift
     between a rebuild and the frozen request is recorded, never applied.
  2. For each model in --models, generate N candidates and SAVE every raw
     candidate to disk BEFORE any validation runs — raw candidates are never
     lost, even if the validator is down (e.g. an OpenAI quota 429).
  3. Apply the SAME validator (assess_candidate) to every candidate, recording
     the identity/photorealism outcome — or the exact exception if validation
     itself fails — per candidate, as distinct states.
  4. Leave an empty human commercial-score slot per candidate, filled later
     with `score_benchmark.py`.
  5. Rebuild the corpus index.

The corpus is the durable artifact. --out only controls where it lives
(default ./benchmark_corpus). Everything needed to replay the exact request
months later is under cases/<case_id>/request/; each invocation adds one
runs/<run_id>/ evaluation beneath it.

Distinct states, recorded per candidate (candidate.json):
  generated=True/False          — did the model return an image at all
  validated=True/False          — did the validator run (vs. service failure)
  validation_error=<str|null>   — the exact exception when it did not run
  identity_passed / accepted    — the candidate-rejection verdict (only meaningful
                                  when validated=True)

Usage:
  python run_single_slide_benchmark.py \
      --slideshow <id-prefix> --slide-index 1 \
      --candidates 3 \
      --models gemini-3.1-flash-image-preview gemini-3-pro-image-preview \
      [--corpus benchmark_corpus] [--notes "why this run"] \
      [--freeze-only]

--freeze-only writes the frozen request and exits WITHOUT any paid generation
(use it to inspect/verify the frozen case, or to seed the corpus offline).

Note: real GenerationAttempt/GeneratedImage/QualityAssessment rows are written
(the production validator needs them). They are tagged in decision_json with
{"benchmark": true} so they are easy to identify and ignore.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Single-slide image-model benchmark (corpus-backed)")
    ap.add_argument("--slideshow", required=True, help="slideshow id or prefix")
    ap.add_argument("--slide-index", type=int, default=None)
    ap.add_argument("--slide-id", default=None, help="explicit slide id (overrides --slide-index)")
    ap.add_argument("--candidates", type=int, default=3)
    ap.add_argument(
        "--models",
        nargs="+",
        default=["gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"],
        help="image model IDs to compare, current first",
    )
    ap.add_argument("--provider", default="nano_banana")
    ap.add_argument("--strategy", default="transformation_plan",
                    choices=["transformation_plan", "source_edit", "source_edit_grounded"],
                    help="source_edit: condition on the original slide, change only background+angle")
    ap.add_argument("--max-attempts", type=int, default=4,
                    help="retries per candidate on transient errors (503/timeout/no-image)")
    ap.add_argument("--corpus", default="benchmark_corpus", help="corpus root directory")
    ap.add_argument("--out", default=None, help="alias for --corpus (back-compat)")
    ap.add_argument("--notes", default="", help="free-text note attached to this run")
    ap.add_argument("--freeze-only", action="store_true",
                    help="write/refresh the frozen request and exit (no paid generation)")
    args = ap.parse_args()

    from app.db import SessionLocal
    from app.benchmark import corpus as corpuslib
    from app.benchmark.runner import resolve_slide, run_case

    repo = Path(__file__).resolve().parent
    corpus_root = Path(args.corpus or args.out or "benchmark_corpus")

    db = SessionLocal()
    slide = resolve_slide(db, slideshow=args.slideshow, slide_index=args.slide_index,
                          slide_id=args.slide_id)
    if slide is None:
        print("No matching slide found."); return 2
    print(f"slide {slide.id[:8]} idx {slide.slide_index} of slideshow {slide.slideshow_id[:8]}")

    summary = run_case(
        db, slide, models=args.models, candidates=args.candidates,
        provider=args.provider, corpus_root=corpus_root, repo=repo,
        notes=args.notes, freeze_only=args.freeze_only, max_attempts=args.max_attempts,
        strategy=args.strategy,
    )
    corpuslib.rebuild_index(corpus_root)

    if summary.get("error"):
        print("ERROR:", summary["error"]); return 2
    print("\n" + "=" * 66)
    if summary.get("frozen_only"):
        print(f"freeze-only: case {summary['case_id']} "
              f"({'new' if summary['created'] else 'reused'}). No generation performed.")
    else:
        print(f"Done. Case {summary['case_id']}, run {summary.get('run_id')}.")
        print("Score candidates with:  python score_benchmark.py --corpus "
              f"{corpus_root} score --case {summary['case_id']} --run {summary.get('run_id')} ...")
    print(f"Corpus: {corpus_root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
