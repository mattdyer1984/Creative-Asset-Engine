"""
END-TO-END slideshow validation — RUN ON YOUR MAC (needs the Keychain keys).

Pipeline exercised, in order:
  import 5 slides as ONE slideshow  ->  assign products (operator step)
  ->  REAL analysis (11 Gemini stages: OCR, product-isolation, scene,
      ownership, marketing, narrative, creative-spec)  [uses the GEMINI key]
  ->  build TransformationPlan for every slide
  ->  derive Attention + Ownership (from the plan) + assemble GenerationSpec
  ->  NanoBananaPromptAdapter -> one provider request per slide
  ->  one paid image generation per slide            [uses the NANO_BANANA key]
  ->  save gen_out_slideshow/slide_<i>.png  +  <i>.manifest.json

Products (operator assignment; the pipeline requires >=1 product per analysed
slide and at most ONE per slide):
    slide 1 (index1) "Not 1" -> toothbrush
    slide 2 (index2) "Not 2" -> serum
    slide 3 (index3) "Not 3" -> toothpaste
    slide 0 (£20 hook) and slide 4 (CTA, 3 products) -> intentionally UNASSIGNED
    (the 3-product CTA is a documented limitation, not a bug to hack around).

Usage (recommended two-phase, avoids paying for analysis twice):
    .venv/bin/python run_slideshow_e2e.py --no-generate
        # PHASE 1: import + assign + REAL analysis + build requests. NO images.
        # Prints "slideshow_id = <ID>". Send me the output; I sanity-check analysis.
    .venv/bin/python run_slideshow_e2e.py --generate-only <ID>
        # PHASE 2: reuse the analysed slideshow <ID>, generate 5 images. No re-analysis.

    .venv/bin/python run_slideshow_e2e.py
        # one-shot full run (import + analysis + 5 generations) if you prefer.

The API keys are read from the macOS Keychain via the app's own get_api_key.
This script never prints, logs, or stores any key value.
"""
import os, sys, json, glob, sqlite3

os.environ.setdefault("CAE_SEQUENTIAL_STAGES", "1")   # deterministic single-thread run

HERE = os.path.dirname(os.path.abspath(__file__))
SLIDES_DIR = os.path.join(HERE, "data", "crocs_slides")     # slide_1.jpg .. (ordered)
OUTDIR = os.path.join(HERE, "gen_out_crocs")
IMAGE_MODEL = "gemini-3.1-flash-image-preview"

# operator product assignment: one product may recur across slides.
# each entry = {name, slides:[0-indexed]}. Crocs Classic Clog is the single
# product, featured on all three slides (shelf / held / worn).
PRODUCTS = [
    {"name": "Crocs Classic Clog Black", "slides": [0, 1, 2]},
]


def resolves(provider):
    from app.ai_providers.config import get_api_key
    try:
        return bool(get_api_key(provider))
    except Exception:
        return False


def ownership_from_plan(plan):
    """Deterministic ownership dict (element_id -> OwnershipDecision), derived from
    the plan's rendering_owner. composite_layer=creator overlay (added later, not
    baked); on-product=product_native; other baked scene text=design_integral."""
    from app.transformation.ownership import OwnershipDecision
    out = {}
    for sd in plan.slides:
        for e in sd.elements:
            if e.kind != "text":
                continue
            if e.rendering_owner == "composite_layer":
                cls, alters = "creator_overlay", False
            elif e.element_id.endswith("_packaging"):
                cls, alters = "product_native", True
            else:
                cls, alters = "design_integral", True
            out[e.element_id] = OwnershipDecision(
                e.element_id, e.verbatim or "", cls, 0.9, alters,
                "derived from plan rendering_owner", ["plan_derived"], [])
    return out


def analysis_health(db_path, slideshow_id):
    """Provider-agnostic check that analysis actually populated the DB."""
    from app.transformation.analysis_source import AnalysisSource
    src = AnalysisSource(db_path)
    rows = []
    for s in src.slides(slideshow_id):
        ocr = len(src.ocr_blocks(s["id"]))
        scene = len(src.scene_regions(s["id"]))
        rows.append((s["slide_index"], ocr, scene))
    return rows


def build_and_generate(DB, sid, generate):
    """Plan -> attention -> ownership -> spec -> adapter per slide; optionally generate.
    Uses only AnalysisSource (raw sqlite) + the transformation layer — no ORM."""
    from app.transformation.analysis_source import AnalysisSource
    from app.transformation.plan_builder import build_plan
    from app.transformation.attention import derive_attention
    from app.transformation.generation_spec import assemble_generation_spec
    from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter
    from app.transformation.generation_request import slide_requirements
    from run_three_families import brief_from_plan, req_to_dict

    plan = build_plan(AnalysisSource(DB), sid)
    attention = derive_attention(plan, brief_from_plan(plan))
    ownership = ownership_from_plan(plan)
    spec = assemble_generation_spec(plan, attention, ownership)
    print(f"[spec] assembled {len(spec.slides)} slide specs")

    os.makedirs(OUTDIR, exist_ok=True)
    adapter = NanoBananaPromptAdapter()
    for slide_spec in sorted(spec.slides, key=lambda s: s.slide_index):
        i = slide_spec.slide_index
        out = adapter.write(slide_spec)
        enc = [f"{e.requirement.id.kind}:{e.requirement.id.ref}" for e in out.manifest.entries if e.status == "encoded"]
        uns = [{"id": f"{e.requirement.id.kind}:{e.requirement.id.ref}", "reason": e.reason}
               for e in out.manifest.entries if e.status == "unsupported"]
        ref_ids = [r for p in slide_spec.products for r in p.reference_ids]
        manifest = {
            "slide_index": i, "slideshow_id": sid,
            "provider_request": out.provider_request,
            "requirements": [req_to_dict(r) for r in slide_requirements(slide_spec)],
            "encoded": enc, "unsupported": uns,
            "overlay_handoff": [{"ref": t.ref, "text": t.text} for t in slide_spec.texts
                                if t.disposition == "overlay_handoff"],
            "reference_ids": ref_ids,
        }
        with open(os.path.join(OUTDIR, f"slide_{i}.request.txt"), "w") as f:
            f.write(out.provider_request)
        with open(os.path.join(OUTDIR, f"slide_{i}.manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"[slide {i}] encoded={len(enc)} unsupported={len(uns)} refs={len(ref_ids)} "
              f"req_chars={len(out.provider_request)}")

        if generate:
            import time
            from run_local_generation import reference_paths, gen_image
            refs = reference_paths(ref_ids)
            _T = ("503", "unavailable", "high demand", "overloaded", "429",
                  "resource_exhausted", "500", "internal", "deadline")
            for attempt in range(1, 4):
                try:
                    img = gen_image(out.provider_request, refs, os.path.join(OUTDIR, f"slide_{i}.png"))
                    print(f"[slide {i}] SAVED {img}  (refs attached: {len(refs)})")
                    break
                except Exception as e:
                    transient = any(t in str(e).lower() for t in _T)
                    print(f"[slide {i}] generation attempt {attempt}/3 failed: {e!r}")
                    if transient and attempt < 3:
                        time.sleep(30 * attempt); continue
                    print(f"[slide {i}] GENERATION FAILED (giving up on this slide, continuing)"); break


def import_assign_analyse(DB):
    """Import 5 slides as one slideshow, assign products, run REAL analysis. Returns slideshow_id."""
    from app.db import SessionLocal
    from app.services.slideshow_import import import_slideshows
    from app.models.product import Product
    from app.models.product_appearance import ProductAppearance
    from app.slideshow_stages.orchestrator import SlideshowOrchestrator

    paths = sorted(glob.glob(os.path.join(SLIDES_DIR, "slide_*.*")))
    if not paths:
        raise SystemExit(f"no slide_*.* files found in {SLIDES_DIR}")
    print(f"[input] {len(paths)} slides:", [os.path.basename(p) for p in paths])

    db = SessionLocal()
    try:
        files = [{"filename": os.path.basename(p), "content": open(p, "rb").read()} for p in paths]
        slideshow = import_slideshows(db, source_type="local_file",
                                      source_config={"files": files},
                                      project_id=None, group_as_one=True)[0]
        sid = slideshow.id
        slides = sorted(slideshow.slides, key=lambda s: s.slide_index)
        print(f"[import] slideshow {sid[:8]} with {len(slides)} slides")

        for entry in PRODUCTS:
            prod = Product(display_name=entry["name"]); db.add(prod); db.flush()
            for idx in entry["slides"]:
                db.add(ProductAppearance(slide_id=slides[idx].id, product_id=prod.id,
                                         prominence="primary", confidence=1.0, is_current=True))
                print(f"[assign] slide {idx} <- {entry['name']}")
        db.commit()

        print("[analyze] running full analysis pipeline (paid calls)...")
        import time
        orch = SlideshowOrchestrator()
        _TRANSIENT = ("503", "UNAVAILABLE", "high demand", "overloaded",
                      "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL", "deadline")
        for attempt in range(1, 5):
            try:
                res = orch.run_full_pipeline(db, slideshow)
                print("[analyze] pipeline returned:", res)
                break
            except Exception as e:
                is_transient = any(t.lower() in str(e).lower() for t in _TRANSIENT)
                print(f"[analyze] attempt {attempt}/4 failed: {e!r}")
                if is_transient and attempt < 4:
                    wait = 45 * attempt
                    print(f"  transient provider overload — waiting {wait}s, then retrying "
                          "(earlier completed stages may re-run)...")
                    time.sleep(wait)
                    continue
                raise
        db.commit()

        health = analysis_health(DB, sid)
        print("[analyze] per-slide (index, ocr_blocks, scene_regions):", health)
        if any(scene == 0 for _, _, scene in health):
            print("  ! some slides have no scene analysis — analysis may have partially failed; "
                  "check the pipeline return above before trusting downstream output.")
        return sid
    finally:
        db.close()


def main():
    from app.config import settings
    DB = str(settings.database_path)
    args = sys.argv[1:]
    no_gen = "--no-generate" in args
    gen_only = "--generate-only" in args
    positional = [a for a in args if not a.startswith("--")]

    nb_ok, gem_ok = resolves("nano_banana"), resolves("gemini")
    print(f"[keys] nano_banana resolved: {nb_ok} | gemini resolved: {gem_ok}")
    will_generate = not no_gen
    if will_generate and not nb_ok:
        raise SystemExit("nano_banana key not resolved — needed for image generation. Aborting before spend.")

    if gen_only:
        if not positional:
            raise SystemExit("--generate-only needs a slideshow_id: run_slideshow_e2e.py --generate-only <ID>")
        sid = positional[0]
        print(f"[generate-only] reusing analysed slideshow {sid[:8]} (no re-analysis)")
        build_and_generate(DB, sid, generate=True)
        print(f"\nDONE. Images + manifests in {OUTDIR}\nslideshow_id = {sid}")
        return

    if not gem_ok:
        print("  (note: no separate 'gemini' key — the analysis stages reuse the nano_banana key, "
              "so this is normally fine.)")
    sid = import_assign_analyse(DB)
    build_and_generate(DB, sid, generate=will_generate)
    print("\nDONE." + ("  (analysis + requests only; no images generated)" if no_gen
                        else f"  Images + manifests in {OUTDIR}"))
    print(f"slideshow_id = {sid}")


if __name__ == "__main__":
    main()
