"""
AI Provider registry (plan §4.2).

Maps capability -> concrete adapter, driven by providers.yaml. A Stage
only ever asks the registry for "the current OCR provider" - it never
imports an SDK or instantiates an adapter itself. Adding a new provider
for an existing capability (e.g. Claude for OCR) is: implement
OCRProvider in a new class, add one line to OCR_ADAPTERS, flip
providers.yaml - no registry code changes.

`default_registry` (bottom of this file) is constructed lazily via a
module-level __getattr__ (PEP 562), not as a bare top-level statement -
see the comment down there for why, and app/main.py's `lifespan` for
where construction is explicitly, intentionally triggered.
"""

from app.ai_providers.base import (
    ImageGenerationProvider,
    OCRProvider,
    ProductIsolationProvider,
    PromptGenerationProvider,
    TextGenerationProvider,
    VisionAnalysisProvider,
)
from app.ai_providers.config import ModelsConfig, ProvidersConfig, load_config
from app.ai_providers.gemini_adapter import GeminiOCRAdapter, GeminiVisionAnalysisAdapter
from app.ai_providers.nano_banana_adapter import NanoBananaImageGenerationAdapter
from app.ai_providers.openai_adapter import (
    OpenAIImageGenerationAdapter,
    OpenAIOCRAdapter,
    OpenAIProductIsolationAdapter,
    OpenAIPromptGenerationAdapter,
    OpenAITextGenerationAdapter,
    OpenAIVisionAnalysisAdapter,
)

OCR_ADAPTERS: dict[str, type[OCRProvider]] = {
    "openai": OpenAIOCRAdapter,
    # Real-world-driven cost/quality change (see MIGRATION_PLAN.md) - the
    # default provider for this capability (see providers.yaml), not
    # merely an available alternative like nano_banana is for
    # image_generation.
    "gemini": GeminiOCRAdapter,
}

PRODUCT_ISOLATION_ADAPTERS: dict[str, type[ProductIsolationProvider]] = {
    "openai": OpenAIProductIsolationAdapter,
}

VISION_ANALYSIS_ADAPTERS: dict[str, type[VisionAnalysisProvider]] = {
    "openai": OpenAIVisionAnalysisAdapter,
    # Real-world-driven cost/quality change (see MIGRATION_PLAN.md) -
    # deliberately NOT the default provider for this capability (unlike
    # gemini for ocr above): most vision_analysis schema_names (Scene
    # Intelligence, Identity Validation, Image Validation, Photorealism,
    # Reference Scoring) stay on OpenAI. Only Product Lock Profile Stage
    # and Creative Fingerprint Stage explicitly request this via
    # vision(provider_name="gemini") - a narrower scope the user chose
    # explicitly over moving every vision_analysis task at once.
    "gemini": GeminiVisionAnalysisAdapter,
}

TEXT_GENERATION_ADAPTERS: dict[str, type[TextGenerationProvider]] = {
    "openai": OpenAITextGenerationAdapter,
}

PROMPT_GENERATION_ADAPTERS: dict[str, type[PromptGenerationProvider]] = {
    "openai": OpenAIPromptGenerationAdapter,
}

IMAGE_GENERATION_ADAPTERS: dict[str, type[ImageGenerationProvider]] = {
    "openai": OpenAIImageGenerationAdapter,
    # Phase 10.1 of the AI Creative Engine vNext (see MIGRATION_PLAN.md's
    # ADR §10) - the first genuinely second provider for any capability
    # in this registry. Not yet live-verified (no API key added as of
    # this sub-phase) - see nano_banana_adapter.py's own docstring.
    "nano_banana": NanoBananaImageGenerationAdapter,
}


class AIProviderRegistry:
    def __init__(
        self,
        providers_config: ProvidersConfig | None = None,
        models_config: ModelsConfig | None = None,
    ):
        if providers_config is None or models_config is None:
            loaded_providers, loaded_models = load_config()
            providers_config = providers_config or loaded_providers
            models_config = models_config or loaded_models

        self._ocr: OCRProvider = self._build(
            OCR_ADAPTERS, providers_config.ocr, models_config, "ocr"
        )
        self._isolation: ProductIsolationProvider = self._build(
            PRODUCT_ISOLATION_ADAPTERS,
            providers_config.product_isolation,
            models_config,
            "product_isolation",
        )
        self._vision: VisionAnalysisProvider = self._build(
            VISION_ANALYSIS_ADAPTERS,
            providers_config.vision_analysis,
            models_config,
            "vision_analysis",
        )
        self._text_generation: TextGenerationProvider = self._build(
            TEXT_GENERATION_ADAPTERS,
            providers_config.text_generation,
            models_config,
            "text_generation",
        )
        self._prompt_generation: PromptGenerationProvider = self._build(
            PROMPT_GENERATION_ADAPTERS,
            providers_config.prompt_generation,
            models_config,
            "prompt_generation",
        )
        self._image_generation: ImageGenerationProvider = self._build(
            IMAGE_GENERATION_ADAPTERS,
            providers_config.image_generation,
            models_config,
            "image_generation",
        )
        self._models_config = models_config
        self._image_generation_fallback_name = providers_config.image_generation_fallback
        self._ocr_fallback_name = providers_config.ocr_fallback

    @staticmethod
    def _build(adapters: dict, provider_name: str, models_config: ModelsConfig, capability: str):
        model = getattr(models_config, provider_name, {}).get(capability, "gpt-5.5")
        return adapters[provider_name](model=model, provider=provider_name)

    def ocr(self) -> OCRProvider:
        return self._ocr

    def ocr_fallback(self) -> OCRProvider | None:
        """
        Reliability follow-up (see MIGRATION_PLAN.md) - mirrors
        image_generation_fallback exactly: the provider ocr_stage.py
        retries against when the primary OCR provider's own call fails
        (a real, live Gemini outage hit gemini-flash-latest with 503s,
        the same event behind the image-generation fallback). None if
        unconfigured or the same as the primary.
        """
        fallback_name = self._ocr_fallback_name
        if fallback_name is None or fallback_name == self._ocr.provider:
            return None
        return self._build(OCR_ADAPTERS, fallback_name, self._models_config, "ocr")

    def isolation(self) -> ProductIsolationProvider:
        return self._isolation

    def vision(self, provider_name: str | None = None) -> VisionAnalysisProvider:
        """
        Real-world-driven cost/quality change (see MIGRATION_PLAN.md) -
        `vision_analysis` is the second capability (after
        `image_generation`) to need a per-call override rather than only
        ever returning the configured default: Product Lock Profile
        Stage and Creative Fingerprint Stage explicitly request
        `provider_name="gemini"`, while every other vision_analysis
        caller (Scene Intelligence, Identity/Image Validation,
        Photorealism, Reference Scoring) calls `vision()` with no
        argument and keeps getting the configured default (OpenAI).
        `provider_name=None` (the default) preserves every pre-existing
        call site's exact behavior - additive, not breaking.
        """
        if provider_name is None or provider_name == self._vision.provider:
            return self._vision
        return self._build(VISION_ANALYSIS_ADAPTERS, provider_name, self._models_config, "vision_analysis")

    def vision_fallback(self, provider_name: str) -> VisionAnalysisProvider | None:
        """
        Reliability follow-up (see MIGRATION_PLAN.md) - the provider
        Product Lock Profile Stage/Creative Fingerprint Stage retry
        against when their explicit vision(provider_name="gemini") call
        itself fails. Simply the plain configured default (`vision()`
        with no override, OpenAI) - there's no separate config key for
        this since the default is already a real, different, always-
        available provider. None if `provider_name` already names the
        default (nothing distinct to fall back to).
        """
        if provider_name == self._vision.provider:
            return None
        return self._vision

    def text_generation(self) -> TextGenerationProvider:
        return self._text_generation

    def prompt_generation(self) -> PromptGenerationProvider:
        return self._prompt_generation

    def image_generation(self, provider_name: str | None = None) -> ImageGenerationProvider:
        """
        Phase 10.1 of the AI Creative Engine vNext (see MIGRATION_PLAN.md's
        ADR §10) - `image_generation` is the first capability with more
        than one real adapter, so this is the first accessor that
        supports an explicit override rather than only ever returning
        the configured default. `provider_name=None` (the default, and
        every existing call site's behavior) returns the same cached
        instance as before - this is additive, not a breaking change to
        the 5 other capabilities' single-provider accessors, which have
        no reason to grow this parameter until they have a second real
        adapter of their own.
        """
        if provider_name is None or provider_name == self._image_generation.provider:
            return self._image_generation
        return self._build(
            IMAGE_GENERATION_ADAPTERS, provider_name, self._models_config, "image_generation"
        )

    def image_generation_fallback(self) -> ImageGenerationProvider | None:
        """
        Reliability follow-up to the Story Slide feature (see
        MIGRATION_PLAN.md) - the second provider
        `generation_engine._generate_candidates` retries against when
        the primary `image_generation` provider's own call fails (a
        transient error like a provider 5xx/overload - a different
        concern from generate_with_retry.py's existing retry-on-rejected-
        candidate loop, which retries for a quality reason, not a
        provider failure). `None` if no fallback is configured, or if
        the configured fallback names the same provider as the primary
        (nothing real to fall back to).
        """
        fallback_name = self._image_generation_fallback_name
        if fallback_name is None or fallback_name == self._image_generation.provider:
            return None
        return self.image_generation(fallback_name)


# Module-level default instance - Stages import this rather than each
# constructing their own registry, so config is loaded once per process.
#
# Built lazily (on first access to the name `default_registry`, via the
# module __getattr__ below - PEP 562) rather than as a bare
# `default_registry = AIProviderRegistry()` statement, so merely
# *importing* this module (e.g. for the AIProviderRegistry class itself,
# or transitively via some import chain that never actually needs the
# singleton) no longer has the side effect of reading providers.yaml and
# constructing five adapters. app/main.py's `lifespan` explicitly touches
# `default_registry` on app startup as the intentional, documented
# trigger point for that construction.
#
# Every Stage still does `from app.ai_providers.registry import
# default_registry` exactly as before - that statement itself invokes
# this __getattr__ (Python's `from module import name` performs a
# getattr(module, name), which module-level __getattr__ intercepts), so
# no Stage or test file needed to change: each Stage's own
# `default_registry` name still ends up bound to this same cached
# instance, and `monkeypatch.setattr("app.stages.<x>.default_registry",
# ...)` continues to work exactly as it does today.
_default_registry: AIProviderRegistry | None = None


def __getattr__(name: str) -> AIProviderRegistry:
    if name == "default_registry":
        global _default_registry
        if _default_registry is None:
            _default_registry = AIProviderRegistry()
        return _default_registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
