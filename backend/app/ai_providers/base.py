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
    def extract_text(self, image_bytes: bytes) -> OCRExtraction: ...


class VisionAnalysisProvider(Protocol):
    def analyze_creative(
        self, image_bytes: bytes, prompt_spec: dict, response_schema: dict
    ) -> dict: ...


class ProductIsolationProvider(Protocol):
    def isolate_product(self, image_bytes: bytes) -> list[dict]:
        """Returns bounding-box + notes dicts; the Stage handles cropping/saving."""
        ...


class PromptGenerationProvider(Protocol):
    def generate_creative_specification(
        self, lock_profile: dict, fingerprint: dict, response_schema: dict
    ) -> dict: ...


class TextGenerationProvider(Protocol):
    """
    Text-only structured generation - no image input. Used by the
    Marketing Analysis Stage (a text-only pass over the Creative
    Fingerprint's JSON, not vision - plan §6.3, §9).
    """

    def generate(self, prompt_spec: dict, response_schema: dict) -> dict: ...


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
    """

    creative_intent: str
    immutable_constraints: list[str]
    things_to_avoid: list[str]
    aspect_ratio: str


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
