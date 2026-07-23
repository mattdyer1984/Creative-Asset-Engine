"""
Unit test for OpenAIOCRAdapter itself - unlike test_ocr_stage.py (which
uses FakeOCRProvider and never touches this class), this test exercises
the real adapter's request construction and response parsing against a
mocked OpenAI client, catching SDK-shape mismatches (e.g. a
response_format field that doesn't exist in the installed SDK version)
that a fake-provider test can't.

No real network call is made - openai.OpenAI.chat.completions.create is
replaced with a stub that returns a canned response shaped like a real
ChatCompletion.
"""

import base64
import json
from types import SimpleNamespace
from unittest.mock import patch

from app.ai_providers.base import GenerationRequest
from app.ai_providers.openai_adapter import OpenAIImageGenerationAdapter, OpenAIOCRAdapter


def _fake_chat_completion(content_dict: dict):
    """Mimics the small slice of a real ChatCompletion this adapter reads."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(content_dict)))]
    )


def test_openai_ocr_adapter_parses_structured_response():
    canned_response = _fake_chat_completion(
        {
            "raw_text": "20% Off Today Only",
            "structured_blocks": [{"text": "20% Off Today Only", "role": "cta"}],
        }
    )

    adapter = OpenAIOCRAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client  # forces lazy construction using the patched key

    with patch.object(
        client.chat.completions, "create", return_value=canned_response
    ) as mock_create:
        result = adapter.extract_text(b"fake-image-bytes")

    assert result.raw_text == "20% Off Today Only"
    assert result.structured_blocks == [{"text": "20% Off Today Only", "role": "cta"}]

    # Confirm the request was actually shaped the way we expect - this is
    # what would break if the installed SDK version didn't support this
    # response_format shape.
    _, kwargs = mock_create.call_args
    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["messages"][0]["content"][1]["type"] == "image_url"


def _fake_image_response(b64_json: str):
    """Mimics the small slice of a real ImagesResponse this adapter reads."""
    return SimpleNamespace(data=[SimpleNamespace(b64_json=b64_json, url=None)])


def test_openai_image_generation_adapter_parses_b64_response():
    """
    Phase 8.2 of the Generation -> Validation proof of loop (see
    MIGRATION_PLAN.md) - same real-SDK-shape discipline as the OCR
    adapter test above, no real network call.
    """
    fake_png_bytes = b"\x89PNG\r\n\x1a\nfake-bytes"
    canned_response = _fake_image_response(base64.b64encode(fake_png_bytes).decode())

    adapter = OpenAIImageGenerationAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Subject: a bottle of orange juice",
        immutable_constraints=["brand: Sunrise", "color: orange"],
        things_to_avoid=["cluttered background"],
        aspect_ratio="4:5",
    )

    with patch.object(client.images, "generate", return_value=canned_response) as mock_generate:
        result = adapter.generate_image(request)

    assert result.image_bytes == fake_png_bytes
    assert result.provider == "openai"
    assert result.model == "gpt-5.5"
    assert result.seed is None
    assert result.generation_time_seconds >= 0
    assert "Subject: a bottle of orange juice" in result.prompt_used
    assert "Must include exactly: brand: Sunrise; color: orange" in result.prompt_used
    assert "Avoid: cluttered background" in result.prompt_used

    _, kwargs = mock_generate.call_args
    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["prompt"] == result.prompt_used
    assert kwargs["size"] == "1024x1536"  # mapped from aspect_ratio "4:5"
    assert kwargs["n"] == 1


def test_openai_image_generation_adapter_omits_optional_prompt_sections_when_empty():
    canned_response = _fake_image_response(base64.b64encode(b"bytes").decode())
    adapter = OpenAIImageGenerationAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Subject: a bottle",
        immutable_constraints=[],
        things_to_avoid=[],
        aspect_ratio="unknown-ratio",
    )

    with patch.object(client.images, "generate", return_value=canned_response) as mock_generate:
        result = adapter.generate_image(request)

    assert result.prompt_used == "Subject: a bottle"
    assert "Must include exactly" not in result.prompt_used
    assert "Avoid" not in result.prompt_used

    _, kwargs = mock_generate.call_args
    assert kwargs["size"] == "1024x1024"  # unrecognized aspect ratio falls back to square
