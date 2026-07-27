"""
Plan Builder — one responsibility: convert analysis into executable decisions.
No prompt generation, no image work, no OCR repair beyond canonicalisation
(which is a confidence gate, not content invention).
"""
from __future__ import annotations

from .analysis_source import AnalysisSource
from .canonicalize import clean_ocr, extract_commercial_values, classify_text
from .plan import (
    TransformationPlan, SlideDirective, SceneDirective, PlanElement, Invariant, Provenance,
)

# canonical text-safe bands (0..1), used when analysis gives only positional cues
_ZONE_TOP = [0.08, 0.04, 0.92, 0.24]
_ZONE_BOTTOM = [0.08, 0.72, 0.92, 0.95]
_ZONE_BOTTOM_RIGHT = [0.50, 0.72, 0.97, 0.95]


def _mechanisms(narrative, marketing):
    text = (marketing + " " + (narrative or {}).get("arc_summary", "")).lower()
    out = []
    if any(w in text for w in ("sale", "discount", "price", "cheap", "save", "voucher", "%", "-28")):
        out.append("value")
    beats = [s.get("beat") for s in (narrative or {}).get("slides", [])]
    if beats[:1] == ["hook"] and "reveal" in beats:
        out.append("curiosity")
    if any(w in text for w in ("delicious", "every night", "indulgent", "treat", "guilt-free")):
        out.append("product_desirability")
    return out or ["product_desirability"]


def _narrative_allows_product(role: str) -> bool:
    # direct-response rule: the hook withholds the promoted product; the reveal requires it.
    return role != "hook"


def _text_safe_zones(scene_regions: list[dict]) -> list[list]:
    zones = []
    for r in scene_regions:
        notes = (r.get("notes") or "").lower()
        if any(w in notes for w in ("text", "overlay", "copy", "caption")):
            bb = [r.get("x_min"), r.get("y_min"), r.get("x_max"), r.get("y_max")]
            if all(v is not None for v in bb):
                zones.append(bb)
    return zones


def _zone_for(role: str, is_price: bool, scene_zones: list[list]) -> list:
    if is_price:
        return _ZONE_BOTTOM_RIGHT
    if role == "headline" and scene_zones:
        return scene_zones[0]
    if role == "subheadline":
        return _ZONE_BOTTOM
    return _ZONE_TOP


def _scene(fp: dict, scene_regions: list[dict], role: str, product_refs: list[str]) -> SceneDirective:
    gaps = []
    subject_present = any(
        w in (str(fp.get("visual_style", "")) + str(fp.get("layout_and_composition", "")) +
              str(fp.get("visual_hierarchy", ""))).lower()
        for w in ("selfie", "face", "subject", "person", "first-person")
    )
    emotion = fp.get("emotional_appeal") or []
    action = None
    if subject_present:
        vh = str(fp.get("visual_hierarchy", "")) + " " + str(fp.get("layout_and_composition", ""))
        action = "reacting to camera (UGC selfie)" if "selfie" in vh.lower() else "holding/presenting the product"
    concept = " ; ".join(x for x in [fp.get("visual_style"), fp.get("marketing_objective")] if x)
    env = fp.get("background_environment") or ""
    light = fp.get("lighting_style") or ""
    framing = fp.get("layout_and_composition") or ""
    if not concept:
        gaps.append("scene concept (fingerprint.visual_style/marketing_objective missing)")
    if subject_present and not emotion:
        gaps.append("subject emotion (fingerprint.emotional_appeal missing)")
    if not env:
        gaps.append("environment (fingerprint.background_environment missing)")

    # originality levers: concrete change decisions appropriate to the slide
    levers = ["change_environment", "change_lighting"]
    if subject_present:
        levers = ["swap_person", "change_environment", "change_lighting", "change_angle_or_crop"]
    else:
        levers += ["change_composition", "swap_props"]

    refs = [f"product_reference:{r}" for r in product_refs] if product_refs else []
    prov = [Provenance("scene concept & framing", "creative_fingerprints"),
            Provenance("text-safe zones", "scene_analyses")]
    return SceneDirective(
        concept=concept, subject_present=subject_present, subject_action=action,
        subject_emotion=list(emotion), environment=env, lighting=light, framing=framing,
        text_safe_zones=_text_safe_zones(scene_regions), references_provided=refs,
        change_directives=levers, gaps=gaps, provenance=prov,
    )


def build_plan(source: AnalysisSource, slideshow_prefix: str, plan_version: int = 1) -> TransformationPlan:
    sid = source.resolve_slideshow_id(slideshow_prefix)
    slides_meta = source.slides(sid)
    narrative = source.narrative(sid)
    marketing = source.marketing_text(sid)
    beat_by_index = {s.get("slide_index"): s.get("beat") for s in (narrative or {}).get("slides", [])}
    cta_index = (narrative or {}).get("cta_slide_index")
    mechanisms = _mechanisms(narrative, marketing)

    slide_directives, invariants, promoted_on = [], [], []
    all_commercial_values = []

    for meta in slides_meta:
        idx, slide_db = meta["slide_index"], meta["id"]
        role = beat_by_index.get(idx, "unknown")
        fp = source.fingerprint(slide_db)
        scene_regions = source.scene_regions(slide_db)
        appearances = source.product_appearances(slide_db)
        detected = [a for a in appearances if a["is_current"]]

        # --- product presence: NARRATIVE decides, detection is evidence (point 4) ---
        allow = _narrative_allows_product(role)
        detect_present = len(detected) > 0
        prod_prov = [Provenance(f"narrative role={role} => product_allowed={allow}",
                                "narrative_structures:beats")]
        if allow != detect_present:
            prod_prov.append(Provenance(
                "narrative overrides detection (conflict noted)",
                "product_appearances", f"detection_present={detect_present}"))
        if allow:
            promoted_on.append(idx)

        product_refs = source.product_references(detected[0]["product_id"]) if (allow and detected) else []
        scene = _scene(fp, scene_regions, role, product_refs)
        scene_zones = scene.text_safe_zones

        elements, required_ids, physical_bits = [], [], []
        headline_seen = False

        # --- product element (only where narrative allows AND a product exists) ---
        if allow and detected:
            a = detected[0]
            elements.append(PlanElement(
                element_id=f"s{idx}_product", kind="product", label=a["display_name"][:60],
                must_survive=["identity"], should_improve=["environment", "composition", "styling"],
                commercial_importance="critical",
                preservation_mode="product_reference" if product_refs else "identity_constraint",
                reference_ids=product_refs,
                provenance=[Provenance("promoted product on reveal", "narrative_structures:beats"),
                            Provenance(f"identity anchored by {len(product_refs)} reference(s)",
                                       "product_reference_images")]
                + ([] if product_refs else [Provenance("GAP: no reference images to anchor identity",
                                                       "product_reference_images")]),
            ))

        # --- text elements ---
        for i, b in enumerate(source.ocr_blocks(slide_db)):
            raw = (b.get("text") or "").strip()
            if not raw:
                continue
            role_b = (b.get("role") or "other").lower()
            surface = (b.get("surface") or "").lower()
            cleaned, had_noise, residue = clean_ocr(raw)
            cvs = extract_commercial_values(cleaned)
            is_price = bool(cvs) or role_b == "price"
            is_primary_hook = (role == "hook" and role_b == "headline" and not headline_seen)
            if role_b == "headline":
                headline_seen = True

            # on-product feature words → aggregate; ride with the product reference
            if surface == "physical" and role_b == "other" and not is_price:
                physical_bits.append(cleaned)
                continue

            status, notes = classify_text(
                role=role_b, surface=surface, is_primary_hook=is_primary_hook,
                cleaned=cleaned, had_noise=had_noise, residue_suspicious=residue,
                commercial_values=cvs,
            )
            if status == "exact_commercial_value":
                survive, importance = ["exact_text"], "critical"
            elif status == "trusted_exact":
                survive, importance = ["exact_text"], "high"
            else:  # meaning_preserve or uncertain
                survive, importance = ["meaning"], ("medium" if status == "meaning_preserve" else "low")

            # overlay creator copy is composited; anything else the provider renders in-scene
            owner = "composite_layer" if (surface == "overlay" or role_b in
                                          {"headline", "subheadline", "price", "cta"}) else "provider_scene"
            # reserved zone = the block's own OCR bounding box (precise) — canonical band only as fallback
            bb = b.get("bounding_box") or {}
            zone = None
            if owner == "composite_layer":
                if all(k in bb for k in ("x_min", "y_min", "x_max", "y_max")):
                    zone = [bb["x_min"], bb["y_min"], bb["x_max"], bb["y_max"]]
                else:
                    zone = _zone_for(role_b, is_price, scene_zones)

            prov = [Provenance(f"{role_b}/{surface} copy captured", f"ocr_results:{slide_db}:b{i}")]
            for n in notes:
                prov.append(Provenance(n, "canonicalize"))
            if cvs:
                all_commercial_values.extend(cvs)

            el = PlanElement(
                element_id=f"s{idx}_t{i}", kind="text", label=f"{role_b} text",
                verbatim=cleaned, must_survive=survive, commercial_importance=importance,
                text_status=status, commercial_values=cvs, rendering_owner=owner,
                reserved_zone=zone, provenance=prov,
            )
            elements.append(el)
            if status in ("trusted_exact", "exact_commercial_value") and importance in ("high", "critical"):
                required_ids.append(el.element_id)

        if physical_bits:
            elements.append(PlanElement(
                element_id=f"s{idx}_packaging", kind="text", label="on-product feature text",
                verbatim=" / ".join(physical_bits), must_survive=["meaning"],
                commercial_importance="medium", text_status="meaning_preserve",
                rendering_owner="provider_scene",
                provenance=[Provenance("printed on packaging; rides with product reference",
                                       f"ocr_results:{slide_db}", "surface=physical")],
            ))

        slide_directives.append(SlideDirective(
            slide_index=idx, role=role, promoted_product_allowed=allow,
            cta_allowed=(cta_index == idx), scene=scene,
            required_text_element_ids=required_ids, elements=elements,
            originality_levers_required=3, provenance=prod_prov,
        ))

    # --- slideshow-level invariants (properties, not element survival) ---
    invariants.append(Invariant("single_promoted_product", "slideshow", {"distinct_promoted": 1},
                                [Provenance("one promoted product across the set", "product_appearances")]))
    if promoted_on:
        invariants.append(Invariant("product_present_on_reveal", f"slide:{max(promoted_on)}", {"present": True},
                                    [Provenance("reveal must show the product", "narrative_structures:beats")]))
    for d in slide_directives:
        if d.role == "hook":
            invariants.append(Invariant("product_absent_on_hook", f"slide:{d.slide_index}", {"present": False},
                                        [Provenance("hook withholds the product", "narrative_structures:beats")]))
    if all_commercial_values:
        invariants.append(Invariant("commercial_values_present", "slideshow",
                                    {"values": [v["value"] for v in all_commercial_values]},
                                    [Provenance("exact prices/discounts are the mechanism", "canonicalize")]))
    if cta_index is None:
        invariants.append(Invariant("no_cta", "slideshow", {"cta_allowed": False},
                                    [Provenance("arc has no direct CTA", "narrative_structures")]))

    return TransformationPlan(
        slideshow_id=sid, plan_version=plan_version, processing_mode="direct_response",
        mechanisms_to_preserve=mechanisms, slides=slide_directives, invariants=invariants,
    )
