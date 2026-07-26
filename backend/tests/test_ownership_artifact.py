"""Persisted text ownership (ADR 0001, Package A)."""

import pytest

from app.models.analysis_run import AnalysisRun
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.ownership_artifact import (
    OWNERSHIP_MODEL_VERSION,
    OwnershipIntegrityError,
    decisions_of,
    get_current,
    record_ownership,
)
from app.services.profile_schema import TextMode
from app.services.text_ownership import Owner, decide_ownership

BLOCKS = [
    {"text": "1.", "surface": "overlay"},
    {"text": "Your upper back", "surface": "overlay"},
    {"text": "Shoulders keep falling forward", "surface": "overlay"},
]


@pytest.fixture
def slide(db_session):
    show = Slideshow()
    db_session.add(show)
    db_session.flush()
    row = Slide(slideshow_id=show.id, slide_index=0, stored_file_path="/tmp/x.jpg",
                original_filename="x.jpg", source_type="upload",
                source_locator="x.jpg")
    db_session.add(row)
    db_session.flush()
    return row


def _run(db_session) -> str:
    run = AnalysisRun(analysis_type="text_ownership", provider="gemini",
                      model_name="test", status="succeeded")
    db_session.add(run)
    db_session.flush()
    return run.id


def _plan():
    return decide_ownership(BLOCKS, project_text_mode=TextMode.DESIGNED_TYPOGRAPHY)


def test_ownership_is_persisted_with_its_effective_policies(db_session, slide):
    artifact = record_ownership(
        db_session, slide_id=slide.id, analysis_run_id=_run(db_session), plan=_plan(),
        project_profile_id="profile-1", effective_copy_policy="preserve_verbatim",
        effective_overlay_policy="keep",
    )
    assert artifact.is_current
    assert artifact.ownership_model_version == OWNERSHIP_MODEL_VERSION
    assert artifact.project_profile_id == "profile-1"
    assert all(b["effective_copy_policy"] == "preserve_verbatim" for b in artifact.blocks_json)


def test_re_analysis_supersedes_and_history_stays_inspectable(db_session, slide):
    first = record_ownership(db_session, slide_id=slide.id,
                             analysis_run_id=_run(db_session), plan=_plan())
    second = record_ownership(db_session, slide_id=slide.id,
                              analysis_run_id=_run(db_session), plan=_plan())
    db_session.flush()
    assert not first.is_current
    assert get_current(db_session, slide.id) is second
    assert first.blocks_json, "the superseded artifact stays readable"


def test_decisions_round_trip(db_session, slide):
    artifact = record_ownership(db_session, slide_id=slide.id,
                                analysis_run_id=_run(db_session), plan=_plan())
    db_session.flush()
    restored = decisions_of(artifact)
    assert [d.block_id for d in restored] == [d.block_id for d in _plan().decisions]
    assert all(d.owner is Owner.TYPOGRAPHY for d in restored)
    assert all(d.source_ocr_block_id for d in restored)


def test_a_duplicated_block_is_refused(db_session, slide):
    plan = _plan()
    plan.decisions.append(plan.decisions[0].model_copy())
    with pytest.raises(OwnershipIntegrityError, match="more than once"):
        record_ownership(db_session, slide_id=slide.id,
                         analysis_run_id=_run(db_session), plan=plan)


def test_every_recognised_block_must_be_accounted_for(db_session, slide):
    plan = _plan()
    plan.decisions.pop()
    with pytest.raises(OwnershipIntegrityError, match="accounted for"):
        record_ownership(
            db_session, slide_id=slide.id, analysis_run_id=_run(db_session), plan=plan,
            expected_block_ids={"block-0", "block-1", "block-2"},
        )


def test_evidence_is_retained_for_review(db_session, slide):
    artifact = record_ownership(db_session, slide_id=slide.id,
                                analysis_run_id=_run(db_session), plan=_plan())
    numeral = artifact.blocks_json[0]
    assert numeral["evidence"], "the classifier's working must survive persistence"
