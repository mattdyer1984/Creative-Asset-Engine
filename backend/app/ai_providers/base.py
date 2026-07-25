"""
AI capability interfaces (plan §4.1).

Each interface is deliberately provider-agnostic: plain Python types in,
plain Python types out. A Stage (app.stages) only ever talks to these
interfaces, never to an `openai` or `anthropic` SDK object directly.

Naming note: the plan's §4.1 sketch used "OCRResult" as both the AI
provider's raw return type and the persisted Analysis Artifact's table
name. Those are two different things in code - the DB model OCRResult
(app.models.ocr_result) is what the OCR Stage writes to the database;
OCRExtraction below is the plain-data shape a provider adapter hands back
before the Stage turns it into that DB row. This is a naming
clarification for implementation clarity, not an architectural change.

On response-shape validation: Stages currently trust that whatever a
provider adapter returns matches the response_schema they passed in -
this holds for the real OpenAI adapters because Structured Outputs with
strict=True guarantees it. If validation of that guarantee is ever added
(e.g. to defend against a future provider that doesn't enforce its
schema as reliably), it belongs in the adapter layer - each adapter
validating its own parsed response before returning it - not duplicated
inside every Stage. Stages should stay simple and keep trusting the
provider contract; enforcing that contract is the provider's job.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class OCRExtraction:
    raw_text: str
    structured_blocks: list[dict] = field(default_factory=list)


class OCRProvider(Protocol):
    def extract_text(self, image_bytes: bytes, *, usage_sink: dict | None = None) -> OCRExtraction: ...


class VisionAnalysisProvider(Protocol):
    def analyze_creative(
        self,
        image_bytes: bytes | list[bytes],
        prompt_spec: dict,
        response_schema: dict,
        *,
        usage_sink: dict | None = None,
    ) -> dict:
        """
        image_bytes accepts a list as of Phase 9.4 of Product Lock v2
        (see MIGRATION_PLAN.md's "ADR: Canonical Product Reference"
        §7) - Stage 1 Identity Validation needs to show the model the
        generated image AND one or more reference images in the same
        call, to compare them directly, rather than describing one
        image against text. Every existing caller (Product Lock
        Profile Stage, Creative Fingerprint Stage, Stage 2 of Image
        Validation) still passes a single `bytes` value and is
        unaffected - this is a backward-compatible extension of what
        was already a single-image parameter, not a new method.

        usage_sink (Optimisation & Stability Pass, Tier 2.2, see
        MIGRATION_PLAN.md) - an optional caller-supplied dict the
        adapter populates in place with `prompt_tokens`/
        `completion_tokens` after a real call, if the caller wants
        cost instrumentation. Deliberately an out-parameter rather than
        changing the return type: this method returns the schema-shaped
        dict itself (callers read `result["field"]` directly), so there
        is no room to also carry metadata on the return value without
        breaking every existing caller. `None` (the default) means "the
        caller doesn't want usage data" - every pre-existing call site
        is unaffected.
        """
        ...


class ProductIsolationProvider(Protocol):
    def isolate_product(self, image_bytes: bytes, *, usage_sink: dict | None = None) -> list[dict]:
        """Returns bounding-box + notes dicts; the Stage handles cropping/saving."""
        ...


class PromptGenerationProvider(Protocol):
    def generate_creative_specification(
        self,
        lock_profile: dict | None,
        fingerprint: dict,
        response_schema: dict,
        *,
        usage_sink: dict | None = None,
    ) -> dict:
        """
        lock_profile is None for a Story Slide (see MIGRATION_PLAN.md) -
        a slide with no detected product still gets a creative
        specification, composed from its Creative Fingerprint alone. The
        implementation must not invent a product when this is None.
        """
        ...


class TextGenerationProvider(Protocol):
    """
    Text-only structured generation - no image input. Used by the
    Marketing Analysis Stage (a text-only pass over the Creative
    Fingerprint's JSON, not vision - plan §6.3, §9).
    """

    def generate(self, prompt_spec: dict, response_schema: dict, *, usage_sink: dict | None = None) -> dict: ...


@dataclass
class GenerationRequest:
    """
    A compiled, provider-agnostic image generation request - the Prompt
    Compiler's output (app.services.prompt_compiler.
    compile_generation_request), Phase 8.2 of the Generation -> Validation
    proof of loop (see MIGRATION_PLAN.md).

    English-language intent, never provider-specific syntax - turning
    this into the literal request a given provider's API expects (the
    actual prompt string, size parameter, etc.) is each concrete
    ImageGenerationProvider's own job, not the compiler's. This is what
    keeps everything upstream of the provider boundary provider-agnostic.

    reference_image_paths (Phase 9.3 of Product Lock v2, see
    MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §6) replaces
    immutable_constraints as of that phase: the product is no longer
    described in text at all - these images (the Reference Selection
    service's chosen subset of the Canonical Reference Library) are the
    only source of product identity a generation call carries. A hard
    prerequisite, not optional - the Prompt Compiler refuses to compile
    a request without at least one, per that ADR's own explicit design
    decision (no silent text-only fallback).

    story_mode (Story Slide feature, see MIGRATION_PLAN.md) - False for
    every pre-existing call site (a real behavior-preserving default).
    True only for `run_story_generation_attempt`'s product-free path,
    where reference_image_paths is the slide's own source photo, not a
    product reference library selection - each adapter's own
    `_compile_*_prompt` reads this to swap "preserve the exact product"
    (meaningless with no product) for an "original, subtly-varied
    recreation of this scene" instruction instead.
    """

    creative_intent: str
    reference_image_paths: list[str]
    things_to_avoid: list[str]
    aspect_ratio: str
    story_mode: bool = False


@dataclass
class ProviderCapabilities:
    """
    What a given ImageGenerationProvider adapter can actually do - Phase
    10.1 of the AI Creative Engine vNext (see MIGRATION_PLAN.md's ADR
    §10). Exists so Reference Selection/the Decision Engine can ask a
    provider "how many reference images can you take" as data, rather
    than every caller hardcoding an assumption about one specific
    provider's real API limits. One dataclass covering every capability
    axis discovered so far, rather than a new Protocol method per axis -
    the axes here are the ones this codebase has directly verified
    against a real provider (OpenAI's Images API SDK, Google's Gemini
    API SDK) as of Phase 10.1; new axes get added to this dataclass, not
    new methods bolted onto the Protocol.
    """

    supports_reference_images: bool
    max_reference_images: int
    supports_masking: bool
    supports_inpainting: bool
    supported_resolutions: list[str]
    # Phase 10.3 of the AI Creative Engine vNext (see MIGRATION_PLAN.md's
    # ADR §2/§10.3/§13, "Photorealism by Default") - the provider-side
    # levers this codebase confirmed real for at least one adapter
    # (OpenAI's images.edit/generate `quality` parameter for gpt-image-1
    # specifically). Both default to None rather than a guessed value -
    # a provider only sets one of these once it's actually been
    # confirmed applicable to *its own* configured model, the same
    # "prove it before wiring it" discipline this project applies to
    # every other provider-specific capability claim.
    preferred_quality: str | None = None
    preferred_style: str | None = None


@dataclass
class GeneratedImageResult:
    """
    What a provider hands back after generating one image: the bytes
    plus facts about how they were produced. Mirrors
    ProductIsolationProvider's division of labor - the provider reports
    what it did, the calling Stage is responsible for persistence
    (saving the file, writing the DB row); the provider never touches
    storage or the database itself.
    """

    image_bytes: bytes
    provider: str
    model: str
    prompt_used: str
    seed: str | None
    generation_time_seconds: float


class ImageGenerationProvider(Protocol):
    """
    The one genuinely new AI capability the Generation -> Validation
    proof of loop needs (Phase 8, see MIGRATION_PLAN.md's architecture
    direction) - none of the 5 capabilities above can produce an image,
    all are analysis-only (image/text in, structured JSON out).
    """

    def generate_image(self, request: GenerationRequest) -> GeneratedImageResult: ...

    @property
    def capabilities(self) -> ProviderCapabilities:
        """
        Phase 10.1 (see MIGRATION_PLAN.md's vNext ADR §10) - a property,
        not a method: capability data is static per adapter instance
        (fixed at construction from the real, verified provider limits),
        never something worth a network round-trip to ask for.
        """
        ...
