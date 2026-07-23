"""
Unit tests for SceneIntelligenceStage (Phase 10.4 of AI Creative Engine
vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §8). No
real vision call - FakeVisionAnalysisProvider throughout.
"""

from app.models.analysis_run import STATUS_SUCCEEDED, AnalysisRun
from app.models.scene_analysis import SceneAnalysis
from app.slideshow_stages.scene_intelligence_stage import SceneIntelligenceStage
from tests.fakes import FakeAIProviderRegistry, FakeVisionAnalysisProvider

SCENE_RESULT = {
    "regions": [
        {
            "region_type": "product",
            "x_min": 0.3,
            "y_min": 0.4,
            "x_max": 0.7,
            "y_max": 0.9,
            "importance_tier": "important",  # deliberately wrong - the Stage must force this to "essential"
            "notes": "The bottle itself.",
        },
        {
            "region_type": "background",
            "x_min": 0.0,
            "y_min": 0.0,
            "x_max": 1.0,
            "y_max": 1.0,
            "importance_tier": "context",
            "notes": "Studio backdrop.",
        },
        {
            "region_type": "decorative_element",
            "x_min": 0.05,
            "y_min": 0.05,
            "x_max": 0.15,
            "y_max": 0.15,
            "importance_tier": "replaceable",
            "notes": "Small decorative sticker in the corner.",
        },
    ],
}


def test_succeeds_and_updates_slide(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.scene_intelligence_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=SCENE_RESULT)),
    )

    stage = SceneIntelligenceStage()
    result = stage.run(db_session, slideshow_with_slide)

    assert result.succeeded is True

    slide = slideshow_with_slide.primary_slide
    db_session.refresh(slide)
    scene_analysis_id = slide.current_scene_analysis_id
    assert scene_analysis_id is not None

    scene_analysis = db_session.get(SceneAnalysis, scene_analysis_id)
    assert scene_analysis.is_current is True
    assert scene_analysis.slide_id == slide.id
    assert len(scene_analysis.regions_json) == 3

    analysis_run = db_session.get(AnalysisRun, scene_analysis.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "scene_intelligence"


def test_forces_product_region_to_essential_regardless_of_model_output(
    db_session, slideshow_with_slide, monkeypatch
):
    """
    The one hard constraint this Stage must enforce, never trust from
    the AI - SCENE_RESULT deliberately supplies "important" for the
    product region to prove this isn't a coincidental pass.
    """
    monkeypatch.setattr(
        "app.slideshow_stages.scene_intelligence_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=SCENE_RESULT)),
    )

    stage = SceneIntelligenceStage()
    stage.run(db_session, slideshow_with_slide)

    slide = slideshow_with_slide.primary_slide
    db_session.refresh(slide)
    scene_analysis = db_session.get(SceneAnalysis, slide.current_scene_analysis_id)

    product_regions = [r for r in scene_analysis.regions_json if r["region_type"] == "product"]
    assert len(product_regions) == 1
    assert product_regions[0]["importance_tier"] == "essential"

    # Non-product regions are untouched.
    background_regions = [r for r in scene_analysis.regions_json if r["region_type"] == "background"]
    assert background_regions[0]["importance_tier"] == "context"


def test_rerun_produces_new_version_and_flips_previous(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.scene_intelligence_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=SCENE_RESULT)),
    )

    stage = SceneIntelligenceStage()
    stage.run(db_session, slideshow_with_slide)
    slide = slideshow_with_slide.primary_slide
    db_session.refresh(slide)
    first = db_session.get(SceneAnalysis, slide.current_scene_analysis_id)

    stage.run(db_session, slideshow_with_slide)
    db_session.refresh(slide)
    db_session.refresh(first)
    second = db_session.get(SceneAnalysis, slide.current_scene_analysis_id)

    assert second.id != first.id
    assert first.is_current is False
    assert second.is_current is True


def test_fails_gracefully_on_provider_error(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.scene_intelligence_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(raise_error=RuntimeError("vision provider down"))
        ),
    )

    result = SceneIntelligenceStage().run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "vision provider down" in result.error

    slide = slideshow_with_slide.primary_slide
    db_session.refresh(slide)
    assert slide.current_scene_analysis_id is None
