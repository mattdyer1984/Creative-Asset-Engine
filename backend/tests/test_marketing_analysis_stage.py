"""
Unit tests for MarketingAnalysisStage (plan §13's Stage contract tests).
"""

from sqlalchemy import select

from app.models.analysis_run import AnalysisRun
from app.models.marketing_analysis import MarketingAnalysis
from app.stages.creative_fingerprint_stage import CreativeFingerprintStage
from app.stages.marketing_analysis_stage import MarketingAnalysisStage
from tests.fakes import FakeAIProviderRegistry, FakeTextGenerationProvider, FakeVisionAnalysisProvider
from tests.test_creative_fingerprint_stage import FINGERPRINT_RESULT


def _run_fingerprint_stage_first(db_session, creative, monkeypatch):
    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    CreativeFingerprintStage().run(db_session, creative, creative.blueprint)


def test_fails_gracefully_without_a_fingerprint(db_session, creative_with_blueprint, monkeypatch):
    monkeypatch.setattr(
        "app.stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = MarketingAnalysisStage()
    result = stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)

    assert result.succeeded is False
    assert "No Creative Fingerprint" in result.error
    # No AnalysisRun should be created - the prerequisite was never met.
    assert db_session.scalars(select(AnalysisRun)).first() is None


def test_succeeds_and_updates_blueprint(db_session, creative_with_blueprint, monkeypatch):
    _run_fingerprint_stage_first(db_session, creative_with_blueprint, monkeypatch)

    monkeypatch.setattr(
        "app.stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )
    stage = MarketingAnalysisStage()
    result = stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)

    assert result.succeeded is True

    db_session.refresh(creative_with_blueprint.blueprint)
    marketing_analysis_id = creative_with_blueprint.blueprint.current_marketing_analysis_id
    assert marketing_analysis_id is not None

    marketing_analysis = db_session.get(MarketingAnalysis, marketing_analysis_id)
    assert marketing_analysis.is_current is True
    assert "health-conscious" in marketing_analysis.narrative_text

    analysis_run = db_session.get(AnalysisRun, marketing_analysis.analysis_run_id)
    assert analysis_run.status == "succeeded"
    assert analysis_run.analysis_type == "marketing_analysis"


def test_prompt_includes_fingerprint_json(db_session, creative_with_blueprint, monkeypatch):
    """Directly verifies the Fingerprint's JSON is actually included in the prompt sent to the provider."""
    _run_fingerprint_stage_first(db_session, creative_with_blueprint, monkeypatch)

    fake_text_provider = FakeTextGenerationProvider()
    monkeypatch.setattr(
        "app.stages.marketing_analysis_stage.default_registry",
        FakeAIProviderRegistry(text_generation_provider=fake_text_provider),
    )

    MarketingAnalysisStage().run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)

    assert fake_text_provider.last_prompt_spec is not None
    assert "health-conscious young adults" in fake_text_provider.last_prompt_spec["prompt"]


def test_fails_gracefully_on_provider_error(db_session, creative_with_blueprint, monkeypatch):
    _run_fingerprint_stage_first(db_session, creative_with_blueprint, monkeypatch)

    monkeypatch.setattr(
        "app.stages.marketing_analysis_stage.default_registry",
        FakeAIProviderRegistry(
            text_generation_provider=FakeTextGenerationProvider(raise_error=RuntimeError("provider down"))
        ),
    )

    result = MarketingAnalysisStage().run(
        db_session, creative_with_blueprint, creative_with_blueprint.blueprint
    )

    assert result.succeeded is False
    assert "provider down" in result.error

    db_session.refresh(creative_with_blueprint.blueprint)
    assert creative_with_blueprint.blueprint.current_marketing_analysis_id is None


def test_rerun_produces_new_version(db_session, creative_with_blueprint, monkeypatch):
    _run_fingerprint_stage_first(db_session, creative_with_blueprint, monkeypatch)
    monkeypatch.setattr(
        "app.stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = MarketingAnalysisStage()
    stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)
    db_session.refresh(creative_with_blueprint.blueprint)
    first_id = creative_with_blueprint.blueprint.current_marketing_analysis_id

    stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)
    db_session.refresh(creative_with_blueprint.blueprint)
    second_id = creative_with_blueprint.blueprint.current_marketing_analysis_id

    assert second_id != first_id
    first = db_session.get(MarketingAnalysis, first_id)
    assert first.is_current is False
