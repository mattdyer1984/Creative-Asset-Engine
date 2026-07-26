"""
Test doubles for AI provider capabilities.

Used to test Stages/Orchestrator behavior without any real network call -
exactly what plan §13 calls for ("Integration tests ... using a mocked AI
provider (no real API calls in CI)").
"""

from app.ai_providers.base import (
    GeneratedImageResult,
    GenerationRequest,
    OCRExtraction,
    ProviderCapabilities,
)


def _assert_matches_ocr_response_shape(extraction: OCRExtraction) -> None:
    """
    Guards against FakeOCRProvider's canned data silently drifting out of
    sync with OCR_RESPONSE_SCHEMA (app.ai_providers.openai_adapter) - the
    two agree today by construction, not by any automatic check, so this
    fails loudly (at fixture-creation time, before any test even runs) if
    someone changes one without the other.
    """
    assert isinstance(extraction.raw_text, str)
    assert isinstance(extraction.structured_blocks, list)
    for block in extraction.structured_blocks:
        assert set(block.keys()) == {"text", "role", "bounding_box"}, (
            f"structured_blocks entries must have exactly 'text', 'role', and "
            f"'bounding_box' keys to match OCR_RESPONSE_SCHEMA - got {block.keys()}"
        )
        assert isinstance(block["text"], str)
        assert isinstance(block["role"], str)
        assert set(block["bounding_box"].keys()) == {"x_min", "y_min", "x_max", "y_max"}


class FakeOCRProvider:
    """Returns a canned result, or raises, depending on how it's configured."""

    model = "fake-ocr-model"
    provider = "openai"

    def __init__(self, extraction: OCRExtraction | None = None, raise_error: Exception | None = None):
        self._extraction = extraction or OCRExtraction(
            raw_text="Fresh Squeezed. Zero Sugar Added.",
            structured_blocks=[
                {
                    "text": "Fresh Squeezed",
                    "role": "headline",
                    "bounding_box": {"x_min": 0.1, "y_min": 0.05, "x_max": 0.9, "y_max": 0.2},
                },
                {
                    "text": "Zero Sugar Added",
                    "role": "subheadline",
                    "bounding_box": {"x_min": 0.1, "y_min": 0.22, "x_max": 0.7, "y_max": 0.32},
                },
            ],
        )
        if raise_error is None:
            _assert_matches_ocr_response_shape(self._extraction)
        self._raise_error = raise_error

    def extract_text(self, image_bytes: bytes, *, usage_sink: dict | None = None) -> OCRExtraction:
        if self._raise_error is not None:
            raise self._raise_error
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = 100
            usage_sink["completion_tokens"] = 50
        return self._extraction


def _assert_matches_product_isolation_shape(bounding_boxes: list[dict]) -> None:
    """Guards FakeProductIsolationProvider against drifting from PRODUCT_ISOLATION_RESPONSE_SCHEMA."""
    expected_keys = {"x_min", "y_min", "x_max", "y_max", "confidence", "notes"}
    for box in bounding_boxes:
        assert set(box.keys()) == expected_keys, (
            f"bounding box entries must have exactly {expected_keys} - got {box.keys()}"
        )


class FakeProductIsolationProvider:
    """Returns a canned bounding box, or raises, depending on how it's configured."""

    model = "fake-isolation-model"
    provider = "openai"

    def __init__(self, bounding_boxes: list[dict] | None = None, raise_error: Exception | None = None):
        self._bounding_boxes = (
            bounding_boxes
            if bounding_boxes is not None
            else [
                {
                    "x_min": 0.2,
                    "y_min": 0.15,
                    "x_max": 0.8,
                    "y_max": 0.9,
                    "confidence": 0.95,
                    "notes": "Bottle centered in frame",
                }
            ]
        )
        if raise_error is None:
            _assert_matches_product_isolation_shape(self._bounding_boxes)
        self._raise_error = raise_error

    def isolate_product(self, image_bytes: bytes, *, usage_sink: dict | None = None) -> list[dict]:
        if self._raise_error is not None:
            raise self._raise_error
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = 100
            usage_sink["completion_tokens"] = 50
        return self._bounding_boxes


def _assert_matches_product_lock_profile_shape(result: dict) -> None:
    """Guards FakeVisionAnalysisProvider's canned profile against drifting from PRODUCT_LOCK_PROFILE_SCHEMA."""
    expected_keys = {
        "product_category",
        "product_type",
        "shape_and_proportions",
        "packaging",
        "materials",
        "surface_finish",
        "colors",
        "branding",
        "labels_and_text",
        "distinguishing_features",
        "viewing_angle",
        "perspective",
        "lighting_characteristics",
        "approximate_scale_in_frame",
        "immutable_characteristics",
        "extensions",
    }
    assert set(result.keys()) == expected_keys, (
        f"product lock profile result must have exactly {expected_keys} - got {result.keys()}"
    )


#: Canned answers keyed by schema_name, used when a caller has not supplied
#: its own. Stages that share `analyze_creative` but expect different shapes
#: would otherwise each have to be patched individually in every integration
#: test that runs the whole pipeline - and a stage nobody remembered to patch
#: makes a real, paid call from the test suite. That has happened before (see
#: Scene Intelligence, Phase 10.4), so new stages get a default here.
_CANNED_BY_SCHEMA: dict[str, dict] = {
    "scene_intelligence": {"regions": []},
    "composition_contract": {
        "device": "product-hero",
        "device_confidence": 0.8,
        "zones": [
            {"id": "caption", "role": "text",
             "x_min": 0.1, "y_min": 0.05, "x_max": 0.9, "y_max": 0.2},
            {"id": "hero", "role": "product",
             "x_min": 0.1, "y_min": 0.25, "x_max": 0.9, "y_max": 0.85},
        ],
        "relations": [{"subject": "caption", "relation": "above", "object": "hero"}],
        "emphasis": ["caption", "hero"],
    },
    "typography_system": {
        "primary_family_class": "grotesque",
        "secondary_family_class": None,
        "capability_level": "L1",
        "colour_roles": {"body": "near-black"},
        "text_roles": {
            "headline": {"family_class": "grotesque", "weight": "bold",
                         "colour_role": "body", "size_ratio": 2.0},
        },
        "size_scale": {"headline_to_body": 2.0},
    },
}


class FakeVisionAnalysisProvider:
    """Returns a canned Product Lock Profile dict, or raises."""

    model = "fake-vision-model"
    provider = "openai"

    def __init__(
        self,
        result: dict | None = None,
        raise_error: Exception | None = None,
        results_by_schema_name: dict[str, dict] | None = None,
    ):
        """
        results_by_schema_name (Phase 9.4 of Product Lock v2, see
        MIGRATION_PLAN.md) - opt-in, additive: SlideImageValidationStage
        now calls analyze_creative up to twice per run (schema_name
        "identity_validation" then "image_validation"), and most tests
        need each call to return a genuinely different shape/outcome.
        Falls back to `self._result` for any schema_name not given here
        (or when this param is omitted entirely) - every other caller
        of this fake, and every test that only cares about one call, is
        unaffected.
        """
        self._results_by_schema_name = results_by_schema_name
        # Whether the caller chose this result. An explicit one always wins
        # over the schema-keyed defaults below - a test that says what it
        # wants back must get it.
        self._result_is_explicit = result is not None
        self._result = result if result is not None else {
            "product_category": "beverage",
            "product_type": "juice bottle",
            "shape_and_proportions": "tall cylindrical bottle",
            "packaging": {"type": "glass bottle", "closure": "screw cap", "notes": "clear glass"},
            "materials": ["glass", "paper label"],
            "surface_finish": "matte label, glossy glass",
            "colors": {"primary": ["orange"], "secondary": ["white", "green"]},
            "branding": {
                "brand_name": "Sunrise",
                "logo_placement": "front center",
                "logo_description": "sunrise icon above wordmark",
            },
            "labels_and_text": [
                {"text": "Sunrise", "location": "front label", "font_style": "bold serif"}
            ],
            "distinguishing_features": ["sunrise icon", "orange cap"],
            "viewing_angle": "eye-level",
            "perspective": "straight-on",
            "lighting_characteristics": "soft studio lighting",
            "approximate_scale_in_frame": "fills most of frame height",
            "immutable_characteristics": ["bottle shape", "label design", "cap color"],
            "extensions": "",
        }
        if raise_error is None and result is None:
            # Only validated when using our own canned default - a caller
            # testing a different stage that reuses this same provider
            # interface (e.g. Creative Fingerprint Stage) with a
            # different schema legitimately supplies a differently-shaped
            # custom result, which this assertion has no business judging.
            _assert_matches_product_lock_profile_shape(self._result)
        self._raise_error = raise_error
        # Records the most recent call's prompt_spec, so tests can assert
        # on what context (e.g. OCR text) was actually included, rather
        # than just trusting the calling Stage's docstring.
        self.last_prompt_spec: dict | None = None

    def analyze_creative(
        self,
        image_bytes: bytes | list[bytes],
        prompt_spec: dict,
        response_schema: dict,
        *,
        usage_sink: dict | None = None,
    ) -> dict:
        self.last_prompt_spec = prompt_spec
        if self._raise_error is not None:
            raise self._raise_error
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = 100
            usage_sink["completion_tokens"] = 50
        schema_name = prompt_spec.get("schema_name")
        if self._results_by_schema_name is not None:
            if schema_name in self._results_by_schema_name:
                return self._results_by_schema_name[schema_name]
        # A stage whose shape this fake knows gets that shape, but only when
        # the caller did not name one. Returning a product-lock dict to the
        # contract stage would exercise its rejection path, not its success
        # path, in every test that never meant to test either.
        if not self._result_is_explicit and schema_name in _CANNED_BY_SCHEMA:
            return _CANNED_BY_SCHEMA[schema_name]
        return self._result


def _assert_matches_marketing_analysis_shape(result: dict) -> None:
    """Guards FakeTextGenerationProvider's canned result against drifting from MARKETING_ANALYSIS_SCHEMA."""
    assert set(result.keys()) == {"narrative"}, (
        f"marketing analysis result must have exactly {{'narrative'}} - got {result.keys()}"
    )
    assert isinstance(result["narrative"], str)


class FakeTextGenerationProvider:
    """
    Returns a canned dict for TextGenerationProvider.generate(), or
    raises - shared by both real consumers (Marketing Analysis and, since
    Phase 7.2, Narrative Structure - see MIGRATION_PLAN.md), which expect
    different response shapes. The shape guard only applies to this
    class's own default canned result (marketing-analysis-shaped, its
    original and only purpose) - an explicitly supplied `result` is
    trusted as-is, since it's now the caller's job to match whichever
    consumer/schema they're actually faking.
    """

    model = "fake-text-model"
    provider = "openai"

    def __init__(self, result: dict | None = None, raise_error: Exception | None = None):
        self._result = result if result is not None else {
            "narrative": (
                "This creative uses bright, appetizing colors and bold "
                "typography to appeal to health-conscious shoppers looking "
                "for a quick, refreshing drink. The direct product shot and "
                "confident branding suggest a trustworthy, established "
                "product rather than a new market entrant."
            )
        }
        if raise_error is None and result is None:
            _assert_matches_marketing_analysis_shape(self._result)
        self._raise_error = raise_error
        # Records the most recent call's prompt_spec, so tests can assert
        # on what context (e.g. the Fingerprint's JSON) was actually sent.
        self.last_prompt_spec: dict | None = None

    def generate(self, prompt_spec: dict, response_schema: dict, *, usage_sink: dict | None = None) -> dict:
        self.last_prompt_spec = prompt_spec
        if self._raise_error is not None:
            raise self._raise_error
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = 100
            usage_sink["completion_tokens"] = 50
        return self._result


def _assert_matches_creative_specification_ai_shape(result: dict) -> None:
    """Guards FakePromptGenerationProvider's canned result against drifting from CREATIVE_SPECIFICATION_AI_SCHEMA."""
    expected_keys = {
        "subject",
        "composition",
        "style_direction",
        "color_palette",
        "lighting",
        "camera_and_perspective",
        "background_environment",
        "mood",
        "text_overlays",
        "things_to_avoid",
        "aspect_ratio",
        "extensions",
    }
    assert set(result.keys()) == expected_keys, (
        f"creative specification AI result must have exactly {expected_keys} - got {result.keys()}"
    )


class FakePromptGenerationProvider:
    """Returns a canned creative-specification creative-direction dict, or raises."""

    model = "fake-prompt-model"
    provider = "openai"

    def __init__(self, result: dict | None = None, raise_error: Exception | None = None):
        self._result = result if result is not None else {
            "subject": "A single bottle of orange juice on a sunlit kitchen counter",
            "composition": "off-center product shot with negative space for text",
            "style_direction": "warm, natural morning light photography",
            "color_palette": ["warm orange", "cream", "soft green"],
            "lighting": "natural morning sunlight from the left",
            "camera_and_perspective": "eye-level, slight angle",
            "background_environment": "blurred kitchen counter with fruit",
            "mood": "fresh, energizing, morning routine",
            "text_overlays": [{"role": "headline", "content": "Start Fresh"}],
            "things_to_avoid": ["cluttered background", "artificial-looking lighting"],
            "aspect_ratio": "4:5",
            "extensions": "",
        }
        if raise_error is None and result is None:
            _assert_matches_creative_specification_ai_shape(self._result)
        self._raise_error = raise_error
        self.last_call: dict | None = None

    def generate_creative_specification(
        self, lock_profile: dict | None, fingerprint: dict, response_schema: dict, *, usage_sink: dict | None = None
    ) -> dict:
        self.last_call = {"lock_profile": lock_profile, "fingerprint": fingerprint}
        if self._raise_error is not None:
            raise self._raise_error
        if usage_sink is not None:
            usage_sink["prompt_tokens"] = 100
            usage_sink["completion_tokens"] = 50
        return self._result


class FakeImageGenerationProvider:
    """Returns a canned GeneratedImageResult, or raises - Phase 8.2, see MIGRATION_PLAN.md."""

    model = "fake-image-model"
    provider = "openai"

    def __init__(self, result: GeneratedImageResult | None = None, raise_error: Exception | None = None):
        self._result = result or GeneratedImageResult(
            image_bytes=b"\x89PNG\r\n\x1a\nfake-png-bytes",
            provider="openai",
            model="fake-image-model",
            prompt_used="a fake compiled prompt",
            seed=None,
            generation_time_seconds=0.01,
        )
        self._raise_error = raise_error
        self.last_request: GenerationRequest | None = None

    def generate_image(self, request: GenerationRequest) -> GeneratedImageResult:
        self.last_request = request
        if self._raise_error is not None:
            raise self._raise_error
        return self._result

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_reference_images=True,
            max_reference_images=16,
            supports_masking=True,
            supports_inpainting=True,
            supported_resolutions=["1024x1024", "1536x1024", "1024x1536"],
        )


class FakeAIProviderRegistry:
    def __init__(
        self,
        ocr_provider: FakeOCRProvider | None = None,
        isolation_provider: FakeProductIsolationProvider | None = None,
        vision_provider: FakeVisionAnalysisProvider | None = None,
        text_generation_provider: FakeTextGenerationProvider | None = None,
        prompt_generation_provider: FakePromptGenerationProvider | None = None,
        image_generation_provider: FakeImageGenerationProvider | None = None,
        image_generation_fallback_provider: FakeImageGenerationProvider | None = None,
        ocr_fallback_provider: FakeOCRProvider | None = None,
        vision_fallback_provider: FakeVisionAnalysisProvider | None = None,
    ):
        self._ocr_provider = ocr_provider or FakeOCRProvider()
        self._isolation_provider = isolation_provider or FakeProductIsolationProvider()
        self._vision_provider = vision_provider or FakeVisionAnalysisProvider()
        self._text_generation_provider = text_generation_provider or FakeTextGenerationProvider()
        self._prompt_generation_provider = (
            prompt_generation_provider or FakePromptGenerationProvider()
        )
        self._image_generation_provider = (
            image_generation_provider or FakeImageGenerationProvider()
        )
        # Reliability follow-up to the Story Slide feature (see
        # MIGRATION_PLAN.md) - None by default (no fallback configured),
        # matching every pre-existing test's behavior exactly. A test
        # that cares about the fallback path passes one explicitly.
        self._image_generation_fallback_provider = image_generation_fallback_provider
        # None by default (no fallback configured) for both, matching
        # every pre-existing test's behavior exactly - a test that
        # cares about the fallback path passes one explicitly.
        self._ocr_fallback_provider = ocr_fallback_provider
        self._vision_fallback_provider = vision_fallback_provider
        # Spy list, not behavior - real-world-driven cost/quality change
        # (see MIGRATION_PLAN.md): lets a test assert a Stage actually
        # requested vision(provider_name="gemini") rather than just
        # trusting that the (ignored) argument was accepted.
        self.vision_calls: list[str | None] = []

    def ocr(self) -> FakeOCRProvider:
        return self._ocr_provider

    def ocr_fallback(self) -> FakeOCRProvider | None:
        """Mirrors AIProviderRegistry.ocr_fallback's real signature - see MIGRATION_PLAN.md."""
        return self._ocr_fallback_provider

    def isolation(self) -> FakeProductIsolationProvider:
        return self._isolation_provider

    def vision(self, provider_name: str | None = None) -> FakeVisionAnalysisProvider:
        """
        provider_name (real-world-driven cost/quality change, mirroring
        AIProviderRegistry.vision's real override signature - see
        MIGRATION_PLAN.md) - accepted and ignored, same reasoning as
        image_generation's fake below: every test that cares about a
        specific provider name should construct FakeVisionAnalysisProvider
        with that name directly rather than this fake actually branching
        on it, since this double only ever holds one configured instance.
        """
        self.vision_calls.append(provider_name)
        return self._vision_provider

    def vision_fallback(self, provider_name: str) -> FakeVisionAnalysisProvider | None:
        """Mirrors AIProviderRegistry.vision_fallback's real signature - see MIGRATION_PLAN.md."""
        return self._vision_fallback_provider

    def text_generation(self) -> FakeTextGenerationProvider:
        return self._text_generation_provider

    def prompt_generation(self) -> FakePromptGenerationProvider:
        return self._prompt_generation_provider

    def image_generation(self, provider_name: str | None = None) -> FakeImageGenerationProvider:
        """
        provider_name (Phase 10.1, mirroring AIProviderRegistry.
        image_generation's real override signature) - accepted and
        ignored: every test that cares about a specific provider name
        should construct FakeImageGenerationProvider with that name
        directly rather than this fake actually branching on it, since
        this double only ever holds one configured instance.
        """
        return self._image_generation_provider

    def image_generation_fallback(self) -> FakeImageGenerationProvider | None:
        """Mirrors AIProviderRegistry.image_generation_fallback's real signature - see MIGRATION_PLAN.md."""
        return self._image_generation_fallback_provider


def patch_pipeline_registries(monkeypatch, **per_module):
    """
    Point every SLIDESHOW_STAGE_PIPELINE stage at a fake provider registry.

    Derived from the pipeline, not from a hand-written list. The list was a
    standing hazard: Scene Intelligence was added to the pipeline and never
    added to the several copies of that list scattered across the suite, so
    tests documented as "no real provider call" were silently making a real,
    paid vision call for one stage. A stage added tomorrow is covered by
    construction.

    `per_module` overrides a specific stage module by its short module name,
    e.g. `narrative_structure_stage=FakeAIProviderRegistry(...)`, for the few
    stages that need a differently-shaped canned response than
    FakeVisionAnalysisProvider's schema-keyed defaults provide.
    """
    import importlib

    from app.slideshow_stages.pipeline import SLIDESHOW_STAGE_PIPELINE

    for stage in SLIDESHOW_STAGE_PIPELINE:
        path = type(stage).__module__
        if not hasattr(importlib.import_module(path), "default_registry"):
            continue
        override = per_module.get(path.rsplit(".", 1)[-1])
        monkeypatch.setattr(
            f"{path}.default_registry", override or FakeAIProviderRegistry()
        )
