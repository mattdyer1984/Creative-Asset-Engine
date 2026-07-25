"""
OpenAI adapters for the OCR, Product Isolation, Vision Analysis, Text
Generation, Prompt Generation, and Image Generation capabilities (plan
§4; Image Generation added in Phase 8.2, see MIGRATION_PLAN.md).

Uses OpenAI's Structured Outputs mode (response_format=json_schema,
strict=True) throughout the structured-JSON capabilities, so responses
are guaranteed to match the given schema - no manual parsing/validation
of loosely-structured text needed. Image Generation is the one
capability with no structured-output equivalent - OpenAI's Images API
returns image bytes, not JSON.
"""

import base64
import json
import time
from pathlib import Path

import httpx
from openai import OpenAI

from app.ai_providers.base import (
    GeneratedImageResult,
    GenerationRequest,
    OCRExtraction,
    ProviderCapabilities,
)
from app.ai_providers.config import AI_PROVIDER_TIMEOUT_SECONDS, get_api_key
from app.prompts import analysis as _analysis_prompts
from app.prompts import generation as _generation_prompts

OCR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "raw_text": {
            "type": "string",
            "description": "All visible text in the image, concatenated in reading order.",
        },
        "structured_blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "role": {
                        "type": "string",
                        "description": (
                            "The text element's marketing role, e.g. "
                            "headline, subheadline, price, cta, "
                            "disclaimer, logo_text, other."
                        ),
                    },
                    # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a
                    # real generation duplicated text that was already
                    # physically part of the photographed scene (product
                    # packaging, shelf price tags) by re-compositing it a
                    # second time as a marketing overlay - `role` alone
                    # can't distinguish "text a camera would have
                    # captured" from "text someone added on top of the
                    # photo afterward" (both can share a role like
                    # "headline"). `surface` is that explicit distinction,
                    # letting app.services.text_intelligence only ever
                    # treat genuine creator-added overlays as reusable -
                    # anything physically in the scene is the base image
                    # generation's job to reproduce, never this pipeline's.
                    "surface": {
                        "type": "string",
                        "enum": ["physical", "overlay"],
                        "description": (
                            "'physical': text printed, molded, or "
                            "displayed on a real object the camera "
                            "photographed - product packaging, a shelf "
                            "price tag, a sign, a screen. 'overlay': "
                            "text added digitally on top of the photo "
                            "or video afterward by whoever created or "
                            "edited it - a social-media caption, "
                            "meme-style commentary, a watermark, a "
                            "burned-in subtitle. It was never part of "
                            "the physical scene itself."
                        ),
                    },
                    # Phase 10.8 of AI Creative Engine vNext (see
                    # MIGRATION_PLAN.md's ADR §9) - a real, additive
                    # correction: §9 assumed "layout data... already
                    # largely available via OCRResult.structured_blocks_json",
                    # which was wrong (structured_blocks previously had no
                    # position at all). Same x_min/y_min/x_max/y_max
                    # normalized (0.0-1.0) convention Scene Intelligence's
                    # own regions already use (scene_intelligence_stage.py),
                    # not a new one invented for this.
                    "bounding_box": {
                        "type": "object",
                        "properties": {
                            "x_min": {"type": "number"},
                            "y_min": {"type": "number"},
                            "x_max": {"type": "number"},
                            "y_max": {"type": "number"},
                        },
                        "required": ["x_min", "y_min", "x_max", "y_max"],
                        "additionalProperties": False,
                    },
                },
                "required": ["text", "role", "surface", "bounding_box"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["raw_text", "structured_blocks"],
    "additionalProperties": False,
}

# Prompt text moved to app/prompts/ (WP-3) so it has an id, a version and a
# content hash. Re-exported under its original name: call sites and tests
# are deliberately untouched by the move.
OCR_PROMPT = _analysis_prompts.EXTRACT_TEXT.render()


def _image_content_block(image_bytes: bytes) -> dict:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}


def _populate_usage_sink(response, usage_sink: dict | None) -> None:
    """
    Optimisation & Stability Pass, Tier 2.2 (see MIGRATION_PLAN.md) -
    every chat.completions.create response already carries token usage
    for free (response.usage.prompt_tokens/completion_tokens); this
    reads it into the caller-supplied dict rather than changing any
    method's return type (see VisionAnalysisProvider.analyze_creative's
    own docstring for why). A no-op if the caller didn't ask (usage_sink
    is None) or a fake/stub response has no `usage` attribute.
    """
    if usage_sink is None:
        return
    # Follow-up to Checkpoint B (item 2): record the model the provider
    # says it ACTUALLY served. We request "gpt-5.5"; the response carries
    # "gpt-5.5-2026-04-23". Cost must be computed against the resolved
    # model, not against whatever an alias mapped to when pricing.yaml
    # was last written.
    reported_model = getattr(response, "model", None)
    if reported_model:
        usage_sink["reported_model"] = reported_model
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    usage_sink["prompt_tokens"] = usage.prompt_tokens
    usage_sink["completion_tokens"] = usage.completion_tokens


class OpenAIOCRAdapter:
    def __init__(self, model: str = "gpt-5.5", provider: str = "openai"):
        self.model = model
        self.provider = provider

    @property
    def client(self) -> OpenAI:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a fresh client
        # per access, not memoized on self - a memoized client, shared
        # across every concurrent call this adapter instance ever makes
        # (the registry hands out one adapter instance for the whole
        # process), broke under real concurrent use ("Cannot send a
        # request, as the client has been closed") once per-slide stage
        # calls started running concurrently. Construction itself does no
        # network I/O, so this stays just as lazy as the memoized version
        # ever was - only actually calling a method needs a real API key.
        return OpenAI(api_key=get_api_key("openai"), timeout=AI_PROVIDER_TIMEOUT_SECONDS)

    def extract_text(self, image_bytes: bytes, *, usage_sink: dict | None = None) -> OCRExtraction:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md): capture into
        # a local variable rather than chaining `self.client.chat...`
        # directly - since `client` (above) now constructs a fresh
        # object with no reference kept anywhere else, chaining would
        # let its refcount hit zero (and __del__ close its own
        # transport) the instant Python's `LOAD_ATTR` finishes reading
        # `.chat` off it, sometimes before the request the same
        # expression is about to make even completes. A local variable
        # keeps one live reference for this whole method body.
        client = self.client
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        _image_content_block(image_bytes),
                    ],
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ocr_extraction",
                    "schema": OCR_RESPONSE_SCHEMA,
                    "strict": True,
                },
            },
        )

        _populate_usage_sink(response, usage_sink)
        payload = json.loads(response.choices[0].message.content)
        return OCRExtraction(
            raw_text=payload["raw_text"],
            structured_blocks=payload["structured_blocks"],
        )


PRODUCT_ISOLATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "bounding_boxes": {
            "type": "array",
            "description": (
                "One entry per distinct instance of the featured product "
                "visible in the image. Usually exactly one."
            ),
            "items": {
                "type": "object",
                "properties": {
                    # Fractional coordinates (0.0-1.0) relative to image
                    # width/height - avoids needing to tell the model the
                    # image's exact pixel dimensions.
                    "x_min": {"type": "number"},
                    "y_min": {"type": "number"},
                    "x_max": {"type": "number"},
                    "y_max": {"type": "number"},
                    "confidence": {"type": "number"},
                    "notes": {"type": "string"},
                },
                "required": ["x_min", "y_min", "x_max", "y_max", "confidence", "notes"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["bounding_boxes"],
    "additionalProperties": False,
}

# Prompt text moved to app/prompts/ (WP-3) so it has an id, a version and a
# content hash. Re-exported under its original name: call sites and tests
# are deliberately untouched by the move.
PRODUCT_ISOLATION_PROMPT = _analysis_prompts.PRODUCT_ISOLATION.render()


class OpenAIProductIsolationAdapter:
    def __init__(self, model: str = "gpt-5.5", provider: str = "openai"):
        self.model = model
        self.provider = provider

    @property
    def client(self) -> OpenAI:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a fresh client
        # per access, not memoized on self - a memoized client, shared
        # across every concurrent call this adapter instance ever makes
        # (the registry hands out one adapter instance for the whole
        # process), broke under real concurrent use ("Cannot send a
        # request, as the client has been closed") once per-slide stage
        # calls started running concurrently. Construction itself does no
        # network I/O, so this stays just as lazy as the memoized version
        # ever was - only actually calling a method needs a real API key.
        return OpenAI(api_key=get_api_key("openai"), timeout=AI_PROVIDER_TIMEOUT_SECONDS)

    def isolate_product(self, image_bytes: bytes, *, usage_sink: dict | None = None) -> list[dict]:
        client = self.client
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PRODUCT_ISOLATION_PROMPT},
                        _image_content_block(image_bytes),
                    ],
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "product_isolation",
                    "schema": PRODUCT_ISOLATION_RESPONSE_SCHEMA,
                    "strict": True,
                },
            },
        )
        _populate_usage_sink(response, usage_sink)
        payload = json.loads(response.choices[0].message.content)
        return payload["bounding_boxes"]


class OpenAIVisionAnalysisAdapter:
    """
    General-purpose vision analysis - used by any Stage that needs a
    structured JSON description of an image against its own schema
    (Product Lock Profile Stage today; Creative Fingerprint Stage in M5
    will use this same adapter with a different schema/prompt).
    """

    def __init__(self, model: str = "gpt-5.5", provider: str = "openai"):
        self.model = model
        self.provider = provider

    @property
    def client(self) -> OpenAI:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a fresh client
        # per access, not memoized on self - a memoized client, shared
        # across every concurrent call this adapter instance ever makes
        # (the registry hands out one adapter instance for the whole
        # process), broke under real concurrent use ("Cannot send a
        # request, as the client has been closed") once per-slide stage
        # calls started running concurrently. Construction itself does no
        # network I/O, so this stays just as lazy as the memoized version
        # ever was - only actually calling a method needs a real API key.
        return OpenAI(api_key=get_api_key("openai"), timeout=AI_PROVIDER_TIMEOUT_SECONDS)

    def analyze_creative(
        self,
        image_bytes: bytes | list[bytes],
        prompt_spec: dict,
        response_schema: dict,
        *,
        usage_sink: dict | None = None,
    ) -> dict:
        prompt_text = prompt_spec["prompt"]
        schema_name = prompt_spec.get("schema_name", "analysis")
        images = [image_bytes] if isinstance(image_bytes, bytes) else image_bytes

        client = self.client
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        *[_image_content_block(image) for image in images],
                    ],
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": response_schema,
                    "strict": True,
                },
            },
        )
        _populate_usage_sink(response, usage_sink)
        return json.loads(response.choices[0].message.content)


class OpenAITextGenerationAdapter:
    """
    Text-only structured generation - no image input (plan §4). Used by
    the Marketing Analysis Stage, which is a second pass over the
    Creative Fingerprint's JSON, not a fresh look at the image itself.
    """

    def __init__(self, model: str = "gpt-5.5", provider: str = "openai"):
        self.model = model
        self.provider = provider

    @property
    def client(self) -> OpenAI:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a fresh client
        # per access, not memoized on self - a memoized client, shared
        # across every concurrent call this adapter instance ever makes
        # (the registry hands out one adapter instance for the whole
        # process), broke under real concurrent use ("Cannot send a
        # request, as the client has been closed") once per-slide stage
        # calls started running concurrently. Construction itself does no
        # network I/O, so this stays just as lazy as the memoized version
        # ever was - only actually calling a method needs a real API key.
        return OpenAI(api_key=get_api_key("openai"), timeout=AI_PROVIDER_TIMEOUT_SECONDS)

    def generate(self, prompt_spec: dict, response_schema: dict, *, usage_sink: dict | None = None) -> dict:
        prompt_text = prompt_spec["prompt"]
        schema_name = prompt_spec.get("schema_name", "generation")

        client = self.client
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt_text}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": response_schema,
                    "strict": True,
                },
            },
        )
        _populate_usage_sink(response, usage_sink)
        return json.loads(response.choices[0].message.content)


class OpenAIPromptGenerationAdapter:
    """
    Composes a provider-neutral Creative Specification from an existing
    ProductLockProfile + CreativeFingerprint (plan §4, §10) - no image
    input, by design: this is pure composition over prior analysis
    artifacts, never a fresh look at the Creative's image.

    Renamed from "recreation prompt" terminology in Phase 8.1 of the
    Generation -> Validation proof of loop (see MIGRATION_PLAN.md) - the
    output here is provider-neutral creative intent, not a compiled
    provider prompt (that's app.services.prompt_compiler's job, once an
    ImageGenerationProvider exists to compile one for).
    """

    def __init__(self, model: str = "gpt-5.5", provider: str = "openai"):
        self.model = model
        self.provider = provider

    @property
    def client(self) -> OpenAI:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a fresh client
        # per access, not memoized on self - a memoized client, shared
        # across every concurrent call this adapter instance ever makes
        # (the registry hands out one adapter instance for the whole
        # process), broke under real concurrent use ("Cannot send a
        # request, as the client has been closed") once per-slide stage
        # calls started running concurrently. Construction itself does no
        # network I/O, so this stays just as lazy as the memoized version
        # ever was - only actually calling a method needs a real API key.
        return OpenAI(api_key=get_api_key("openai"), timeout=AI_PROVIDER_TIMEOUT_SECONDS)

    def generate_creative_specification(
        self,
        lock_profile: dict | None,
        fingerprint: dict,
        response_schema: dict,
        *,
        usage_sink: dict | None = None,
    ) -> dict:
        # Story Slide feature (see MIGRATION_PLAN.md): lock_profile is
        # None for a slide with no detected product - the prompt must
        # not reference a Product Lock Profile at all in that case (an
        # empty dict there would read as "there IS a product, it's just
        # blank," inviting the model to invent one), and must explicitly
        # instruct against inventing a product.
        if lock_profile is not None:
            prompt_text = (
                "Given the following Product Lock Profile and Creative "
                "Fingerprint for a marketing creative, compose a "
                "provider-neutral creative specification for generating a "
                "NEW, visually original marketing image that features the "
                "exact same product (per the Product Lock Profile) but is "
                "NOT a copy of the original creative - it should feel "
                "visually distinct while preserving the underlying "
                "marketing strategy captured in the Creative Fingerprint.\n\n"
                f"Product Lock Profile (JSON):\n{json.dumps(lock_profile)}\n\n"
                f"Creative Fingerprint (JSON):\n{json.dumps(fingerprint)}\n\n"
                "Focus on composition, style direction, color palette, "
                "lighting, camera and perspective, background environment, "
                "mood, suggested text overlays, things to avoid, and aspect "
                "ratio."
            )
        else:
            prompt_text = (
                "Given the following Creative Fingerprint for a marketing "
                "creative, compose a provider-neutral creative "
                "specification for generating a NEW, visually original "
                "recreation of this creative's scene and narrative - it "
                "should feel visually distinct while preserving the "
                "underlying marketing strategy captured in the Creative "
                "Fingerprint. This slide does NOT feature a product - it "
                "is a narrative/story slide (e.g. a hook, a reaction shot, "
                "a text-only caption card). Do not invent, describe, or "
                "reference any product; focus purely on recreating the "
                "scene, composition, and mood.\n\n"
                f"Creative Fingerprint (JSON):\n{json.dumps(fingerprint)}\n\n"
                "Focus on composition, style direction, color palette, "
                "lighting, camera and perspective, background environment, "
                "mood, suggested text overlays, things to avoid, and aspect "
                "ratio."
            )

        client = self.client
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt_text}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "creative_specification",
                    "schema": response_schema,
                    "strict": True,
                },
            },
        )
        _populate_usage_sink(response, usage_sink)
        return json.loads(response.choices[0].message.content)


# OpenAI's Images API doesn't take an arbitrary aspect ratio - a small,
# explicit mapping to the closest of its supported fixed sizes,
# defaulting to square for anything unrecognized. Not trying to be exact
# for every possible ratio - Phase 8's goal is proving the loop, not a
# precise size-mapping table (see MIGRATION_PLAN.md's architecture
# direction: not optimizing for image quality in this phase).
#
# Matched by substring, not exact equality - a real live-verification
# call (Phase 8.3) exposed that PromptGenerationProvider's real
# aspect_ratio output is free text like "4:5 vertical marketing ad", not
# a bare ratio string; an exact-match lookup silently fell through to
# square for every real Creative Specification. Order matters: "2:3" is
# checked before "3:2" would otherwise never get a chance to match
# strings containing both as substrings of a longer phrase, though none
# of today's real outputs do - kept explicit for when they might.
# Real bug found live (see MIGRATION_PLAN.md): "3:4" - prompt_compiler.
# compile_generation_request's own unconditional, hardcoded default for
# every generation request in the app - had no entry here at all, so
# every OpenAI-generated image silently fell through to square
# (1024x1024) instead of portrait. Invisible until today: Nano Banana
# (the default image_generation provider, whose own _SUPPORTED_ASPECT_RATIOS
# already lists "3:4" directly) was always the one actually generating
# in real use - this table's gap only surfaced once the new fallback-
# on-provider-failure feature made OpenAI run for the first time in
# real, live testing.
_ASPECT_RATIO_TO_OPENAI_SIZE: list[tuple[str, str]] = [
    ("1:1", "1024x1024"),
    ("3:4", "1024x1536"),
    ("4:5", "1024x1536"),
    ("9:16", "1024x1536"),
    ("2:3", "1024x1536"),
    ("16:9", "1536x1024"),
    ("3:2", "1536x1024"),
]


def _size_for_aspect_ratio(aspect_ratio: str) -> str:
    for ratio, size in _ASPECT_RATIO_TO_OPENAI_SIZE:
        if ratio in aspect_ratio:
            return size
    return "1024x1024"


# Verified 2026-07-23 via direct inspection of the installed
# openai==2.46.0 SDK: Images.edit's `image` parameter is
# `Union[FileTypes, SequenceNotStr[FileTypes]]`, and gpt-image-1's
# real, documented limit (openai/developers.openai.com reference docs)
# is up to 16 images per edit call. Reference Selection (§7 of the ADR)
# is what actually enforces this via ProviderCapabilities.
# max_reference_images - this constant is that number's source of
# truth for this one adapter, not a separately-guessed value.
OPENAI_MAX_REFERENCE_IMAGES = 16

_EXTENSION_TO_MIME_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class OpenAIImageGenerationAdapter:
    """
    OpenAI's Images API - Phase 8.2 of the Generation -> Validation
    proof of loop; rewritten in Phase 9.3 of Product Lock v2 (see
    MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §6) to
    always call `images.edit` with the Generation Reference Set's
    images, never `images.generate` - reference_image_paths is a hard
    prerequisite now (app.ai_providers.base.GenerationRequest), so
    there is no text-only code path left to keep. All provider-specific
    prompt formatting lives here (_compile_openai_prompt), never
    upstream in app.services.prompt_compiler - the rest of the system
    only ever produces/consumes the provider-agnostic GenerationRequest.
    """

    def __init__(self, model: str = "gpt-5.5", provider: str = "openai"):
        self.model = model
        self.provider = provider

    @property
    def client(self) -> OpenAI:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a fresh client
        # per access, not memoized on self - a memoized client, shared
        # across every concurrent call this adapter instance ever makes
        # (the registry hands out one adapter instance for the whole
        # process), broke under real concurrent use ("Cannot send a
        # request, as the client has been closed") once per-slide stage
        # calls started running concurrently. Construction itself does no
        # network I/O, so this stays just as lazy as the memoized version
        # ever was - only actually calling a method needs a real API key.
        return OpenAI(api_key=get_api_key(self.provider), timeout=AI_PROVIDER_TIMEOUT_SECONDS)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_reference_images=True,
            max_reference_images=OPENAI_MAX_REFERENCE_IMAGES,
            supports_masking=True,
            supports_inpainting=True,
            supported_resolutions=["1024x1024", "1536x1024", "1024x1536"],
            # Phase 10.3 (see MIGRATION_PLAN.md's vNext ADR §2/§10.3) -
            # confirmed real via direct `openai==2.46.0` SDK introspection:
            # both images.edit/generate accept quality="high" and it's
            # genuinely applicable to gpt-image-1 (the model actually
            # configured), not just to dall-e-3. preferred_style is
            # deliberately left unset - the SDK's own docstring says
            # style is "only supported for dall-e-3," not confirmed for
            # gpt-image-1, so wiring it here would be an unverified guess.
            preferred_quality="high",
        )

    def generate_image(self, request: GenerationRequest) -> GeneratedImageResult:
        prompt = self._compile_openai_prompt(request)
        size = _size_for_aspect_ratio(request.aspect_ratio)
        reference_files = [_load_reference_file(path) for path in request.reference_image_paths]

        start = time.monotonic()
        client = self.client
        response = client.images.edit(
            model=self.model,
            image=reference_files,
            prompt=prompt,
            size=size,
            input_fidelity="high",
            quality=self.capabilities.preferred_quality,
            n=1,
        )
        elapsed = time.monotonic() - start

        image_data = response.data[0]
        if image_data.b64_json:
            image_bytes = base64.b64decode(image_data.b64_json)
        else:
            # Older API shapes (response_format="url") return a URL
            # instead of inline base64 - fetched directly rather than
            # requiring every caller to know which shape their model
            # returns.
            image_bytes = httpx.get(image_data.url, timeout=60.0).content

        return GeneratedImageResult(
            image_bytes=image_bytes,
            provider=self.provider,
            model=self.model,
            prompt_used=prompt,
            seed=None,  # OpenAI's public Images API doesn't expose one today.
            generation_time_seconds=elapsed,
        )

    def _compile_openai_prompt(self, request: GenerationRequest) -> str:
        """
        Provider-specific prompt formatting lives here, not in
        app.services.prompt_compiler - the rest of the system only ever
        sees the provider-agnostic GenerationRequest. No more "must
        include exactly" immutable-constraints text (Phase 9.3) - the
        reference images passed to images.edit are the only source of
        product identity now; the prompt describes scene/composition
        only, with one added, unconditional instruction telling the
        model to preserve what the reference images show rather than
        reinterpret it.

        story_mode (Story Slide feature, see MIGRATION_PLAN.md): the
        single reference image is the slide's own source photo, not a
        product to preserve identity of - "preserve the exact product"
        is meaningless (and risks the model inventing one to preserve)
        for a narrative slide with none. Swapped for an instruction to
        recreate the reference photo's scene as a new, original image
        with subtle variation, explicitly not a verbatim copy and
        explicitly not to add a product.
        """
        return _generation_prompts.compile_image_prompt(
            request.creative_intent,
            story_mode=request.story_mode,
            things_to_avoid=request.things_to_avoid,
        )


def _load_reference_file(path: str) -> tuple[str, bytes, str]:
    file_path = Path(path)
    mime_type = _EXTENSION_TO_MIME_TYPE.get(file_path.suffix.lower(), "image/jpeg")
    return (file_path.name, file_path.read_bytes(), mime_type)
