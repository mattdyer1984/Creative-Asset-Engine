"""
Shared benchmark run logic — used by both the single-slide CLI and the batch CLI.

`run_case` freezes one slide into the corpus and (unless freeze_only) generates N
candidates per model, saving every raw candidate BEFORE validation, then applies
the validator, recording generation / validation-service / rejection as distinct
states. It is the one definition of "run a benchmark on a slide"; the CLIs are
thin wrappers so single-slide and batch behave identically.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

# Signatures of TRANSIENT provider failures worth retrying — server overload,
# timeouts, rate limits, and the intermittent "returned text, no image" response
# (which is a soft, re-askable failure, not a hard refusal). A genuine content
# refusal or bad request won't match these and fails fast without wasting calls.
_TRANSIENT_MARKERS = (
    "503", "500", "502", "504", "unavailable", "overloaded", "timeout", "timed out",
    "429", "rate limit", "resource exhausted", "no image data", "deadline",
    "connection reset", "temporarily",
)


def _is_transient(exc: Exception) -> bool:
    s = f"{type(exc).__name__}: {exc}".lower()
    return any(m in s for m in _TRANSIENT_MARKERS)


def _generate_with_retry(adapter, request, max_attempts: int):
    """Call the provider up to max_attempts times, retrying TRANSIENT failures with
    exponential backoff (2s, 4s, 8s, capped). Returns (result|None, attempts_used,
    last_exc|None). A non-transient error fails immediately."""
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return adapter.generate_image(request), attempt, None
        except Exception as exc:  # noqa: BLE001 - provider errors are opaque
            last_exc = exc
            if attempt < max_attempts and _is_transient(exc):
                delay = min(2 ** attempt, 10)
                print(f"      transient error (attempt {attempt}/{max_attempts}): "
                      f"{type(exc).__name__}: {str(exc)[:60]} — retrying in {delay}s")
                time.sleep(delay)
                continue
            return None, attempt, exc
    return None, max_attempts, last_exc


STRATEGIES = ("transformation_plan", "source_edit", "source_edit_grounded")


def _source_edit_prompt(product_name: str, aspect: str) -> str:
    """NAIVE source-edit: minimal 'keep the product, change background + angle'. Kept
    for A/B against the grounded variant — it is deliberately loose (it does NOT
    preserve the original composition), which is why it can drop the human hand and
    invent an unrelated scene."""
    return (
        f"Use the provided image as the reference. Produce a NEW, original product "
        f"photograph of the same subject ({product_name}). Keep the product itself "
        f"EXACTLY the same — identical shape, colour, materials, proportions, "
        f"branding, logos and any text printed on the product. Change ONLY the "
        f"background/setting and the camera angle, so the result reads as a fresh, "
        f"original photo and not a copy of the reference. Keep it photorealistic, "
        f"naturally lit and commercially appealing, with the product as the clear "
        f"main focus. Any overlaid marketing caption from the reference may be "
        f"removed. Output aspect ratio {aspect}."
    )


def _grounded_keep_clause(scene) -> str:
    """Turn analysis scene facts into a 'preserve THIS composition' instruction.

    Key distinction for ORIGINALITY: a physical product is kept identical, but a
    real *person* must NOT be reproduced verbatim — that recreates a real,
    identifiable individual, which is both an originality flag on TikTok and a
    likeness problem. So when a person is a visible subject (a face/figure, not
    just a hand), keep the action and the demonstrated effect (the lash/makeup/
    skin result) but RECAST them as a different, similar-looking individual. A
    limb-only subject (a hand holding a product) has no identity to protect, so it
    is simply kept as a limb. Empty when analysis saw no person."""
    if scene is None or not getattr(scene, "subject_present", False):
        return ""
    action = getattr(scene, "subject_action", None)
    extent = getattr(scene, "subject_extent", None)
    rel = getattr(scene, "product_subject_relation", None)
    if action:
        who = f"a person {action}"
    elif rel:
        who = f"the product {rel} by a person"
    else:
        who = "a person present with the product"
    extent_bit = f" (showing the {extent})" if extent else ""

    limb_only = (extent or "").strip().lower() in (
        "", "hand", "hands", "hand and forearm", "forearm", "lower legs", "legs", "feet",
    )
    if limb_only:
        return (f" Preserve the composition: keep {who}{extent_bit}, in the same pose and "
                f"framing as the reference; only a limb is shown, so keep it just a limb "
                f"(do not add a full person or a face).")
    # A visible subject (real person OR illustrated/animated character): PRESERVE
    # role/action/expression/type/style, but CHANGE identity/face/features/pose/
    # placement. Reproducing the same person or character is an originality problem,
    # and source-conditioning anchors the face — so the change must be made explicit.
    return (
        f" Preserve the subject's ROLE, ACTION and EXPRESSION and any product or demonstrated "
        f"effect shown on them (e.g. the lash / makeup / skin result), and keep their general "
        f"TYPE and ART STYLE (gender, approximate age, hair colour, skin tone; for illustration, "
        f"the same drawing/cartoon style). CRITICAL for originality: the subject — a real person "
        f"OR an illustrated/animated character — MUST be a clearly DIFFERENT individual. Change "
        f"the identity and face/design: a different nose, jaw, eye shape and hairline, different "
        f"distinguishing features, and a changed pose, placement and camera angle, so it is "
        f"unmistakably NOT the same person or character. Never reproduce the reference's face or "
        f"identity — only its general type and style."
    )


def _grounded_environment_clause(scene) -> str:
    """Pin the KIND of setting from analysis so the refresh stays in-category — a
    kitchen stays a kitchen, a bedroom stays a bedroom — instead of jumping to an
    unrelated location (the 'shoe on a beach' failure). The specific decor may still
    vary for originality. Empty when analysis captured no environment."""
    env = (getattr(scene, "environment", None) or "").strip().rstrip(".") if scene else ""
    if not env:
        return ""
    return (f" Keep the SAME TYPE of setting as the reference (originally: {env}): you may "
            f"vary the specific decor, props, colours and layout for originality, but the "
            f"scene must stay the same kind of place — a kitchen stays a kitchen, a bedroom "
            f"stays a bedroom, a bathroom stays a bathroom, an outdoor shot stays outdoors.")


# UGC realism — the end goal for photographic slides is an authentic, casual
# user-generated phone photo, NOT a polished studio/catalog shot. Over-perfection is
# what reads as "AI"; a lived-in, slightly imperfect scene reads as real. Also forces
# the product to sit IN the scene (perspective, contact shadows, matching light) so it
# doesn't look pasted over the background. Applies only to photographic output.
_UGC_REALISM = (
    " If the result is photographic, it MUST look like an authentic, casual phone photo "
    "taken by a real person for social media (UGC) — natural, slightly imperfect lighting "
    "and framing, a genuinely lived-in space with everyday clutter and personal touches "
    "(not staged or spotless), and NOT a polished studio, catalog or advertisement look. "
    "The product must sit naturally WITHIN the scene, with correct perspective, believable "
    "contact shadows and ambient light that matches the room, so it looks photographed "
    "there — never pasted on top. Avoid an over-perfect, glossy, 'stock photo' feel. Aim "
    "for GOOD-quality UGC — a skilled creator's clean, well-shot phone photo — not a "
    "mediocre or amateur one."
)

# Lighting — imperfection belongs in the ROOM, never in how the product is lit. The
# product must be bright, clearly visible and flatteringly lit (true to its colour) so
# it sells; replicate the reference slide's good, bright lighting. Medium-agnostic.
_GOOD_LIGHTING = (
    " Light the product well: it must be bright, clearly visible and flatteringly lit, with "
    "its TRUE colour and detail reading accurately — replicate the good, bright lighting of "
    "the reference slide. Never leave the product dark, dim, muddy or in shadow; a slightly "
    "imperfect ROOM is fine, but the product itself must always be well-lit and appealing."
)


def _source_edit_grounded_prompt(product_name: str, scene, aspect: str) -> str:
    """GROUNDED source-edit: condition on the original slide AND on a few analysis
    facts (subject/hand, setting type, and preserve the medium), refreshing only the
    background details + angle moderately. The 'combine reference + basic analysis' path."""
    keep = _grounded_keep_clause(scene)
    env = _grounded_environment_clause(scene)
    return (
        f"Use the provided image as the reference. Produce a NEW, original image of the "
        f"same subject ({product_name}). Keep the product itself EXACTLY the same — "
        f"identical shape, colour, materials, proportions, branding, logos and any "
        f"printed text. Match the visual style and MEDIUM of the reference: if it is a "
        f"photograph keep it photographic; if it is illustrated, cartoon or animated, "
        f"keep that exact style and do NOT make it photorealistic." + _UGC_REALISM + _GOOD_LIGHTING +
        f" Refresh the specific background details and change the camera angle so it reads "
        f"as a new, original shot rather than a copy — but keep the change moderate and do "
        f"not invent an unrelated scene.{env}{keep} Keep the product the clear main focus. "
        f"Any overlaid marketing caption from the reference may be removed. Output aspect "
        f"ratio {aspect}."
    )


def _source_edit_request(slide, prompt: str, aspect: str):
    """Build a source-edit GenerationRequest: the ORIGINAL slide image as the
    reference + the given prompt. Returns the request, or None when the slide has no
    resolvable source image."""
    from app.benchmark import corpus as corpuslib
    from app.ai_providers.base import GenerationRequest

    src = corpuslib._resolve_asset_path(getattr(slide, "stored_file_path", "") or "")
    if src is None:
        return None
    return GenerationRequest(
        creative_intent=prompt,
        reference_image_paths=[str(src)],
        things_to_avoid=[],
        aspect_ratio=aspect,
        precompiled_prompt=prompt,
    )


# Output aspect ratios Nano Banana supports, as width/height floats. We KEEP the
# original slide's ratio (snapped to the nearest supported one) rather than forcing
# 3:4 — squashing a 1:1 or 9:16 slide into 3:4 hurts both fidelity and originality.
_SUPPORTED_ASPECTS = {
    "1:1": 1.0, "2:3": 2 / 3, "3:4": 3 / 4, "4:3": 4 / 3,
    "3:2": 3 / 2, "9:16": 9 / 16, "16:9": 16 / 9, "21:9": 21 / 9,
}


def _nearest_aspect_ratio(width, height, default: str = "3:4") -> str:
    if not width or not height:
        return default
    r = width / height
    return min(_SUPPORTED_ASPECTS, key=lambda k: abs(_SUPPORTED_ASPECTS[k] - r))


def _measure_image(path):
    """(width, height) of an image, via the app's measurer with a PIL fallback."""
    try:
        from app.services.image_dimensions import measure_source_file

        _, dims = measure_source_file(path)
        if dims:
            return int(dims[0]), int(dims[1])
    except Exception:
        pass
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception:
        return None, None


def source_output_aspect(slide, default: str = "3:4") -> str:
    """The output aspect for a slide = its ORIGINAL image's ratio, snapped to the
    nearest supported provider ratio. Falls back to `default` when the source image
    can't be measured."""
    from app.benchmark import corpus as corpuslib

    raw = getattr(slide, "stored_file_path", "") or ""
    src = corpuslib._resolve_asset_path(raw) or raw
    w, h = _measure_image(str(src)) if src else (None, None)
    return _nearest_aspect_ratio(w, h, default)


def resolve_slide(db, *, slideshow: Optional[str] = None, slide_index: Optional[int] = None,
                  slide_id: Optional[str] = None):
    """Resolve a Slide by explicit id, or by slideshow-prefix (+ optional index)."""
    from app.models.slide import Slide

    if slide_id:
        return db.get(Slide, slide_id)
    q = db.query(Slide).filter(Slide.slideshow_id.like((slideshow or "") + "%"))
    if slide_index is not None:
        q = q.filter(Slide.slide_index == slide_index)
    return q.order_by(Slide.slide_index).first()


def run_case(
    db,
    slide,
    *,
    models: list[str],
    candidates: int,
    provider: str,
    corpus_root: Path,
    repo: Path,
    notes: str = "",
    freeze_only: bool = False,
    max_attempts: int = 4,
    strategy: str = "transformation_plan",
) -> dict:
    """Freeze `slide` into the corpus and (unless freeze_only) run the benchmark.

    Returns a summary dict: {case_id, created, drift, run_id?, results?, error?}.
    Never raises for a single-slide failure it can describe — returns {"error": ...}
    so a batch keeps going."""
    from app.models.product import Product
    from app.models.creative_specification import CreativeSpecification
    from app.models.generated_image import GeneratedImage
    from app.models.generation_attempt import GenerationAttempt
    from app.models.analysis_run import ANALYSIS_TYPE_GENERATED_IMAGE
    from app.ai_providers.nano_banana_adapter import NanoBananaImageGenerationAdapter
    from app.services.reference_selection import create_reference_set_from_ids
    from app.services.quality_engine import assess_candidate
    from app.models.image_validation_result import ImageValidationResult
    from app.services.cost_estimation import estimate_image_cost_usd
    from app.slideshow_stages.base import StageResult
    from app.slideshow_stages.creative_specification_stage import resolve_primary_appearance
    from app.stages.execution import start_analysis_run, mark_succeeded
    from app.prompts import generation as _generation_prompts
    from app import storage
    from app.benchmark import corpus as corpuslib

    tag = f"{slide.slideshow_id[:8]} idx {slide.slide_index}"
    appearance = resolve_primary_appearance(slide.current_product_appearances)
    product = db.get(Product, appearance.product_id) if appearance else None
    creative_spec = (
        db.get(CreativeSpecification, slide.current_creative_specification_id)
        if slide.current_creative_specification_id else None
    )
    if creative_spec is None:
        return {"error": f"{tag}: no current Creative Specification (run analysis first)"}

    # ---- FREEZE ----
    try:
        freeze = corpuslib.freeze_case(
            db, slide, corpus_root=corpus_root, models=models,
            candidates=candidates, repo=repo,
        )
    except Exception as exc:
        return {"error": f"{tag}: freeze failed: {type(exc).__name__}: {exc}"}

    frozen = freeze.frozen
    print(f"CASE {freeze.case_id}: {'FROZEN (new)' if freeze.created else 'reused'}  "
          f"aspect={frozen.aspect_ratio}  refs={len(frozen.reference_files)}  strategy={strategy}")
    if freeze.drift:
        print(f"  ⚠ DRIFT: {freeze.drift['diffs']}")

    if freeze_only:
        return {"case_id": freeze.case_id, "created": freeze.created,
                "drift": freeze.drift, "frozen_only": True}

    # Output ratio = the ORIGINAL slide's ratio (snapped to a supported one), not a
    # forced 3:4. Applied to every strategy so generations keep the source shape.
    out_aspect = source_output_aspect(slide, frozen.aspect_ratio)
    print(f"  output aspect: {out_aspect} (from source; frozen was {frozen.aspect_ratio})")

    # ---- choose the generation request by STRATEGY ----
    strategy_prompt = None
    if strategy in ("source_edit", "source_edit_grounded"):
        # Condition on the ORIGINAL slide. Grounded also injects analysis scene facts.
        name = product.display_name if product else "the product"
        scene = getattr(frozen.spec, "scene", None) if getattr(frozen, "spec", None) else None
        if strategy == "source_edit_grounded":
            strategy_prompt = _source_edit_grounded_prompt(name, scene, out_aspect)
        else:
            strategy_prompt = _source_edit_prompt(name, out_aspect)
        request = _source_edit_request(slide, strategy_prompt, out_aspect)
        if request is None:
            return {"error": f"{tag}: {strategy} needs the original slide image, none resolved"}
        print(f"  {strategy}: reference=original slide  prompt_chars={len(strategy_prompt)}")
    else:
        # transformation_plan: the creative-spec pipeline prompt + product references.
        corpuslib.ensure_provider_prompt(freeze.case_root, provider)
        request = frozen.to_generation_request(provider)
        request.aspect_ratio = out_aspect  # keep the source ratio here too

    generation_reference_set = create_reference_set_from_ids(
        db, product.id if product else None, frozen.reference_ids
    ) if product else None
    grs_id = generation_reference_set.id if generation_reference_set else None

    run = corpuslib.RunWriter(
        freeze.case_root, models=models, candidates=candidates,
        repo=repo, drift=freeze.drift, notes=notes,
        strategy=strategy, strategy_prompt=strategy_prompt,
    )
    print(f"  RUN {run.run_id}")

    run_results: dict = {}
    for model in models:
        print(f"  MODEL {model}")
        adapter = NanoBananaImageGenerationAdapter(model=model, provider=provider)
        attempt = GenerationAttempt(
            slide_id=slide.id, creative_specification_id=creative_spec.id,
            generation_reference_set_id=grs_id, quality_mode="benchmark",
            decision_json={"benchmark": True, "model": model,
                           "case_id": freeze.case_id, "run_id": run.run_id},
            retry_of_generation_attempt_id=None,
        )
        db.add(attempt); db.flush()

        model_results = []
        candidates_gi: list[GeneratedImage] = []
        for i in range(candidates):
            rec = {"candidate": i, "model": model, "provider": provider, "strategy": strategy,
                   "generated": False, "validated": False, "validation_error": None,
                   "identity_passed": None, "accepted": None, "rejection_reasons": [],
                   "seed": None, "generation_time_seconds": None, "estimated_cost_usd": None,
                   "attempts": 0}
            image_bytes = None
            # Provider call with transient-error retry (503/timeout/no-image/etc).
            result, attempts_used, gen_exc = _generate_with_retry(adapter, request, max_attempts)
            rec["attempts"] = attempts_used
            if result is None:
                rec["generation_error"] = f"{type(gen_exc).__name__}: {gen_exc}"
                print(f"    cand {i}: GENERATION FAILED after {attempts_used} attempt(s): {gen_exc}")
            else:
                try:
                    image_bytes = result.image_bytes
                    run_a = start_analysis_run(db, slide_id=slide.id,
                                               analysis_type=ANALYSIS_TYPE_GENERATED_IMAGE,
                                               provider=result.provider, model_name=result.model, durable=True)
                    gi = GeneratedImage(
                        analysis_run_id=run_a.id, slideshow_id=slide.slideshow_id, slide_id=slide.id,
                        creative_specification_id=creative_spec.id, generation_reference_set_id=grs_id,
                        generation_attempt_id=attempt.id, candidate_index=i, is_current=False,
                        provider=result.provider, model_name=result.model, prompt_used=result.prompt_used,
                        **_generation_prompts.generated_image_identity(),
                        seed=result.seed, generation_time_seconds=result.generation_time_seconds,
                        file_path="", estimated_cost_usd=estimate_image_cost_usd(result.provider, result.model),
                    )
                    db.add(gi); db.flush()
                    saved = storage.save_generated_image(slide.id, gi.id, result.image_bytes)
                    gi.file_path = str(saved); db.flush()
                    mark_succeeded(db, run_a, provider_call_ms=result.generation_time_seconds * 1000)
                    rec.update(generated=True, seed=result.seed,
                               generation_time_seconds=result.generation_time_seconds,
                               estimated_cost_usd=gi.estimated_cost_usd, generated_image_id=gi.id)
                    candidates_gi.append(gi)
                    print(f"    cand {i}: generated" + (f" (attempt {attempts_used})" if attempts_used > 1 else ""))
                except Exception as exc:
                    rec["generation_error"] = f"persist failed: {type(exc).__name__}: {exc}"
                    print(f"    cand {i}: PERSIST FAILED: {exc}")
            run.save_candidate(model, i, image_bytes=image_bytes, candidate=rec,
                               validation={"validated": False, "validation_error": None,
                                           "note": "pending" if rec["generated"] else "not generated"})
            model_results.append(rec)
        db.commit()

        gi_by_cand = {gi.candidate_index: gi for gi in candidates_gi}
        for rec in model_results:
            if not rec["generated"]:
                continue
            gi = gi_by_cand.get(rec["candidate"])
            validation: dict = {"validated": False, "validation_error": None}
            try:
                assessment = assess_candidate(db, gi)
                if isinstance(assessment, StageResult):
                    rec["validated"] = False
                    rec["validation_error"] = assessment.error
                    validation = {"validated": False, "validation_error": assessment.error,
                                  "state": "validation_service_failed"}
                    print(f"    cand {rec['candidate']}: VALIDATION DID NOT RUN — {str(assessment.error)[:70]}")
                else:
                    rec["validated"] = True
                    rec["accepted"] = bool(assessment.accepted)
                    iv = assessment.image_validation_result_id
                    v = db.get(ImageValidationResult, iv) if iv else None
                    reasons: list[str] = []
                    if v is not None:
                        rec["identity_passed"] = bool(v.identity_passed)
                        for chk in (v.identity_checks_json or []):
                            if not chk.get("preserved"):
                                reasons.append(f"identity/{chk.get('field_name')}: {chk.get('reason')}")
                        for chk in (v.field_checks_json or []):
                            if not chk.get("preserved"):
                                reasons.append(f"detail/{chk.get('field_name')}: {chk.get('reason')}")
                    rec["rejection_reasons"] = reasons
                    rec["photorealism"] = assessment.photorealism_json
                    validation = {
                        "validated": True, "state": "validated",
                        "accepted": rec["accepted"], "identity_passed": rec["identity_passed"],
                        "rejection_reasons": reasons, "photorealism": assessment.photorealism_json,
                        "image_validation_result_id": iv,
                    }
                    print(f"    cand {rec['candidate']}: validated accepted={rec['accepted']} "
                          f"identity_passed={rec['identity_passed']} rejections={len(reasons)}")
            except Exception as exc:
                rec["validated"] = False
                rec["validation_error"] = f"{type(exc).__name__}: {exc}"
                validation = {"validated": False, "validation_error": rec["validation_error"],
                              "state": "validation_raised"}
                print(f"    cand {rec['candidate']}: VALIDATION RAISED — {exc}")
            run.save_candidate(model, rec["candidate"], image_bytes=None,
                               candidate=rec, validation=validation)
        db.commit()
        run_results[model] = model_results

    run.finalize(run_results)
    return {"case_id": freeze.case_id, "created": freeze.created,
            "drift": freeze.drift, "run_id": run.run_id, "results": run_results}
