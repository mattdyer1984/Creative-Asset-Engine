"""
Creative Project Profile Stage (ADR 0001 §14, Package E).

WP-1.1 built the profile's persistence, its analysed/user split and its
carry-forward guarantee. Nothing wrote to it. This does.

**Two questions, answered by different means on purpose.**

*What kind of text project is this?* is answered deterministically, from OCR
blocks the pipeline already has plus the source-style classification. It costs
nothing, it is testable without a provider, and it is the answer ownership
routing actually depends on - so it must not be the thing that breaks when a
provider is down.

*What is the type system?* genuinely needs vision: family class, colour roles,
size scale and capability level are not recoverable from text. That call is
made only for projects whose text mode is designed typography. A UGC caption
project has no design typography to read, and paying to be told so is waste -
the benchmark fixtures assert exactly that (`typography_system: null` for
every ugc_photographic case).

**User decisions are never touched.** `record_analysis` carries every `user_*`
field forward; this stage writes `analysed_*` only. Re-running analysis on a
project where someone chose `overlay_policy=remove` must not restore `keep`.
"""

import logging
import time
from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_CREATIVE_PROFILE
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.ocr_result import OCRResult
from app.models.slideshow import Slideshow
from app.prompts import analysis as _analysis_prompts
from app.services.creative_project_profile import record_analysis
from app.services.profile_schema import (
    BlockClassificationEvidence,
    CapabilityLevel,
    ClassificationEvidence,
    FamilyClass,
    TextMode,
    TextRole,
    TypographySystem,
)
from app.services.source_style import RenderingFamily, classify_source_style
from app.services.text_classification import REVIEW_CONFIDENCE, TextClass, classify_block
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

logger = logging.getLogger(__name__)

#: Share of classified blocks that must agree before the project mode is
#: called with confidence. Below this the mode is still recorded - a default
#: is better than nothing for routing - but the confidence says otherwise.
_MODE_MAJORITY = 0.6

# OpenAI structured outputs (strict mode) impose two constraints this schema
# has to respect, both found by Phase F running against the real provider -
# every unit test passed, because a fake does not validate what it is handed.
#
# 1. `required` must list EVERY property, at every level. A missing one is a
#    400, not a degraded response.
# 2. Open-ended maps are not expressible. `additionalProperties: {schema}` is
#    rejected; strict mode demands `additionalProperties: false` and a fixed
#    key set.
#
# The domain model keeps its open role maps - ADR §10 made them open on
# purpose, so a design's OWN roles can be named rather than squeezed into a
# fixed vocabulary. Only the WIRE shape changes: roles travel as arrays of
# {role, ...} and `build_typography_system` rebuilds the maps on receipt.
# That is a transport concern, not a modelling one.
def _named_array(item_properties: dict, key: str = "role") -> dict:
    """An open map, expressed as the array strict mode can actually carry."""
    properties = {key: {"type": "string"}, **item_properties}
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TYPOGRAPHY_SYSTEM_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_family_class": {"type": "string", "enum": [str(f) for f in FamilyClass]},
        "secondary_family_class": {
            "type": ["string", "null"], "enum": [str(f) for f in FamilyClass] + [None],
        },
        "capability_level": {"type": "string", "enum": [str(c) for c in CapabilityLevel]},
        "colour_roles": _named_array({"colour": {"type": "string"}}),
        "text_roles": _named_array({
            "family_class": {"type": "string", "enum": [str(f) for f in FamilyClass]},
            "weight": {"type": "string"},
            "italic": {"type": "boolean"},
            "case": {"type": "string"},
            "colour_role": {"type": "string"},
            "alignment": {"type": "string"},
            "size_ratio": {"type": "number"},
            "tracking": {"type": "number"},
            "line_height": {"type": "number"},
        }),
        "size_scale": _named_array({"ratio": {"type": "number"}}, key="name"),
    },
    "required": [
        "primary_family_class", "secondary_family_class", "capability_level",
        "colour_roles", "text_roles", "size_scale",
    ],
    "additionalProperties": False,
}

TYPOGRAPHY_SYSTEM_PROMPT = _analysis_prompts.TYPOGRAPHY_SYSTEM.render()


def _blocks_of(db: Session, slide) -> list[dict]:
    """The slide's current OCR blocks, or none. Read by id, not relationship -
    the `current_*_id` pointers are plain columns by design."""
    if slide.current_ocr_result_id is None:
        return []
    ocr = db.get(OCRResult, slide.current_ocr_result_id)
    if ocr is None:
        return []
    return list(ocr.structured_blocks_json or [])


def infer_text_mode(
    slides_blocks: list[list[dict]], style_family: RenderingFamily | None
) -> tuple[TextMode, float, ClassificationEvidence]:
    """
    Decide the project's DEFAULT interpretation of its text (ADR §12.1).

    Counts only blocks whose class actually distinguishes the two modes.
    Product-native and environmental text appears in both kinds of project
    and says nothing about which this is - including it would let a slide
    full of packaging outvote the one designed headline that decides it.

    The source style breaks ties rather than deciding: an illustrated or
    rendered source is far more likely to be a designed creative, but a
    photographic source is perfectly capable of carrying designed type.
    """
    evidence_blocks: list[BlockClassificationEvidence] = []
    counts: Counter[TextClass] = Counter()

    for blocks in slides_blocks:
        for block in blocks:
            classification = classify_block(block)
            evidence_blocks.append(
                BlockClassificationEvidence(
                    text=(block.get("text") or "")[:120],
                    text_class=str(classification.text_class),
                    confidence=classification.confidence,
                    reasons=list(classification.reasons),
                    needs_review=classification.confidence < REVIEW_CONFIDENCE,
                )
            )
            if classification.text_class in (
                TextClass.DESIGNED_TYPOGRAPHY, TextClass.PLATFORM_CAPTION
            ):
                counts[classification.text_class] += 1

    designed = counts[TextClass.DESIGNED_TYPOGRAPHY]
    caption = counts[TextClass.PLATFORM_CAPTION]
    deciding = designed + caption
    reasons: list[str] = [
        f"{designed} block(s) read as designed typography, {caption} as platform caption",
    ]

    if deciding == 0:
        # No block distinguishes the modes. The style is all we have, and
        # saying so is better than presenting a coin flip as a finding.
        if style_family in (RenderingFamily.ILLUSTRATED, RenderingFamily.RENDER):
            reasons.append(f"no deciding text; {style_family} source suggests a designed creative")
            mode, confidence = TextMode.DESIGNED_TYPOGRAPHY, 0.4
        else:
            reasons.append("no deciding text and no style signal - defaulting to caption")
            mode, confidence = TextMode.PLATFORM_CAPTION, 0.2
        return mode, confidence, ClassificationEvidence(
            blocks=evidence_blocks, project_mode_reasons=reasons
        )

    if designed >= caption:
        mode, share = TextMode.DESIGNED_TYPOGRAPHY, designed / deciding
    else:
        mode, share = TextMode.PLATFORM_CAPTION, caption / deciding

    confidence = share
    if style_family in (RenderingFamily.ILLUSTRATED, RenderingFamily.RENDER):
        if mode is TextMode.DESIGNED_TYPOGRAPHY:
            confidence = min(confidence + 0.1, 1.0)
            reasons.append(f"{style_family} source agrees with designed typography")
        else:
            reasons.append(
                f"{style_family} source would suggest a designed creative - "
                "the blocks say otherwise and the blocks win"
            )
    if share < _MODE_MAJORITY:
        reasons.append(
            f"only {share:.0%} of deciding blocks agree - recorded as the default, "
            "not as a confident finding"
        )

    return mode, round(confidence, 3), ClassificationEvidence(
        blocks=evidence_blocks, project_mode_reasons=reasons
    )


def _as_map(value, key: str = "role") -> dict[str, dict]:
    """
    Normalise the wire shape back to the domain shape.

    Accepts the array form strict structured outputs require, and the plain
    map form, which is what the domain model uses and what a caller handing
    back a stored system would supply.
    """
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    result: dict[str, dict] = {}
    for entry in value or []:
        if isinstance(entry, dict) and entry.get(key):
            name = str(entry[key])
            result[name] = {k: v for k, v in entry.items() if k != key}
    return result


def build_typography_system(response: dict) -> TypographySystem:
    """
    Turn a provider response into a type system, dropping what will not
    validate rather than coercing it into something plausible.
    """
    text_roles: dict[str, TextRole] = {}
    for name, raw in _as_map(response.get("text_roles")).items():
        try:
            text_roles[name] = TextRole.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - one bad role must not lose the rest
            logger.warning("typography role %r dropped: %s", name, exc)

    try:
        primary = FamilyClass(response.get("primary_family_class"))
    except ValueError:
        primary = FamilyClass.GROTESQUE
        logger.warning(
            "unrecognised primary family %r - falling back to grotesque",
            response.get("primary_family_class"),
        )
    secondary_raw = response.get("secondary_family_class")
    try:
        secondary = FamilyClass(secondary_raw) if secondary_raw else None
    except ValueError:
        secondary = None

    try:
        capability = CapabilityLevel(response.get("capability_level"))
    except ValueError:
        # L1 is the optimistic answer, and claiming it wrongly produces a
        # flat recreation of integrated typography. Unknown means L3: route
        # it away from the deterministic renderer rather than into it.
        capability = CapabilityLevel.L3
        logger.warning(
            "unrecognised capability level %r - treated as L3 so it is not "
            "sent to the L1 renderer", response.get("capability_level"),
        )

    return TypographySystem(
        primary_family_class=primary,
        secondary_family_class=secondary,
        capability_level=capability,
        colour_roles={
            name: str(entry.get("colour", entry) if isinstance(entry, dict) else entry)
            for name, entry in _as_map(response.get("colour_roles")).items()
        },
        text_roles=text_roles,
        size_scale={
            name: float(value)
            for name, value in (
                (n, e.get("ratio") if isinstance(e, dict) else e)
                for n, e in _as_map(response.get("size_scale"), key="name").items()
            )
            if isinstance(value, (int, float))
        },
    )


class SlideshowCreativeProfileStage:
    name = "creative_profile"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        """
        One profile per slideshow. Slideshow-scoped because text mode is a
        project property (ADR §12.1) - a slideshow whose slides disagreed
        about it would be two creatives, not one.
        """
        fingerprint = None
        primary = slideshow.primary_slide
        if primary is not None and primary.current_creative_fingerprint_id is not None:
            row = db.get(CreativeFingerprint, primary.current_creative_fingerprint_id)
            fingerprint = row.structured_json if row is not None else None

        style = classify_source_style(fingerprint)
        mode, confidence, evidence = infer_text_mode(
            [_blocks_of(db, slide) for slide in slideshow.slides], style.family
        )
        evidence.project_mode_reasons.append(
            f"source style {style.style} ({style.family}), confidence {style.confidence:.2f}"
        )

        needs_typography = mode is TextMode.DESIGNED_TYPOGRAPHY
        provider = default_registry.vision() if needs_typography else None

        analysis_run = start_analysis_run(
            db,
            slideshow_id=slideshow.id,
            analysis_type=ANALYSIS_TYPE_CREATIVE_PROFILE,
            provider=provider.provider if provider else "local",
            model_name=provider.model if provider else "deterministic",
            durable=True,
        )

        typography: TypographySystem | None = None
        provider_call_ms: float | None = None
        usage: dict = {}

        try:
            if needs_typography and primary is not None:
                image_bytes = Path(primary.stored_file_path).read_bytes()
                start = time.perf_counter()
                response = provider.analyze_creative(
                    image_bytes=image_bytes,
                    prompt_spec={
                        "prompt": TYPOGRAPHY_SYSTEM_PROMPT,
                        "schema_name": "typography_system",
                    },
                    response_schema=TYPOGRAPHY_SYSTEM_SCHEMA,
                    usage_sink=usage,
                )
                provider_call_ms = (time.perf_counter() - start) * 1000
                typography = build_typography_system(response)

            record_analysis(
                db,
                slideshow_id=slideshow.id,
                analysis_run_id=analysis_run.id,
                primary_text_mode=mode,
                text_mode_confidence=confidence,
                typography_system=typography,
                classification_evidence=evidence,
            )
        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        # No ProviderCall row when no provider was called. Cost reporting
        # reads ProviderCall exclusively, so emitting a zero-cost row for
        # deterministic work would put a call in the ledger that never
        # happened - the opposite of what that ledger is for.
        return mark_succeeded(
            db, analysis_run,
            provider_call_ms=provider_call_ms, usage=usage,
            emit_provider_call=provider_call_ms is not None,
            prompt=_analysis_prompts.TYPOGRAPHY_SYSTEM if needs_typography else None,
        )
