#!/usr/bin/env python3
"""
Run the GROUNDED source-edit strategy on an ARBITRARY image file (not a DB slide).

For ad-hoc tests — e.g. an uploaded example image that isn't in the library. It
reuses the exact grounded prompt builder from the benchmark
(app.benchmark.runner._source_edit_grounded_prompt), so what it produces reflects
the real strategy, including the human/character recast logic. Scene facts that a
DB slide would get from analysis are supplied here on the command line.

Example (the eyelash-lift example):
  python run_source_edit_image.py \
    --image benchmark_corpus/_adhoc/lash.jpg \
    --product "the eyelash comparison (lifted lashes vs flat lashes)" \
    --subject-action "a woman touching under her eye to show lifted vs flat lashes" \
    --subject-extent face --environment "bedroom" \
    --candidates 2 --models gemini-3.1-flash-image-preview gemini-3-pro-image-preview \
    --out benchmark_corpus/_adhoc/lash_out

Saves prompt.txt + one PNG per model/candidate to --out. No DB, no corpus.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace


def main() -> int:
    ap = argparse.ArgumentParser(description="Grounded source-edit on an arbitrary image")
    ap.add_argument("--image", required=True, help="path to the reference image")
    ap.add_argument("--product", default="the subject",
                    help="what to keep identical / the demonstrated effect")
    ap.add_argument("--subject-action", default=None,
                    help="what the person is doing (triggers human recast when a face/figure)")
    ap.add_argument("--subject-extent", default="face",
                    help="hand | face | full figure ... (face/figure => recast the person)")
    ap.add_argument("--environment", default=None, help="setting type to keep (e.g. bedroom)")
    ap.add_argument("--aspect", default="3:4")
    ap.add_argument("--candidates", type=int, default=2)
    ap.add_argument("--models", nargs="+",
                    default=["gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"])
    ap.add_argument("--provider", default="nano_banana")
    ap.add_argument("--max-attempts", type=int, default=4)
    ap.add_argument("--out", default="source_edit_image_out")
    args = ap.parse_args()

    from app.benchmark.runner import _source_edit_grounded_prompt, _generate_with_retry
    from app.ai_providers.base import GenerationRequest
    from app.ai_providers.nano_banana_adapter import NanoBananaImageGenerationAdapter

    if not Path(args.image).is_file():
        print(f"image not found: {args.image}"); return 2

    scene = SimpleNamespace(
        subject_present=bool(args.subject_action or args.subject_extent),
        subject_action=args.subject_action,
        subject_extent=args.subject_extent,
        product_subject_relation=None,
        environment=args.environment,
    )
    prompt = _source_edit_grounded_prompt(args.product, scene, args.aspect)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.txt").write_text(prompt)
    print("PROMPT:\n" + prompt + "\n" + "=" * 66)

    req = GenerationRequest(
        creative_intent=prompt, reference_image_paths=[args.image],
        things_to_avoid=[], aspect_ratio=args.aspect, precompiled_prompt=prompt,
    )
    for model in args.models:
        adapter = NanoBananaImageGenerationAdapter(model=model, provider=args.provider)
        print(f"\nMODEL {model}")
        for i in range(args.candidates):
            result, attempts, exc = _generate_with_retry(adapter, req, args.max_attempts)
            if result is None:
                print(f"  cand {i}: FAILED after {attempts} attempt(s): {exc}")
                continue
            p = out / f"{model.replace('/', '_')}_cand{i}.png"
            p.write_bytes(result.image_bytes)
            print(f"  cand {i}: saved {p}" + (f" (attempt {attempts})" if attempts > 1 else ""))

    print("\nDone. Images in:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
