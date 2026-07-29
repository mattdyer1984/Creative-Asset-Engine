#!/usr/bin/env python3
"""
Slideshow continuity prototype — a SHARED BACKGROUND PLATE across a slideshow.

This is the OPT-IN "single-location" path (per the design: continuity is a
per-slideshow choice, not always-on — animated / multi-location / store slideshows
skip it). Running this script = opting in. It:

  1. Builds ONE background plate — a new, original version of the room, emptied of
     product and people — seeded from the slide that shows the most room
     (--plate-slide).
  2. Generates every slide conditioned on TWO references: the slide's own source
     (product / subject / pose / medium) AND the plate (the room), instructed to
     place the subject in that same room.

So all slides share one consistent, original setting. Costs one extra generation
per slideshow (the plate), amortised across every slide.

Example:
  python run_slideshow_continuity.py --slideshow aa5a26b9 --plate-slide 1 \
    --candidates 1 --models gemini-3-pro-image-preview \
    --out benchmark_corpus/_adhoc/aa5a26b9_continuity

Outputs to --out: _plate.png, then slide<idx>_<model>_cand<i>.png. Prototype —
writes to a folder, not the corpus.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _plate_prompt(room: str, aspect: str) -> str:
    room = (room or "room").strip().rstrip(".")
    return (
        f"Using the provided image as a reference for the KIND of space, generate a NEW, "
        f"original, EMPTY interior of the same type of room (originally: {room}). Remove any "
        f"product and any person entirely — show only the room itself. It must look like a "
        f"REAL person's actual, lived-in room casually photographed on a phone — NOT a "
        f"pristine interior-design or furniture-catalog showroom. Include everyday realism: "
        f"a casually-made (not perfectly-styled) bed, some personal belongings and light "
        f"clutter, natural imperfect daylight, ordinary wear. Keep it the same KIND of place "
        f"but a clearly different specific room from the reference (different decor and "
        f"layout) for originality. No text, no people, no products. Output aspect ratio {aspect}."
    )


def _continuity_slide_prompt(name: str, scene, aspect: str) -> str:
    from app.benchmark.runner import _grounded_keep_clause, _UGC_REALISM

    keep = _grounded_keep_clause(scene)
    return (
        f"You are given TWO reference images. IMAGE 1 is the original slide: keep the product/"
        f"subject from it EXACTLY — identical shape, colour, materials, branding, logos and any "
        f"printed text — and match its visual MEDIUM (if photographic keep it photographic; if "
        f"illustrated/cartoon keep that style). IMAGE 2 is the ROOM to use. Place the product/"
        f"subject ({name}) into the room shown in IMAGE 2: use its background, surfaces, "
        f"furniture and lighting; do NOT invent a different room — this room must stay consistent."
        + _UGC_REALISM +
        f" Change the camera angle and framing moderately for a fresh, original shot.{keep} Keep "
        f"the product the clear main focus. Any overlaid marketing caption may be removed. Output "
        f"aspect ratio {aspect}."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Slideshow continuity prototype (shared background plate)")
    ap.add_argument("--slideshow", required=True, help="slideshow id or prefix")
    ap.add_argument("--plate-slide", type=int, default=0, help="slide index to seed the room plate from")
    ap.add_argument("--candidates", type=int, default=1)
    ap.add_argument("--models", nargs="+", default=["gemini-3-pro-image-preview"])
    ap.add_argument("--provider", default="nano_banana")
    ap.add_argument("--max-attempts", type=int, default=4)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from app.db import SessionLocal
    from app.models.slide import Slide
    from app.models.product import Product
    from app.slideshow_stages.creative_specification_stage import resolve_primary_appearance
    from app.ai_providers.base import GenerationRequest
    from app.ai_providers.nano_banana_adapter import NanoBananaImageGenerationAdapter
    from app.benchmark import corpus as corpuslib
    from app.benchmark.runner import (
        _generate_with_retry, source_output_aspect, resolve_slide,
    )
    from app.services.transformation_runner import build_slideshow_spec

    db = SessionLocal()
    slides = (
        db.query(Slide).filter(Slide.slideshow_id.like(args.slideshow + "%"))
        .order_by(Slide.slide_index).all()
    )
    if not slides:
        print("No slides found."); return 2
    ssid = slides[0].slideshow_id
    out = Path(args.out or f"benchmark_corpus/_adhoc/{ssid[:8]}_continuity")
    out.mkdir(parents=True, exist_ok=True)
    print(f"slideshow {ssid[:8]}  slides={len(slides)}  plate-seed=idx {args.plate_slide}")

    # scene per slide index (for the keep/recast clause + room type)
    scene_by_idx = {}
    try:
        spec = build_slideshow_spec(ssid)
        scene_by_idx = {s.slide_index: s.scene for s in spec.slides}
    except Exception as exc:
        print(f"(no transformation spec: {type(exc).__name__}: {exc} — continuing with minimal scene)")

    def src_path(slide):
        return corpuslib._resolve_asset_path(getattr(slide, "stored_file_path", "") or "")

    # ---- 1. build the room plate from the seed slide ----
    seed = next((s for s in slides if s.slide_index == args.plate_slide), slides[0])
    seed_src = src_path(seed)
    if seed_src is None:
        print(f"plate-seed slide idx {seed.slide_index} has no resolvable source image."); return 2
    aspect = source_output_aspect(seed, "3:4")
    seed_scene = scene_by_idx.get(seed.slide_index)
    room = getattr(seed_scene, "environment", None) or "room"
    plate_prompt = _plate_prompt(room, aspect)
    (out / "_plate_prompt.txt").write_text(plate_prompt)
    print(f"\nBUILDING PLATE (room~ {room[:40]!r}, aspect {aspect}) from slide {seed.slide_index}")
    adapter = NanoBananaImageGenerationAdapter(model=args.models[0], provider=args.provider)
    plate_req = GenerationRequest(creative_intent=plate_prompt, reference_image_paths=[str(seed_src)],
                                  things_to_avoid=[], aspect_ratio=aspect, precompiled_prompt=plate_prompt)
    result, attempts, exc = _generate_with_retry(adapter, plate_req, args.max_attempts)
    if result is None:
        print(f"  PLATE FAILED after {attempts}: {exc}"); return 2
    plate_path = out / "_plate.png"; plate_path.write_bytes(result.image_bytes)
    print(f"  plate saved -> {plate_path}")

    # ---- 2. generate each slide with [source, plate] ----
    for slide in slides:
        s_src = src_path(slide)
        if s_src is None:
            print(f"slide {slide.slide_index}: no source image, skipping"); continue
        appearance = resolve_primary_appearance(slide.current_product_appearances)
        product = db.get(Product, appearance.product_id) if appearance else None
        name = product.display_name if product else "the product"
        scene = scene_by_idx.get(slide.slide_index)
        asp = source_output_aspect(slide, aspect)
        prompt = _continuity_slide_prompt(name, scene, asp)
        req = GenerationRequest(
            creative_intent=prompt,
            reference_image_paths=[str(s_src), str(plate_path)],  # IMAGE 1 = source, IMAGE 2 = plate
            things_to_avoid=[], aspect_ratio=asp, precompiled_prompt=prompt,
        )
        print(f"\nSLIDE {slide.slide_index}  ({name[:30]})  aspect {asp}")
        for model in args.models:
            ad = NanoBananaImageGenerationAdapter(model=model, provider=args.provider)
            for i in range(args.candidates):
                r, att, e = _generate_with_retry(ad, req, args.max_attempts)
                if r is None:
                    print(f"  {model.split('-')[1]} cand{i}: FAILED after {att}: {e}"); continue
                p = out / f"slide{slide.slide_index}_{model.replace('/', '_')}_cand{i}.png"
                p.write_bytes(r.image_bytes)
                print(f"  {model.split('-')[1]} cand{i}: saved {p.name}" + (f" (attempt {att})" if att > 1 else ""))

    print(f"\nDone. Plate + slides in: {out}")
    print("Send me that folder and I'll check whether the room holds across the set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
