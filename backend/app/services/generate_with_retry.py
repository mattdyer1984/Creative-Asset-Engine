"""
Automatic Retry Loop — Phase 10.2 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §14). Chains
Decision Engine -> Generation Engine -> Quality Engine, per
`GenerationAttempt.retry_of_generation_attempt_id`, until some
candidate is accepted or `max_retries` is hit.

**Deliberately the "basic" loop, per the ADR's own phased framing
(§19 item 3)** - not yet the fully adaptive retry §11 describes (reading
*why* a previous attempt failed - weak identity vs. weak photorealism
vs. a generic creative choice - and changing strategy accordingly),
since none of those richer failure signals exist yet (Photorealism and
Creative Intelligence are Phases 10.3/10.4). A retry here always means
"run the Decision Engine again with the same quality_mode and a
generic 'nothing was accepted' reason" - true adaptive re-planning is
explicit future work, not silently claimed here.

Deliberately **not** wired into `SLIDESHOW_STAGE_PIPELINE` or any
background/automatic flow, per §14's own explicit instruction - every
candidate is a real paid provider call (up to
`max_retries + 1` attempts * `candidate_count` candidates each), so
this must stay behind its own explicit, user-triggered endpoint
(`POST .../generate-creative`), never one `POST /analyze` away from
firing.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.creative_specification import CreativeSpecification
from app.models.generated_image import GeneratedImage
from app.models.generation_attempt import GenerationAttempt
from app.models.quality_assessment import QualityAssessment
from app.models.slideshow import Slideshow
from app.services.decision_engine import decide_generation_plan
from app.services.generation_engine import run_generation_attempt
from app.services.quality_engine import assess_candidate
from app.slideshow_stages.base import StageResult

# A small, real bound, not "retry forever" - §14 calls for a
# "configured retry limit," this is Phase 10.2's default value for it.
DEFAULT_MAX_RETRIES = 1


@dataclass
class CandidateAssessment:
    generated_image: GeneratedImage
    quality_assessment: QualityAssessment


@dataclass
class GenerationAttemptOutcome:
    attempt: GenerationAttempt
    candidates: list[CandidateAssessment]


@dataclass
class RetryLoopResult:
    attempts: list[GenerationAttemptOutcome]
    winner: CandidateAssessment | None


def generate_with_retry(
    db: Session, slideshow: Slideshow, quality_mode: str, *, max_retries: int = DEFAULT_MAX_RETRIES
) -> RetryLoopResult | StageResult:
    slide = slideshow.primary_slide
    if slideshow.current_creative_specification_id is None:
        return StageResult(
            succeeded=False,
            error="No Creative Specification available yet - run that stage first.",
        )
    creative_specification = db.get(
        CreativeSpecification, slideshow.current_creative_specification_id
    )
    if creative_specification is None:
        return StageResult(
            succeeded=False,
            error="Creative Specification referenced by the Slideshow no longer exists.",
        )

    attempts: list[GenerationAttemptOutcome] = []
    retry_of_id: str | None = None
    retry_reason: str | None = None

    for _ in range(max_retries + 1):
        plan = decide_generation_plan(
            quality_mode,
            retry_of_generation_attempt_id=retry_of_id,
            retry_reason=retry_reason,
        )
        attempt_result = run_generation_attempt(db, slide, creative_specification, plan)
        if isinstance(attempt_result, StageResult):
            # Can't even start (no product assigned, empty Library) -
            # the same failure would recur on every retry, so stop
            # immediately rather than burning the retry budget on
            # attempts that can never succeed.
            return attempt_result

        candidate_assessments: list[CandidateAssessment] = []
        for candidate in attempt_result.candidates:
            assessment_result = assess_candidate(db, candidate)
            if isinstance(assessment_result, StageResult):
                # This one candidate's validation couldn't run (e.g. no
                # immutable Product Profile fields yet) - treated as a
                # non-accepted candidate, not a fatal error for the
                # whole attempt; other candidates may still validate.
                continue
            candidate_assessments.append(
                CandidateAssessment(generated_image=candidate, quality_assessment=assessment_result)
            )

        attempts.append(
            GenerationAttemptOutcome(attempt=attempt_result.attempt, candidates=candidate_assessments)
        )

        accepted = [c for c in candidate_assessments if c.quality_assessment.accepted]
        if accepted:
            winner = max(accepted, key=lambda c: c.quality_assessment.overall_confidence_score)
            db.query(GeneratedImage).filter(
                GeneratedImage.slide_id == slide.id,
                GeneratedImage.is_current.is_(True),
            ).update({"is_current": False})
            winner.generated_image.is_current = True
            # A real commit - the is_current flip is this loop's last
            # write, with nothing after it to piggyback a commit on
            # (same reasoning as quality_engine.assess_candidate's own
            # fix); a flush-only write here would roll back once the
            # request's session closes, silently leaving no "current"
            # generated image at all despite a real accepted winner.
            db.commit()
            return RetryLoopResult(attempts=attempts, winner=winner)

        retry_of_id = attempt_result.attempt.id
        retry_reason = "No candidate in the previous attempt passed Product Fidelity validation."

    return RetryLoopResult(attempts=attempts, winner=None)
