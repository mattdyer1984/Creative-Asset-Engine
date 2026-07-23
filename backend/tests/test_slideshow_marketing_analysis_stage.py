"""
Unit tests for SlideshowMarketingAnalysisStage (new pipeline, Phase
2.4d) - mirrors tests/test_marketing_analysis_stage.py's coverage.
"""

from sqlalchemy import select

from app.models.analysis_run import AnalysisRun
from app.models.marketing_analysis import MarketingAnalysis
from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
from app.slideshow_stages.marketing_analysis_stage import SlideshowMarketingAnalysisStage
from tests.fakes import FakeAIProviderRegistry, FakeTextGenerationProvider, FakeVisionAnalysisProvider
from tests.test_slide_creative_fingerprint_stage import FINGERPRINT_RESULT


def _build_fingerprint(db_session, slideshow, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    SlideCreativeFingerprintStage().run(db_session, slideshow)


def test_fails_gracefully_without_a_fingerprint(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )

    result = SlideshowMarketingAnalysisStage().run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "No Creative Fingerprint" in result.error


def test_succeeds_and_updates_slideshow(db_session, slideshow_with_slide, monkeypatch):
    _build_fingerprint(db_session, slideshow_with_slide, monkeypatch)

    monkeypatch.setattr(
        "app.slideshow_stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )
    result = SlideshowMarketingAnalysisStage().run(db_session, slideshow_with_slide)

    assert result.succeeded is True

    db_session.refresh(slideshow_with_slide)
    ma_id = slideshow_with_slide.current_marketing_analysis_id
    assert ma_id is not None

    ma = db_session.get(MarketingAnalysis, ma_id)
    assert ma.is_current is True
    assert ma.slideshow_id == slideshow_with_slide.id
    assert ma.narrative_text
    # Phase 7.3 (Narrative pass, see MIGRATION_PLAN.md): records exactly
    # which Creative Fingerprint version this was generated from.
    assert ma.creative_fingerprint_id == slideshow_with_slide.primary_slide.current_creative_fingerprint_id

    analysis_run = db_session.get(AnalysisRun, ma.analysis_run_id)
    assert analysis_run.analysis_type == "marketing_analysis"
    assert analysis_run.slideshow_id == slideshow_with_slide.id


def test_prompt_includes_fingerprint_json(db_session, slideshow_with_slide, monkeypatch):
    _build_fingerprint(db_session, slideshow_with_slide, monkeypatch)

    fake_text_provider = FakeTextGenerationProvider()
    monkeypatch.setattr(
        "app.slideshow_stages.marketing_analysis_stage.default_registry",
        FakeAIProviderRegistry(text_generation_provider=fake_text_provider),
    )
    SlideshowMarketingAnalysisStage().run(db_session, slideshow_with_slide)

    assert fake_text_provider.last_prompt_spec is not None
    assert "health-conscious young adults" in fake_text_provider.last_prompt_spec["prompt"]


def test_fails_gracefully_on_provider_error(db_session, slideshow_with_slide, monkeypatch):
    _build_fingerprint(db_session, slideshow_with_slide, monkeypatch)

    monkeypatch.setattr(
        "app.slideshow_stages.marketing_analysis_stage.default_registry",
        FakeAIProviderRegistry(
            text_generation_provider=FakeTextGenerationProvider(
                raise_error=RuntimeError("provider down")
            )
        ),
    )
    result = SlideshowMarketingAnalysisStage().run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "provider down" in result.error

    db_session.refresh(slideshow_with_slide)
    assert slideshow_with_slide.current_marketing_analysis_id is None


def test_legacy_row_with_no_recorded_fingerprint_round_trips_fine(db_session, slideshow_with_slide):
    """
    A pre-Phase-7.3 row has no way to be truthfully backfilled with which
    fingerprint it came from - None must round-trip cleanly, not be
    treated as a data-integrity problem. This is exactly the tolerance
    Phase 7.4's staleness check depends on (None means "unknown", not a
    crash).
    """
    from app.models.analysis_run import ANALYSIS_TYPE_MARKETING_ANALYSIS, STATUS_SUCCEEDED, AnalysisRun

    analysis_run = AnalysisRun(
        slideshow_id=slideshow_with_slide.id,
        analysis_type=ANALYSIS_TYPE_MARKETING_ANALYSIS,
        provider="fake",
        model_name="fake",
        status=STATUS_SUCCEEDED,
    )
    db_session.add(analysis_run)
    db_session.flush()

    legacy_row = MarketingAnalysis(
        analysis_run_id=analysis_run.id,
        slideshow_id=slideshow_with_slide.id,
        narrative_text="Pre-existing narrative, no recorded provenance.",
    )
    db_session.add(legacy_row)
    db_session.commit()
    db_session.refresh(legacy_row)

    assert legacy_row.creative_fingerprint_id is None


def test_rerun_produces_new_version(db_session, slideshow_with_slide, monkeypatch):
    _build_fingerprint(db_session, slideshow_with_slide, monkeypatch)
    monkeypatch.setattr(
        "app.slideshow_stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideshowMarketingAnalysisStage()
    stage.run(db_session, slideshow_with_slide)
    db_session.refresh(slideshow_with_slide)
    first_id = slideshow_with_slide.current_marketing_analysis_id

    stage.run(db_session, slideshow_with_slide)
    db_session.refresh(slideshow_with_slide)
    second_id = slideshow_with_slide.current_marketing_analysis_id

    assert second_id != first_id
    all_mas = list(
        db_session.scalars(
            select(MarketingAnalysis).where(MarketingAnalysis.slideshow_id == slideshow_with_slide.id)
        )
    )
    assert len(all_mas) == 2
    first = db_session.get(MarketingAnalysis, first_id)
    assert first.is_current is False
