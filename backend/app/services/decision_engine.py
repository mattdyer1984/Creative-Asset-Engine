"""
Decision Engine — Phase 10.2 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §11). New service,
not a `SlideshowAnalysisStage` - like `image_validation_stage` before
it, its unit of work (one generation attempt) doesn't fit the
"operates on a whole Slideshow" Protocol shape.

**Deliberately the minimal, honest slice of §11's full design, per the
ADR's own phased-implementation note (§19 item 3)**: "proves Autonomous
Quality end-to-end using the *existing* single Product Fidelity
dimension, before Creative/Photorealism/Text Quality exist." What §11
actually describes is much larger - provider selection informed by
real capability eligibility across multiple candidates, photorealism-
favoring provider settings, and *adaptive* retry reasoning that reads
*why* a previous attempt failed (weak identity vs. weak photorealism vs.
a generic creative choice) and changes strategy accordingly. None of
those inputs exist yet (Provider Capability Framework has exactly one
real second candidate and no eligibility-scoring logic yet). Building
adaptive routing against quality signals that don't exist would be
fabricating a decision, not making one - so `retry_reason` is carried
through and persisted (`decision_json`) so a later sub-phase can start
reading it without a schema change, but this sub-phase's own retry loop
(see generate_with_retry.py) only ever passes a generic "no candidate
was accepted" reason - true adaptive re-planning is explicitly future
work.

`creativity_level` (Phase 10.4, §8/§11 Revision #5) is real, not a
placeholder - it's read by Generation Engine and passed straight
through to Creative Intelligence's `optimize_scene_description`. Per
§8's own explicit correction: this is not a dial between "changed" and
"matched" (both endpoints already optimise) - it controls how *far*
from the original staging that optimisation is allowed to reach,
bounded always by the correct context-tier category and every
preserved region staying intact.

`bundle_members` (Phase 10.7, §12's "Bundle Composition" addendum) is
how a caller opts into Bundle Composition - explicit, never inferred
from "this slide has a Listing-resolved Bundle attached" (the ADR's
own explicit instruction). None by default; when given (a list of
`{"product_id": str, "role_in_scene": str}`), it's carried on the
resulting `GenerationPlan` unchanged, and `generate_with_retry`/
`run_bundle_generation_attempt` branch on its presence rather than a
separate mode flag.

`text_strategy` (Phase 10.8, §9) is `None` by default - a real,
deliberate backward-compatibility choice, not a placeholder: `None`
means "the caller hasn't adopted Text Intelligence," and
`compile_generation_request` keeps its original, pre-Phase-10.8
behavior (the model renders `text_overlays` directly) exactly as
before. Only an explicit `"reuse_original" | "ai_rewrite" | "no_text"`
opts into the new flow - once a winner is accepted,
`generate_with_retry` runs Text Intelligence + the Rendering Engine on
it and persists a `FinalOutput`.
"""

from dataclasses import asdict, dataclass

from app.ai_providers.registry import default_registry
from app.services.text_intelligence import TEXT_STRATEGIES

# Fast=1, Balanced=3, Maximum Quality=5+, exactly as §12 specifies.
QUALITY_MODE_CANDIDATE_COUNTS = {"fast": 1, "balanced": 3, "maximum": 5}

CREATIVITY_LEVELS = {"conservative", "bold"}


@dataclass
class GenerationPlan:
    quality_mode: str
    candidate_count: int
    provider: str
    model: str
    creativity_level: str = "conservative"
    retry_of_generation_attempt_id: str | None = None
    retry_reason: str | None = None
    bundle_members: list[dict] | None = None
    text_strategy: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def decide_generation_plan(
    quality_mode: str,
    *,
    creativity_level: str = "conservative",
    retry_of_generation_attempt_id: str | None = None,
    retry_reason: str | None = None,
    bundle_members: list[dict] | None = None,
    text_strategy: str | None = None,
) -> GenerationPlan:
    if quality_mode not in QUALITY_MODE_CANDIDATE_COUNTS:
        raise ValueError(
            f"Unknown quality_mode {quality_mode!r} - must be one of "
            f"{sorted(QUALITY_MODE_CANDIDATE_COUNTS)}"
        )
    if creativity_level not in CREATIVITY_LEVELS:
        raise ValueError(
            f"Unknown creativity_level {creativity_level!r} - must be one of "
            f"{sorted(CREATIVITY_LEVELS)}"
        )
    if text_strategy is not None and text_strategy not in TEXT_STRATEGIES:
        raise ValueError(f"Unknown text_strategy {text_strategy!r} - must be one of {sorted(TEXT_STRATEGIES)}")

    # Only one real provider is ever eligible today - §10's Provider
    # Capability Framework has exactly one second candidate
    # (nano_banana) and no scoring logic yet to choose *between*
    # eligible providers, so this asks the registry for whichever is
    # currently configured rather than fabricating a choice.
    provider = default_registry.image_generation()

    return GenerationPlan(
        quality_mode=quality_mode,
        candidate_count=QUALITY_MODE_CANDIDATE_COUNTS[quality_mode],
        provider=provider.provider,
        model=provider.model,
        creativity_level=creativity_level,
        retry_of_generation_attempt_id=retry_of_generation_attempt_id,
        retry_reason=retry_reason,
        bundle_members=bundle_members,
        text_strategy=text_strategy,
    )
