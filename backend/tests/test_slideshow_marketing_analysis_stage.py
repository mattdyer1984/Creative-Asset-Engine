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
    assert ma.creative_id is None
    assert ma.narrative_text

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
