"""
Nano Banana (Google's Gemini image generation models) adapter -
Phase 10.1 of the AI Creative Engine vNext (see MIGRATION_PLAN.md's ADR
§10). **Nano Banana Lite is the default `image_generation` provider**
(providers.yaml, `ProvidersConfig.image_generation`) - an implementation
choice the user made explicitly, not an architectural one: this class
implements the same `ImageGenerationProvider` Protocol as
`OpenAIImageGenerationAdapter`, which remains fully intact and
selectable (`registry.image_generation("openai")`) without any code
change - the provider abstraction is exactly what makes swapping the
default a one-line providers.yaml change, not a rewrite.

Built against the real, installed google-genai SDK (2.14.0), not
guessed: every method/field referenced here was confirmed via direct
`inspect.signature`/`model_fields` introspection of the installed
package before being used, the same discipline this project already
applied to the OpenAI SDK (images.edit/input_fidelity, quality/style).

"Nano Banana" is the model family's informal/marketing name; the real,
callable model IDs are versioned - `gemini-2.5-flash-image` (the
original/legacy tier, informally "Nano Banana"), `gemini-3.1-flash-lite-image`
(**"Nano Banana Lite"/"Nano Banana 2 Lite"** - the fastest, cheapest
tier, "engineered for velocity and scale," per Google's own developer
docs - confirmed 2026-07-23, this is the default `model` below),
`gemini-3.1-flash-image-preview` ("Nano Banana 2," the general-purpose
tier), and `gemini-3-pro-image-preview` ("Nano Banana Pro," the premium
tier). `model` is a plain constructor parameter here exactly like every
other adapter in this file, not hardcoded, so providers.yaml picks the
actual model string, not this class - the Lite default lives in
`ModelsConfig.nano_banana`, not baked into this file, so switching
tiers later is also a one-line config change.

NOT YET LIVE-VERIFIED - no Gemini/Google API key has been added to this
environment as of this sub-phase. Every claim below about the SDK's own
shape (parameter names, response structure) is grounded in real
introspection of the installed library; claims about runtime behavior
(does a real call actually succeed, what does a real response look
like, does aspect_ratio actually produce what it says) are NOT verified
against a real call, unlike every other live-verified piece of this
codebase. Flagged here rather than silently treated as equivalent to
the OpenAI adapter's live-verified status - add a key
(keyring.set_password('creative-asset-engine', 'nano_banana_api_key',
'<key>') or NANO_BANANA_API_KEY env var, per get_api_key's existing,
already-generic lookup) and re-run this adapter's tests with the fake
swapped for a real call to close that gap.

Multi-image conditioning is core to this model family (not an edge
case bolted on, unlike OpenAI's separate generate/edit split) -
generate_content's `contents` parameter natively accepts a mixed list
of a text prompt and PIL.Image.Image objects, so there's no separate
"edit" endpoint/parameter to branch on here.
"""

import time

from google import genai
from google.genai import types
from PIL import Image

from app.ai_providers.base import GeneratedImageResult, GenerationRequest, ProviderCapabilities
from app.ai_providers.config import get_api_key

# Verified 2026-07-23 via direct introspection of google-genai==2.14.0's
# types.ImageConfig.model_fields["aspect_ratio"] docstring: "Supported
# values are '1:1', '2:3', '3:2', '3:4', '4:3', '9:16', '16:9', and
# '21:9'." Matched by substring against our free-text aspect_ratio
# field, same reasoning OpenAI's own _size_for_aspect_ratio already
# uses - a real Creative Specification's aspect_ratio is free text like
# "4:5 vertical marketing ad", not a bare ratio string.
_SUPPORTED_ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]

# No official multi-image-conditioning count limit is published as of
# this sub-phase (unlike OpenAI's documented 16) - kept conservative
# and explicitly flagged as a placeholder pending real testing once a
# key is available, rather than assumed unlimited.
NANO_BANANA_MAX_REFERENCE_IMAGES = 14

_EXTENSION_TO_MIME_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _aspect_ratio_for(aspect_ratio: str) -> str:
    for supported in _SUPPORTED_ASPECT_RATIOS:
        if supported in aspect_ratio:
            return supported
    return "1:1"


class NanoBananaImageGenerationAdapter:
    """
    Google's Gemini image models via google-genai's Client.models.
    generate_content - see this module's docstring for what is and
    isn't verified yet.
    """

    def __init__(self, model: str = "gemini-3.1-flash-lite-image", provider: str = "nano_banana"):
        self.model = model
        self.provider = provider
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=get_api_key(self.provider))
        return self._client

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_reference_images=True,
            max_reference_images=NANO_BANANA_MAX_REFERENCE_IMAGES,
            supports_masking=False,
            supports_inpainting=False,
            supported_resolutions=_SUPPORTED_ASPECT_RATIOS,
        )

    def generate_image(self, request: GenerationRequest) -> GeneratedImageResult:
        prompt = self._compile_prompt(request)
        reference_images = [Image.open(path) for path in request.reference_image_paths]
        aspect_ratio = _aspect_ratio_for(request.aspect_ratio)

        start = time.monotonic()
        response = self.client.models.generate_content(
            model=self.model,
            contents=[prompt, *reference_images],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            ),
        )
        elapsed = time.monotonic() - start

        image_bytes = self._extract_image_bytes(response)

        return GeneratedImageResult(
            image_bytes=image_bytes,
            provider=self.provider,
            model=self.model,
            prompt_used=prompt,
            seed=None,  # Gemini's image generation doesn't expose a seed today either.
            generation_time_seconds=elapsed,
        )

    @staticmethod
    def _extract_image_bytes(response) -> bytes:
        """
        Verified real response shape via introspection:
        GenerateContentResponse.candidates[0].content.parts[i].
        inline_data.data - a Part carries either text or inline_data,
        not both, so this returns the first part that actually has
        image bytes rather than assuming a fixed index.
        """
        for candidate in response.candidates or []:
            for part in (candidate.content.parts if candidate.content else None) or []:
                if part.inline_data is not None and part.inline_data.data:
                    return part.inline_data.data
        raise RuntimeError(
            "Nano Banana response contained no image data - the model may have "
            "returned only text (e.g. a refusal or clarifying question)."
        )

    def _compile_prompt(self, request: GenerationRequest) -> str:
        """
        Provider-specific prompt formatting, mirroring
        OpenAIImageGenerationAdapter._compile_openai_prompt - the rest
        of the system only ever sees the provider-agnostic
        GenerationRequest.
        """
        parts = [
            request.creative_intent,
            "Preserve the exact product shown in the reference images - its shape, "
            "proportions, colors, materials, packaging, and any visible branding or "
            "text. Only the scene, composition, lighting, and background described "
            "above should differ from the references.",
        ]
        if request.things_to_avoid:
            parts.append("Avoid: " + "; ".join(request.things_to_avoid))
        return "\n\n".join(parts)
