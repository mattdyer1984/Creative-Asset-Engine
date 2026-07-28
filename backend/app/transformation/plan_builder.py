"""
Plan Builder — one responsibility: convert analysis into executable decisions.
No prompt generation, no image work, no OCR repair beyond canonicalisation
(which is a confidence gate, not content invention).
"""
from __future__ import annotations

import re

from .analysis_source import AnalysisSource
from .canonicalize import clean_ocr, extract_commercial_values, classify_text
from math import gcd

from .plan import (
    TransformationPlan, SlideDirective, SceneDirective, PlanElement, Invariant, Provenance, Canvas,
)

# Fixed output policy (decided 2026-07-27): every generated image is 3:4.
OUTPUT_ASPECT = "3:4"


def _aspect_of(dims) -> str | None:
    """Measured source dims {"width","height"} → a reduced "W:H" string, or None."""
    if not dims:
        return None
    w, h = dims.get("width"), dims.get("height")
    if not w or not h:
        return None
    g = gcd(int(w), int(h)) or 1
    return f"{int(w) // g}:{int(h) // g}"


def _canvas_for(source, slide_db) -> Canvas:
    """Canvas = the decided output aspect + the measured source evidence. The source
    aspect is evidence (may be a gap); the output is the fixed 3:4 target. Nothing is
    invented — an unknown source is recorded, and output still flows from here."""
    dims = source.source_dims(slide_db) if hasattr(source, "source_dims") else None
    src_aspect = _aspect_of(dims)
    prov = [Provenance("output aspect (fixed policy)", "canvas_policy", f"output={OUTPUT_ASPECT}")]
    gaps = []
    if dims and src_aspect:
        prov.append(Provenance("source aspect measured", "slides.stored_file_path",
                               f"{dims['width']}x{dims['height']} => {src_aspect}"))
        fit = "identity" if src_aspect == OUTPUT_ASPECT else "retarget"
    else:
        gaps.append("source dimensions not captured; output aspect uses the fixed target only")
        fit = "target_only"
    return Canvas(
        output_aspect=OUTPUT_ASPECT,
        source_width=(dims or {}).get("width"), source_height=(dims or {}).get("height"),
        source_aspect=src_aspect, fit_behaviour=fit, provenance=prov, gaps=gaps,
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


def _narrative_reveals_identity(role: str) -> bool:
    """Does this beat REVEAL/anchor the promoted-offer identity?

    Distinct from visual presence. The hook opens a curiosity gap: even when the
    product happens to be visible (e.g. on a shop shelf), the hook does not yet
    anchor it as the promoted offer (no reference identity, no price/brand anchor).
    Every other beat reveals it.
    """
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


# Deterministic renderers = the text is composited/rendered by us, exactly. Only such
# text can carry a "required exact" obligation; provider-scene text is rendered in-image.
_DETERMINISTIC_OWNERS = {"composite_layer", "interface_renderer"}


def _owner_from_artifact(own: dict | None) -> str | None:
    """Authoritative rendering owner from the ownership artifact's handling_policy.
    optional_overlay (a separable creator caption) -> composited by us;
    preserve_visual_role (owned by the image: product/scene) -> rendered in-asset.
    None when the artifact is absent/undecided (caller falls back + records it)."""
    hp = (own or {}).get("handling_policy")
    if hp == "optional_overlay":
        return "composite_layer"
    if hp == "preserve_visual_role":
        return "provider_scene"
    return None


# Body-region vocabularies. Matched on \b prefixes so "forehead" != "head" and
# "chest of drawers" is excluded upstream (subject-region gating), not here.
_FACE = ("face", "head", "hairline")
_TORSO = ("torso", "shoulder", "shoulders", "chest", "waist", "hip", "hips", "neckline", "neck", "bust")
_HAND = ("hand", "hands", "finger", "fingers", "forearm", "wrist", "palm", "fist", "thumb")
_LEGS = ("leg", "legs", "feet", "foot", "ankle", "ankles", "sock", "socks", "calf", "shin", "thigh", "thighs", "knee", "knees")
_WHOLE = ("full body", "full-length", "full length", "whole body", "standing", "hunched", "head to toe", "head-to-toe")
_PERSON = ("person", "people", "presenter", "wearer", "model", "figure", "individual")
# A generic person word alone is NOT a strong body signal; parts and whole-body are.
_STRONG_BODY = _FACE + _TORSO + _HAND + _LEGS + _WHOLE

# Interaction verbs (families → canonical gerund). Detection order: wear, use, hold.
_WEAR = ("wear", "wears", "wearing", "worn")
_USE = ("using", "use", "uses", "typing", "scrolling", "viewing", "operating", "pressing")
_HOLD = ("hold", "holds", "holding", "grip", "gripping", "gripped", "presenting",
         "showing", "displaying", "offering", "cradling", "clutching")

# Objects a subject may interact with. NON_PRODUCT props are NEVER the promoted
# product; PRODUCT_OBJ nouns resolve to it. Non-product is scanned first so a
# banknote is reported as a banknote, never silently renamed "the product".
_NON_PRODUCT_OBJ = ("banknote", "money", "cash", "cheque", "credit card", "card",
                    "smartphone", "phone", "mobile", "handbag", "shopping bag", "tote", "bag",
                    "receipt", "wallet", "purse", "coin", "ticket", "voucher", "mug", "remote", "note")
_PRODUCT_OBJ = ("tub", "cup", "tube", "shoe", "shoes", "clog", "clogs", "footwear", "sneaker",
                "trainer", "box", "package", "packaging", "bottle", "jar", "tin", "can",
                "item", "goods", "product")


def _has(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(w)}", text) for w in words)


def _first_match(text: str, words):
    for w in words:
        if re.search(rf"\b{re.escape(w)}", text):
            return w
    return None


def _subject_from_regions(scene_regions: list[dict]):
    """(present, extent, action, relation) derived from analysis scene regions.

    First-loss fix (remediation map): subject semantics come from the region
    labels/notes that already name the visible body region and interaction, NOT
    from fingerprint prose keywords. Extent uncertainty is preserved.

    Entity-binding discipline: the OBSERVED action names whatever object analysis
    actually reports (a banknote stays a banknote). The product_subject_relation
    is set ONLY when the evidence explicitly links the interaction to the promoted
    product (the note literally references "the product") and the interacted object
    is not a known non-product prop. Otherwise it is None (an explicit gap state) —
    holding/wearing/using is never inferred from a verb alone.
    """
    notes = []
    for r in scene_regions:
        rt = (r.get("region_type") or "").lower()
        note = (r.get("notes") or "").lower()
        # human_subject regions are trusted; primary/secondary regions are often
        # mislabelled (overlay text, a machine, "chest of drawers") so they only
        # count when they carry a clear body word.
        if rt == "human_subject" or (
                rt in ("primary_subject", "secondary_subject") and _has(note, _STRONG_BODY)):
            notes.append(note)
    if not notes:
        return False, None, None, None
    alln = " ".join(notes)

    # --- visible body extent (parts win over a generic 'person') ---
    has_face = _has(alln, _FACE)
    has_torso = _has(alln, _TORSO)
    has_hand = _has(alln, _HAND)
    has_legs = _has(alln, _LEGS)
    if _has(alln, _WHOLE) or (has_torso and has_legs) or (has_face and has_legs):
        extent = "full figure"
    elif has_torso:
        extent = "head and shoulders" if has_face else "upper body"
    elif has_face and has_hand:
        extent = "face and hand"
    elif has_face:
        extent = "head and shoulders"
    elif has_hand and has_legs:
        extent = "full figure"
    elif has_hand:
        extent = "hand and forearm" if "forearm" in alln else "hand"
    elif has_legs:
        extent = "lower legs"
    elif _has(alln, _PERSON):
        extent = "full figure"
    else:
        extent = "unspecified"

    # --- observed interaction (verb + the object analysis actually names) ---
    if _has(alln, _WEAR) or "in use" in alln or "on the feet" in alln or "on the foot" in alln:
        verb = "wearing"
    elif _has(alln, _HOLD):
        verb = "holding"
    elif _has(alln, _USE):
        verb = "using"
    else:
        verb = None

    non_product_obj = _first_match(alln, _NON_PRODUCT_OBJ)
    obj = non_product_obj or _first_match(alln, _PRODUCT_OBJ)
    explicit_product = re.search(r"\bproduct\b", alln) is not None

    if verb and obj:
        action = f"{verb} the {obj}"
    elif verb:
        action = f"{verb} the product" if explicit_product else verb
    else:
        action = None

    # Relation is bound only on an explicit product link, never on a prop.
    if verb and explicit_product and not non_product_obj:
        relation = verb
    else:
        relation = None

    return True, extent, action, relation


def _scene(fp: dict, scene_regions: list[dict], role: str, product_refs: list[str]) -> SceneDirective:
    gaps = []
    # Subject semantics from scene regions (extent + action), not fingerprint prose.
    subject_present, subject_extent, action, relation = _subject_from_regions(scene_regions)
    if subject_present and subject_extent == "unspecified":
        gaps.append("subject extent not determinable from scene-region notes")
    # Explicit uncertain state: an interaction was observed but could not be bound
    # to the promoted product (object is a prop, or the product link is implicit).
    # This is a RESOLVED decision (relation deliberately None with the observed action
    # preserved), NOT missing-essential-info — so it is recorded as provenance, not a
    # blocking Plan-sufficiency gap.
    relation_unresolved = (subject_present and action and relation is None
                           and "the product" not in action)
    emotion = fp.get("emotional_appeal") or []
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
    if relation_unresolved:
        prov.append(Provenance(
            "subject_product_relation_unresolved", "scene_analyses",
            "interacted object not confirmed as the promoted product; observed action "
            "preserved and product relationship left None (resolved, not missing)"))
    return SceneDirective(
        concept=concept, subject_present=subject_present, subject_action=action,
        subject_extent=subject_extent, product_subject_relation=relation,
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
    promoted_product_ids = set()          # distinct promoted products across the set (evidence, not "== 1")
    all_commercial_values = []

    for meta in slides_meta:
        idx, slide_db = meta["slide_index"], meta["id"]
        role = beat_by_index.get(idx, "unknown")
        fp = source.fingerprint(slide_db)
        scene_regions = source.scene_regions(slide_db)
        appearances = source.product_appearances(slide_db)
        detected = [a for a in appearances if a["is_current"]]

        # --- product presence vs identity reveal: two ORTHOGONAL facts (point 4) ---
        # These are kept as two SEPARATE evidence sources and never blurred:
        #   observed_visual_presence — what analysis actually detected (evidence)
        #   required_visual_presence — what the narrative reveal beat demands
        # The actionable flag is their union, but the provenance stays truthful:
        # a reveal with no detection is recorded as required-not-observed + a
        # conflict, NOT silently promoted to "observed present".
        # IDENTITY REVEAL is a third, narrative-led fact (anchoring the offer).
        observed_present = len(detected) > 0
        required_present = role == "reveal"          # the reveal beat demands the product
        identity_revealed = _narrative_reveals_identity(role)
        product_present = observed_present or required_present
        presence_conflict = required_present and not observed_present
        prod_prov = [Provenance(
            "product presence", "product_appearances/narrative_structures:beats",
            f"observed_visual_presence={observed_present} "
            f"required_visual_presence={required_present} "
            f"identity_revealed={identity_revealed} role={role}")]
        if presence_conflict:
            prod_prov.append(Provenance(
                "product_presence_conflict", "narrative_structures:beats",
                "reveal requires the promoted product but analysis detected no appearance "
                "(observed_visual_presence=False required_visual_presence=True; "
                "source=narrative reveal requirement) — the request may still require the "
                "product to appear, but no detected appearance anchors it"))
        if role == "hook" and product_present:
            prod_prov.append(Provenance(
                "promoted_identity_withheld_on_hook", "product_appearances",
                f"product visibly present but promoted identity not anchored "
                f"(observed_visual_presence={observed_present})"))
        if identity_revealed and product_present:
            promoted_on.append(idx)
            for a in detected:
                promoted_product_ids.add(a["product_id"])

        # References anchor the promoted identity — attached ONLY where identity is revealed.
        # Preserve the WHOLE collection of appearances, never collapse to detected[0]:
        # each promoted product contributes its own references.
        product_refs = []
        if identity_revealed and detected:
            for a in detected:
                product_refs.extend(source.product_references(a["product_id"]))
        scene = _scene(fp, scene_regions, role, product_refs)
        scene_zones = scene.text_safe_zones

        elements, required_ids, physical_bits = [], [], []
        headline_seen = False
        # Authoritative text-ownership artifact, keyed by OCR block index. Consumed for
        # rendering-owner (never re-derived from OCR when present).
        slide_own = source.text_ownership(slide_db) if hasattr(source, "text_ownership") else {}

        # --- product element (wherever the product is visibly present) ---
        # Identity is ANCHORED only where the narrative reveals it. On a hook where
        # the product merely appears (e.g. on a shelf), it survives by PRESENCE so
        # generation keeps it, without forcing the anchored promoted-offer identity.
        if product_present and detected:
            # ONE product element per current appearance — the authoritative collection is
            # preserved, never collapsed to detected[0]. Single-appearance slides keep the
            # `s{idx}_product` id; multi-product slides get `s{idx}_product{j}`.
            multi = len(detected) > 1
            for j, a in enumerate(detected):
                eid = f"s{idx}_product{j}" if multi else f"s{idx}_product"
                if identity_revealed:
                    refs = source.product_references(a["product_id"])
                    elements.append(PlanElement(
                        element_id=eid, kind="product", label=a["display_name"][:60],
                        must_survive=["identity"], should_improve=["environment", "composition", "styling"],
                        commercial_importance="critical",
                        preservation_mode="product_reference" if refs else "identity_constraint",
                        reference_ids=refs,
                        provenance=[Provenance("promoted product identity revealed", "narrative_structures:beats"),
                                    Provenance(f"identity anchored by {len(refs)} reference(s)",
                                               "product_reference_images")]
                        + ([] if refs else [Provenance("GAP: no reference images to anchor identity",
                                                       "product_reference_images")]),
                    ))
                else:
                    elements.append(PlanElement(
                        element_id=eid, kind="product", label=a["display_name"][:60],
                        must_survive=["presence"], should_improve=["environment", "composition", "styling"],
                        commercial_importance="medium",
                        preservation_mode="identity_constraint", reference_ids=[],
                        provenance=[Provenance("product visibly present but promoted identity withheld "
                                               "(hook curiosity gap)", "narrative_structures:beats"),
                                    Provenance("shown in-context; not anchored to reference identity",
                                               "product_appearances")],
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

            # Authoritative ownership for this OCR block (by index), consumed below.
            own = slide_own.get(i)
            art_owner = _owner_from_artifact(own)

            # on-product feature words → aggregate; ride with the product reference.
            # But NEVER aggregate a block the ownership artifact marks a separable
            # caption — that would let the OCR heuristic override the artifact.
            if (surface == "physical" and role_b == "other" and not is_price
                    and art_owner != "composite_layer"):
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

            # Rendering owner: CONSUME the authoritative ownership artifact when present;
            # fall back to the OCR surface/role heuristic ONLY when it is absent/undecided,
            # and record that fallback explicitly (never silently as though it were evidence).
            if art_owner:
                owner = art_owner
                owner_prov = Provenance(
                    "rendering owner consumed from ownership artifact",
                    "text_ownership_artifacts",
                    f"block-{i}: owner={own.get('owner')} handling={own.get('handling_policy')}")
            else:
                owner = "composite_layer" if (surface == "overlay" or role_b in
                                              {"headline", "subheadline", "price", "cta"}) else "provider_scene"
                owner_prov = Provenance(
                    "GAP: rendering owner inferred from OCR (ownership artifact absent/undecided)",
                    "ocr_heuristic", f"surface={surface} role={role_b}")
            # reserved zone = the block's own OCR bounding box (precise) — canonical band only as fallback
            bb = b.get("bounding_box") or {}
            zone = None
            if owner == "composite_layer":
                if all(k in bb for k in ("x_min", "y_min", "x_max", "y_max")):
                    zone = [bb["x_min"], bb["y_min"], bb["x_max"], bb["y_max"]]
                else:
                    zone = _zone_for(role_b, is_price, scene_zones)

            prov = [Provenance(f"{role_b}/{surface} copy captured", f"ocr_results:{slide_db}:b{i}"),
                    owner_prov]
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
            # "Required" = must be deterministically composited with exact fidelity. Only
            # text WE render (composite/interface) can carry that obligation. Scene/provider
            # text (e.g. the "£20" printed on the note) keeps its commercial-value evidence
            # but is rendered in-image, not asserted as a required composite overlay.
            if (status in ("trusted_exact", "exact_commercial_value")
                    and importance in ("high", "critical")
                    and owner in _DETERMINISTIC_OWNERS):
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
            slide_index=idx, role=role, promoted_product_allowed=product_present,
            cta_allowed=(cta_index == idx), promoted_identity_revealed=identity_revealed,
            canvas=_canvas_for(source, slide_db),
            scene=scene, required_text_element_ids=required_ids, elements=elements,
            originality_levers_required=3, provenance=prod_prov,
        ))

    # --- slideshow-level invariants (properties, not element survival) ---
    n_promoted = len(promoted_product_ids) or 1
    invariants.append(Invariant("distinct_promoted_products", "slideshow", {"distinct_promoted": n_promoted},
                                [Provenance(f"{n_promoted} distinct promoted product(s) across the set "
                                            "(counted from evidence, not assumed to be one)", "product_appearances")]))
    if promoted_on:
        invariants.append(Invariant("product_present_on_reveal", f"slide:{max(promoted_on)}", {"present": True},
                                    [Provenance("reveal must show the product", "narrative_structures:beats")]))
    for d in slide_directives:
        if d.role != "hook":
            continue
        if not d.promoted_product_allowed:
            # genuinely absent (e.g. banknote / reaction hook): withhold the product entirely
            invariants.append(Invariant("product_absent_on_hook", f"slide:{d.slide_index}", {"present": False},
                                        [Provenance("hook withholds the absent product", "narrative_structures:beats")]))
        else:
            # product visibly present on the hook: keep it, but the promoted identity is not revealed here
            invariants.append(Invariant("promoted_identity_withheld_on_hook", f"slide:{d.slide_index}",
                                        {"identity_revealed": False, "present": True},
                                        [Provenance("hook shows the product in-context but does not anchor "
                                                    "the promoted-offer identity", "narrative_structures:beats")]))
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
