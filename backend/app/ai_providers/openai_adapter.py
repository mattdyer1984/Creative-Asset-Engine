"""
OpenAI adapters for the OCR, Product Isolation, and Vision Analysis
capabilities (plan §4).

Uses OpenAI's Structured Outputs mode (response_format=json_schema,
strict=True) throughout, so responses are guaranteed to match the given
schema - no manual parsing/validation of loosely-structured text needed.
"""

import base64
import json

from openai import OpenAI

from app.ai_providers.base import OCRExtraction
from app.ai_providers.config import get_api_key

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
                },
                "required": ["text", "role"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["raw_text", "structured_blocks"],
    "additionalProperties": False,
}

OCR_PROMPT = (
    "Extract all visible text from this marketing image. Return the "
    "complete raw text, plus a structured breakdown of each distinct "
    "text element and its marketing role."
)


def _image_content_block(image_bytes: bytes) -> dict:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}


class OpenAIOCRAdapter:
    def __init__(self, model: str = "gpt-5.5"):
        self.model = model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        # Lazy init: importing/instantiating this adapter never requires
        # an API key to already be configured - only actually calling
        # extract_text() does.
        if self._client is None:
            self._client = OpenAI(api_key=get_api_key("openai"))
        return self._client

    def extract_text(self, image_bytes: bytes) -> OCRExtraction:
        response = self.client.chat.completions.create(
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

PRODUCT_ISOLATION_PROMPT = (
    "Identify the bounding box(es) of the featured product in this "
    "marketing image - the physical product being sold, not background "
    "props, people, or decorative elements. Return coordinates as "
    "fractions of the image width/height (0.0 to 1.0), a confidence "
    "score, and brief notes on what you identified."
)


class OpenAIProductIsolationAdapter:
    def __init__(self, model: str = "gpt-5.5"):
        self.model = model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=get_api_key("openai"))
        return self._client

    def isolate_product(self, image_bytes: bytes) -> list[dict]:
        response = self.client.chat.completions.create(
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
        payload = json.loads(response.choices[0].message.content)
        return payload["bounding_boxes"]


class OpenAIVisionAnalysisAdapter:
    """
    General-purpose vision analysis - used by any Stage that needs a
    structured JSON description of an image against its own schema
    (Product Lock Profile Stage today; Creative Fingerprint Stage in M5
    will use this same adapter with a different schema/prompt).
    """

    def __init__(self, model: str = "gpt-5.5"):
        self.model = model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=get_api_key("openai"))
        return self._client

    def analyze_creative(
        self, image_bytes: bytes, prompt_spec: dict, response_schema: dict
    ) -> dict:
        prompt_text = prompt_spec["prompt"]
        schema_name = prompt_spec.get("schema_name", "analysis")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        _image_content_block(image_bytes),
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
        return json.loads(response.choices[0].message.content)


class OpenAITextGenerationAdapter:
    """
    Text-only structured generation - no image input (plan §4). Used by
    the Marketing Analysis Stage, which is a second pass over the
    Creative Fingerprint's JSON, not a fresh look at the image itself.
    """

    def __init__(self, model: str = "gpt-5.5"):
        self.model = model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=get_api_key("openai"))
        return self._client

    def generate(self, prompt_spec: dict, response_schema: dict) -> dict:
        prompt_text = prompt_spec["prompt"]
        schema_name = prompt_spec.get("schema_name", "generation")

        response = self.client.chat.completions.create(
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
        return json.loads(response.choices[0].message.content)


class OpenAIPromptGenerationAdapter:
    """
    Composes a provider-neutral Recreation Prompt from an existing
    ProductLockProfile + CreativeFingerprint (plan §4, §10) - no image
    input, by design: this is pure composition over prior analysis
    artifacts, never a fresh look at the Creative's image.
    """

    def __init__(self, model: str = "gpt-5.5"):
        self.model = model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=get_api_key("openai"))
        return self._client

    def generate_recreation_prompt(
        self, lock_profile: dict, fingerprint: dict, response_schema: dict
    ) -> dict:
        prompt_text = (
            "Given the following Product Lock Profile and Creative "
            "Fingerprint for a marketing creative, compose a "
            "provider-neutral recreation prompt specification for "
            "generating a NEW, visually original marketing image that "
            "features the exact same product (per the Product Lock "
            "Profile) but is NOT a copy of the original creative - it "
            "should feel visually distinct while preserving the "
            "underlying marketing strategy captured in the Creative "
            "Fingerprint.\n\n"
            f"Product Lock Profile (JSON):\n{json.dumps(lock_profile)}\n\n"
            f"Creative Fingerprint (JSON):\n{json.dumps(fingerprint)}\n\n"
            "Focus on composition, style direction, color palette, "
            "lighting, camera and perspective, background environment, "
            "mood, suggested text overlays, things to avoid, and aspect "
            "ratio."
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt_text}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "recreation_prompt",
                    "schema": response_schema,
                    "strict": True,
                },
            },
        )
        return json.loads(response.choices[0].message.content)
