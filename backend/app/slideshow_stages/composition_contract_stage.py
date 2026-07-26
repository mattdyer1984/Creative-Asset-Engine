"""
Composition Contract Stage (ADR 0001 §9, Package E).

The stage Packages B, C and D were waiting on. Those packages could reason
about zones, spatial ownership and graphic residue - but only for slides
somebody had annotated by hand. This produces a contract from an image, which
is what makes the whole chain reachable on real work.

**The model's answer is validated, never trusted.** A response naming a zone
role outside the closed vocabulary, a relation endpoint that is not a declared
zone, or bounds outside 0..1 is a response that would poison every downstream
decision - and it would do so quietly, because a contract is structure and
structure looks authoritative. Anything unusable is dropped with a recorded
reason, and a contract that loses too much is downgraded to `unknown` rather
than shipped as a confident finding.

Reuses `VisionAnalysisProvider.analyze_creative` unchanged - the same "one
shared capability, many consumers" pattern every other vision-backed stage
follows. Slide-scoped, `is_current` versioned, durable `AnalysisRun`, like
Scene Intelligence.
"""

import logging
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_COMPOSITION_CONTRACT
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.prompts import analysis as _analysis_prompts
from app.services.composition_contract import record_contract
from app.services.composition_schema import (
    CompositionContract,
    Device,
    Relation,
    RelationEdge,
    Zone,
    ZoneRole,
)
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.concurrency import run_concurrently
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

logger = logging.getLogger(__name__)

#: Below this share of zones surviving validation, the contract is not
#: trustworthy enough to route ownership from. Downstream degrades to
#: WP-1.5A wording-only behaviour, which is worse but not wrong.
MINIMUM_ZONE_SURVIVAL = 0.5

COMPOSITION_CONTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "device": {"type": "string", "enum": [str(d) for d in Device]},
        "device_confidence": {"type": "number"},
        "zones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "role": {"type": "string", "enum": [str(r) for r in ZoneRole]},
                    "x_min": {"type": "number"},
                    "y_min": {"type": "number"},
                    "x_max": {"type": "number"},
                    "y_max": {"type": "number"},
                },
                "required": ["id", "role", "x_min", "y_min", "x_max", "y_max"],
                "additionalProperties": False,
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "relation": {"type": "string", "enum": [str(r) for r in Relation]},
                    "object": {"type": "string"},
                },
                "required": ["subject", "relation", "object"],
                "additionalProperties": False,
            },
        },
        "emphasis": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["device", "device_confidence", "zones", "relations", "emphasis"],
    "additionalProperties": False,
}

COMPOSITION_CONTRACT_PROMPT = _analysis_prompts.COMPOSITION_CONTRACT.render()


def build_contract(response: dict) -> tuple[CompositionContract, list[str]]:
    """
    Turn a provider response into a validated contract, plus what was dropped.

    Returns the rejections as well as the contract because a silently
    shortened contract is indistinguishable from a simple layout. A reviewer
    looking at a two-zone contract needs to know whether the slide had two
    zones or the model produced nine and seven were unusable.
    """
    rejected: list[str] = []

    zones: list[Zone] = []
    seen_ids: set[str] = set()
    for raw in response.get("zones") or []:
        zone_id = str(raw.get("id") or "").strip()
        if not zone_id:
            rejected.append("zone with no id")
            continue
        if zone_id in seen_ids:
            rejected.append(f"duplicate zone id {zone_id!r}")
            continue
        try:
            zone = Zone(
                zone_id=zone_id,
                role=ZoneRole(raw["role"]),
                bounds=(
                    float(raw["x_min"]), float(raw["y_min"]),
                    float(raw["x_max"]), float(raw["y_max"]),
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append(f"zone {zone_id!r}: {exc}")
            continue
        seen_ids.add(zone_id)
        zones.append(zone)

    # Endpoints must resolve. An edge naming something undeclared reads as
    # structure and means nothing - the exact defect Package C found in the
    # hand-annotated fixtures, and a model will make it far more often.
    relations: list[RelationEdge] = []
    for raw in response.get("relations") or []:
        subject, obj = str(raw.get("subject", "")), str(raw.get("object", ""))
        if subject not in seen_ids or obj not in seen_ids:
            rejected.append(f"relation {subject!r} -> {obj!r} names an undeclared zone")
            continue
        if subject == obj:
            rejected.append(f"relation from {subject!r} to itself")
            continue
        try:
            relations.append(
                RelationEdge(subject=subject, relation=Relation(raw["relation"]), object=obj)
            )
        except (KeyError, ValueError) as exc:
            rejected.append(f"relation {subject!r} -> {obj!r}: {exc}")

    emphasis = []
    for entry in response.get("emphasis") or []:
        if entry in seen_ids:
            emphasis.append(entry)
        else:
            rejected.append(f"emphasis {entry!r} is not a declared zone")

    try:
        device = Device(response.get("device"))
    except ValueError:
        rejected.append(f"unrecognised device {response.get('device')!r}")
        device = Device.UNKNOWN

    try:
        confidence = min(max(float(response.get("device_confidence", 0.0)), 0.0), 1.0)
    except (TypeError, ValueError):
        rejected.append("device_confidence was not a number")
        confidence = 0.0

    # Too much loss means the response was not understood, whatever survived.
    offered = len(response.get("zones") or [])
    if offered and len(zones) / offered < MINIMUM_ZONE_SURVIVAL:
        rejected.append(
            f"only {len(zones)}/{offered} zones survived validation - device "
            "downgraded to unknown rather than presented as a finding"
        )
        device, confidence = Device.UNKNOWN, 0.0

    contract = CompositionContract(
        device=device, device_confidence=confidence,
        zones=zones, relations=relations, emphasis=emphasis,
    )
    return contract, rejected


class SlideCompositionContractStage:
    name = "composition_contract"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        """
        One contract per slide. Every slide is processed unconditionally -
        layout is a property of the image and does not depend on a product
        appearance, so the same widening as Scene Intelligence applies.
        """
        result: StageResult = StageResult(succeeded=True)
        vision_provider = default_registry.vision()

        def _analyse(slide: Slide):
            image_bytes = Path(slide.stored_file_path).read_bytes()
            usage: dict = {}
            start = time.perf_counter()
            response = vision_provider.analyze_creative(
                image_bytes=image_bytes,
                prompt_spec={
                    "prompt": COMPOSITION_CONTRACT_PROMPT,
                    "schema_name": "composition_contract",
                },
                response_schema=COMPOSITION_CONTRACT_SCHEMA,
                usage_sink=usage,
            )
            return response, (time.perf_counter() - start) * 1000, usage

        outcomes = run_concurrently(slideshow.slides, _analyse)

        for index, slide in enumerate(slideshow.slides):
            analysis_run = start_analysis_run(
                db,
                slide_id=slide.id,
                analysis_type=ANALYSIS_TYPE_COMPOSITION_CONTRACT,
                provider=vision_provider.provider,
                model_name=vision_provider.model,
                durable=True,
            )

            try:
                outcome = outcomes[index]
                if isinstance(outcome, Exception):
                    raise outcome
                response, provider_call_ms, usage = outcome
                contract, rejected = build_contract(response)
                if rejected:
                    logger.warning(
                        "composition contract for slide %s dropped %d item(s): %s",
                        slide.id, len(rejected), "; ".join(rejected[:5]),
                    )
                record_contract(
                    db, slide_id=slide.id, analysis_run_id=analysis_run.id,
                    contract=contract,
                )
            except Exception as exc:
                return mark_failed(db, analysis_run, exc, rollback=True)

            result = mark_succeeded(
                db, analysis_run,
                provider_call_ms=provider_call_ms, usage=usage,
                prompt=_analysis_prompts.COMPOSITION_CONTRACT,
            )

        return result
