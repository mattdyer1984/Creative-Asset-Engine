"""
Gemini adapters for the OCR and Vision Analysis capabilities - a
real-world-driven cost/quality change, not an architecture-first one
(see MIGRATION_PLAN.md): OCR, Product Lock Profile, and Creative
Fingerprint are the three multimodal analysis tasks the user identified
as strong fits for Gemini (fast, dramatically cheaper than GPT-5.5, and,
per this project's own Nano Banana experience, at least as capable at
reading/reasoning about printed text). Product Isolation, Scene
Intelligence, Reference Scoring, and every quality-gating vision task
(Identity Validation, per-field Image Validation, Photorealism) are
deliberately NOT migrated here - a narrower scope the user chose
explicitly, to avoid re-calibrating the whole quality bar (which
OpenAI/GPT-5.5 currently judges) at the same time as the pipeline
stages it judges change underneath it.

Model IDs are `gemini-flash-latest`/`gemini-pro-latest` (providers.yaml/
config.py's `ModelsConfig.gemini`), NOT the user's literally-requested
`gemini-2.5-flash`/`gemini-2.5-pro` - a real, live-discovered
substitution, not a guess: both 2.5-dated models returned a real 404
("This model ... is no longer available to new users") against this
account during live verification (2026-07-24), and the next dated
snapshot tried was already retired too. Google's own auto-updating
-latest aliases avoid this exact deprecation problem recurring - see
MIGRATION_PLAN.md for the full live-verification trail.

Distinct from `nano_banana_adapter.py`: that file's models
(`gemini-3.1-flash-image-preview` etc.) are the Gemini *image
generation* family ("Nano Banana"); the flash/pro models here are the
general-purpose multimodal *analysis* family - same underlying Google
AI Studio account and API, genuinely different model family and use
case, so this file uses its own `provider = "gemini"` identity
(distinct from `nano_banana`) for AnalysisRun bookkeeping accuracy -
callers/dashboards that group by `AnalysisRun.provider` should be able
to tell "this ran on Nano Banana" from "this ran on Gemini" at a
glance.

**Deliberately reuses the `nano_banana` API key** (`get_api_key
("nano_banana")`, not `get_api_key("gemini")`) rather than requiring a
second keychain entry - both are the exact same Google AI Studio
account/credential; registering it under `self.provider`'s own name
would demand a redundant keyring.set_password call for a key that
already works, for zero real benefit. If a genuinely different Gemini
account is ever needed for analysis vs. generation, this is the one
line to change.

Structured output uses `response_json_schema` (not `response_schema`,
Gemini's other, deliberately restricted OpenAPI-3.0-subset field) -
confirmed via direct introspection of the installed
`google-genai==2.14.0` SDK that `response_json_schema` supports
`additionalProperties`/`required`, matching the exact JSON Schema
constructs this codebase's existing schemas (OCR_RESPONSE_SCHEMA,
PRODUCT_LOCK_PROFILE_SCHEMA, CREATIVE_FINGERPRINT_SCHEMA, ...) already
use - the same schema dicts already written for OpenAI's Structured
Outputs mode are reused here completely unchanged, with zero
translation layer needed. `response_mime_type="application/json"` must
also be set alongside it; without it, `response_json_schema` is
ignored.

Live-verified 2026-07-24 (see MIGRATION_PLAN.md) - real OCR, Product
Lock Profile, and Creative Fingerprint reruns against a real slide/
product, all three succeeding with real, coherent structured output
after the model-ID substitution above.
"""

import io
import json

from google import genai
from google.genai import types
from PIL import Image

from app.ai_providers.base import OCRExtraction
from app.ai_providers.config import AI_PROVIDER_TIMEOUT_SECONDS, get_api_key
from app.ai_providers.openai_adapter import OCR_PROMPT, OCR_RESPONSE_SCHEMA


def _images_from_bytes(image_bytes: bytes | list[bytes]) -> list[Image.Image]:
    raw_images = [image_bytes] if isinstance(image_bytes, bytes) else image_bytes
    return [Image.open(io.BytesIO(raw)) for raw in raw_images]


def _populate_usage_sink(response, usage_sink: dict | None) -> None:
    """
    Optimisation & Stability Pass, Tier 2.2 (see MIGRATION_PLAN.md) -
    mirrors openai_adapter.py's helper of the same name/purpose. Gemini
    reports usage as response.usage_metadata.prompt_token_count/
    candidates_token_count (confirmed via direct google-genai==2.14.0
    introspection), not response.usage - a real, different field name/
    shape from OpenAI's, not a copy-paste of that helper.
    """
    if usage_sink is None:
        return
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return
    usage_sink["prompt_tokens"] = usage.prompt_token_count
    usage_sink["completion_tokens"] = usage.candidates_token_count


class GeminiOCRAdapter:
    def __init__(self, model: str = "gemini-flash-latest", provider: str = "gemini"):
        self.model = model
        self.provider = provider

    @property
    def client(self) -> genai.Client:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a fresh
        # client per access, not memoized on self - see
        # app.ai_providers.openai_adapter's identical fix for the full
        # reasoning (a memoized, registry-shared client broke under real
        # concurrent use once per-slide stage calls started running
        # concurrently).
        return genai.Client(
            api_key=get_api_key("nano_banana"),
            http_options=types.HttpOptions(timeout=AI_PROVIDER_TIMEOUT_SECONDS * 1000),
        )

    def extract_text(self, image_bytes: bytes, *, usage_sink: dict | None = None) -> OCRExtraction:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md and
        # openai_adapter.py's identical fix for the full reasoning) -
        # captured into a local variable, not chained directly off
        # `self.client`: `genai.Client` has a real `__del__` that closes
        # its own httpx transport, and chaining would let its refcount
        # hit zero mid-expression, sometimes closing the transport
        # before the very request that same expression was making had
        # finished - confirmed live ("Cannot send a request, as the
        # client has been closed").
        client = self.client
        response = client.models.generate_content(
            model=self.model,
            contents=[OCR_PROMPT, *_images_from_bytes(image_bytes)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=OCR_RESPONSE_SCHEMA,
            ),
        )
        _populate_usage_sink(response, usage_sink)
        payload = json.loads(response.text)
        return OCRExtraction(
            raw_text=payload["raw_text"],
            structured_blocks=payload["structured_blocks"],
        )


class GeminiVisionAnalysisAdapter:
    """
    General-purpose vision analysis, mirroring OpenAIVisionAnalysisAdapter's
    schema-agnostic design - the caller (Product Lock Profile Stage,
    Creative Fingerprint Stage) supplies its own prompt and response_schema;
    this adapter has no schema knowledge of its own.
    """

    def __init__(self, model: str = "gemini-pro-latest", provider: str = "gemini"):
        self.model = model
        self.provider = provider

    @property
    def client(self) -> genai.Client:
        # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a fresh
        # client per access, not memoized on self - see
        # app.ai_providers.openai_adapter's identical fix for the full
        # reasoning (a memoized, registry-shared client broke under real
        # concurrent use once per-slide stage calls started running
        # concurrently).
        return genai.Client(
            api_key=get_api_key("nano_banana"),
            http_options=types.HttpOptions(timeout=AI_PROVIDER_TIMEOUT_SECONDS * 1000),
        )

    def analyze_creative(
        self,
        image_bytes: bytes | list[bytes],
        prompt_spec: dict,
        response_schema: dict,
        *,
        usage_sink: dict | None = None,
    ) -> dict:
        prompt_text = prompt_spec["prompt"]
        images = _images_from_bytes(image_bytes)

        client = self.client
        response = client.models.generate_content(
            model=self.model,
            contents=[prompt_text, *images],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=response_schema,
            ),
        )
        _populate_usage_sink(response, usage_sink)
        return json.loads(response.text)
