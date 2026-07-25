"""
Unit tests for Creative Intelligence's decision layer (Phase 10.4 of AI
Creative Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative
Engine vNext" §8). No real provider call - FakeTextGenerationProvider.
"""

from app.models.scene_analysis import SceneAnalysis
from app.services.creative_intelligence import region_decision


def test_essential_and_important_tiers_preserve():
    assert region_decision("essential") == "preserve"
    assert region_decision("important") == "preserve"


def test_context_incidental_replaceable_tiers_transform():
    assert region_decision("context") == "transform"
    assert region_decision("incidental") == "transform"
    assert region_decision("replaceable") == "transform"


def test_optimize_scene_description_calls_text_provider_with_correct_prompt_split(monkeypatch):
    from app.services.creative_intelligence import optimize_scene_description

    scene_analysis = SceneAnalysis(
        slide_id="slide-1",
        analysis_run_id="run-1",
        regions_json=[
            {"region_type": "product", "importance_tier": "essential", "notes": "The bottle."},
            {"region_type": "environment", "importance_tier": "context", "notes": "Studio backdrop."},
            {"region_type": "prop", "importance_tier": "incidental", "notes": "A chair."},
        ],
    )

    captured = {}

    class _CapturingTextProvider:
        model = "fake-text-model"
        provider = "openai"

        def generate(self, prompt_spec, response_schema, *, usage_sink=None):
            captured["prompt"] = prompt_spec["prompt"]
            captured["schema_name"] = prompt_spec["schema_name"]
            return {
                "optimized_scene_description": "a premium modern studio backdrop with a single elegant chair",
                "reasoning": "matches the premium positioning",
            }

    class _FakeRegistryForText:
        def text_generation(self):
            return _CapturingTextProvider()

    monkeypatch.setattr(
        "app.services.creative_intelligence.default_registry", _FakeRegistryForText()
    )

    result = optimize_scene_description(
        scene_analysis,
        visual_style="clean, minimalist product photography",
        marketing_narrative="drives trial purchase among health-conscious buyers",
        product_category="beverage",
        creativity_level="bold",
    )

    assert result["optimized_scene_description"] == (
        "a premium modern studio backdrop with a single elegant chair"
    )
    assert captured["schema_name"] == "creative_intelligence"
    # The product region (essential) must appear in the "preserve" half
    # of the prompt, never offered up as something free to transform.
    assert "The bottle." in captured["prompt"]
    assert "Studio backdrop." in captured["prompt"]
    assert "A chair." in captured["prompt"]
    # Bold creativity guidance should be present, not the conservative one.
    assert "boldly" in captured["prompt"]
