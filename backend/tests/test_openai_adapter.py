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


def _fake_chat_completion(content_dict: dict, usage=None):
    """Mimics the small slice of a real ChatCompletion this adapter reads."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(content_dict)))],
        usage=usage,
    )


def test_openai_ocr_adapter_parses_structured_response():
    canned_response = _fake_chat_completion(
        {
            "raw_text": "20% Off Today Only",
            "structured_blocks": [
                {
                    "text": "20% Off Today Only",
                    "role": "cta",
                    "bounding_box": {"x_min": 0.1, "y_min": 0.8, "x_max": 0.9, "y_max": 0.95},
                }
            ],
        }
    )

    adapter = OpenAIOCRAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client  # a real client, used only as a target to patch methods on

    # Real-world-diagnosed fix (see MIGRATION_PLAN.md): `client` is now a
    # fresh-per-access property (no longer memoized, for thread-safety) -
    # pinning the class attribute to this one already-configured client
    # for the test's duration makes every `.client` access return the
    # same object, so patching its methods below still reaches the
    # adapter's own real call.
    with (
        patch.object(OpenAIOCRAdapter, "client", client),
        patch.object(client.chat.completions, "create", return_value=canned_response) as mock_create,
    ):
        result = adapter.extract_text(b"fake-image-bytes")

    assert result.raw_text == "20% Off Today Only"
    assert result.structured_blocks == [
        {
            "text": "20% Off Today Only",
            "role": "cta",
            "bounding_box": {"x_min": 0.1, "y_min": 0.8, "x_max": 0.9, "y_max": 0.95},
        }
    ]

    # Confirm the request was actually shaped the way we expect - this is
    # what would break if the installed SDK version didn't support this
    # response_format shape.
    _, kwargs = mock_create.call_args
    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["messages"][0]["content"][1]["type"] == "image_url"


def test_openai_ocr_adapter_populates_usage_sink_from_response_usage():
    """
    Optimisation & Stability Pass, Tier 2.2 (see MIGRATION_PLAN.md) -
    confirms the real OpenAI ChatCompletion.usage attribute names
    (prompt_tokens/completion_tokens), not just that the plumbing compiles.
    """
    usage = SimpleNamespace(prompt_tokens=80, completion_tokens=30, total_tokens=110)
    canned_response = _fake_chat_completion(
        {"raw_text": "x", "structured_blocks": []}, usage=usage
    )
    adapter = OpenAIOCRAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client

    usage_sink: dict = {}
    with (
        patch.object(OpenAIOCRAdapter, "client", client),
        patch.object(client.chat.completions, "create", return_value=canned_response),
    ):
        adapter.extract_text(b"fake-image-bytes", usage_sink=usage_sink)

    assert usage_sink == {"prompt_tokens": 80, "completion_tokens": 30}


def test_openai_ocr_adapter_usage_sink_untouched_when_response_has_no_usage():
    """A None usage_sink (the default, every pre-existing call site) must stay a no-op."""
    canned_response = _fake_chat_completion({"raw_text": "x", "structured_blocks": []})
    adapter = OpenAIOCRAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client

    with (
        patch.object(OpenAIOCRAdapter, "client", client),
        patch.object(client.chat.completions, "create", return_value=canned_response),
    ):
        # No usage_sink passed at all - must not raise.
        adapter.extract_text(b"fake-image-bytes")


def _fake_image_response(b64_json: str):
    """Mimics the small slice of a real ImagesResponse this adapter reads."""
    return SimpleNamespace(data=[SimpleNamespace(b64_json=b64_json, url=None)])


def _make_reference_image_file(tmp_path, filename="ref.jpg") -> str:
    path = tmp_path / filename
    path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    return str(path)


def test_openai_image_generation_adapter_parses_b64_response(tmp_path):
    """
    Phase 8.2 of the Generation -> Validation proof of loop; rewritten
    in Phase 9.3 of Product Lock v2 (see MIGRATION_PLAN.md) to call
    images.edit with reference images, not images.generate - same
    real-SDK-shape discipline as the OCR adapter test above, no real
    network call.
    """
    fake_png_bytes = b"\x89PNG\r\n\x1a\nfake-bytes"
    canned_response = _fake_image_response(base64.b64encode(fake_png_bytes).decode())

    adapter = OpenAIImageGenerationAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Composition: off-center product shot",
        reference_image_paths=[_make_reference_image_file(tmp_path)],
        things_to_avoid=["cluttered background"],
        aspect_ratio="4:5",
    )

    # Real-world-diagnosed fix (see MIGRATION_PLAN.md): `client` is now a
    # fresh-per-access property (no longer memoized, for thread-safety) -
    # see the OCR adapter test above for the full reasoning.
    with (
        patch.object(OpenAIImageGenerationAdapter, "client", client),
        patch.object(client.images, "edit", return_value=canned_response) as mock_edit,
    ):
        result = adapter.generate_image(request)

    assert result.image_bytes == fake_png_bytes
    assert result.provider == "openai"
    assert result.model == "gpt-5.5"
    assert result.seed is None
    assert result.generation_time_seconds >= 0
    assert "Composition: off-center product shot" in result.prompt_used
    assert "Preserve the exact product shown in the reference images" in result.prompt_used
    assert "Avoid: cluttered background" in result.prompt_used

    _, kwargs = mock_edit.call_args
    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["prompt"] == result.prompt_used
    assert kwargs["size"] == "1024x1536"  # mapped from aspect_ratio "4:5"
    assert kwargs["n"] == 1
    assert kwargs["input_fidelity"] == "high"
    assert len(kwargs["image"]) == 1
    filename, contents, mime_type = kwargs["image"][0]
    assert filename == "ref.jpg"
    assert contents == b"\xff\xd8\xff\xe0fake-jpeg-bytes"
    assert mime_type == "image/jpeg"


def test_openai_image_generation_adapter_omits_things_to_avoid_when_empty(tmp_path):
    canned_response = _fake_image_response(base64.b64encode(b"bytes").decode())
    adapter = OpenAIImageGenerationAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Composition: a bottle on a counter",
        reference_image_paths=[_make_reference_image_file(tmp_path)],
        things_to_avoid=[],
        aspect_ratio="unknown-ratio",
    )

    with (
        patch.object(OpenAIImageGenerationAdapter, "client", client),
        patch.object(client.images, "edit", return_value=canned_response) as mock_edit,
    ):
        result = adapter.generate_image(request)

    assert "Composition: a bottle on a counter" in result.prompt_used
    assert "Preserve the exact product shown in the reference images" in result.prompt_used
    assert "Avoid" not in result.prompt_used

    _, kwargs = mock_edit.call_args
    assert kwargs["size"] == "1024x1024"  # unrecognized aspect ratio falls back to square


def test_openai_image_generation_adapter_matches_aspect_ratio_by_substring(tmp_path):
    """
    Real gap found live-verifying Phase 8.3 (see MIGRATION_PLAN.md):
    PromptGenerationProvider's real output is free text like "4:5
    vertical marketing ad", not a bare ratio string - an exact-match
    lookup silently fell through to square for every real Creative
    Specification.
    """
    canned_response = _fake_image_response(base64.b64encode(b"bytes").decode())
    adapter = OpenAIImageGenerationAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Composition: a bottle",
        reference_image_paths=[_make_reference_image_file(tmp_path)],
        things_to_avoid=[],
        aspect_ratio="4:5 vertical marketing ad",
    )

    with (
        patch.object(OpenAIImageGenerationAdapter, "client", client),
        patch.object(client.images, "edit", return_value=canned_response) as mock_edit,
    ):
        adapter.generate_image(request)

    _, kwargs = mock_edit.call_args
    assert kwargs["size"] == "1024x1536"


def test_openai_image_generation_adapter_maps_the_apps_real_default_aspect_ratio(tmp_path):
    """
    Real bug found live (see MIGRATION_PLAN.md): "3:4" is
    prompt_compiler.compile_generation_request's own unconditional,
    hardcoded aspect_ratio for every real generation request the app
    ever sends - and this adapter had no mapping entry for it at all,
    silently falling through to square. Invisible until a real 503 from
    Nano Banana (whose own mapping does include "3:4") triggered the
    fallback-on-failure feature and OpenAI actually generated for the
    first time in live use, at the wrong ratio.
    """
    canned_response = _fake_image_response(base64.b64encode(b"bytes").decode())
    adapter = OpenAIImageGenerationAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Composition: a bottle",
        reference_image_paths=[_make_reference_image_file(tmp_path)],
        things_to_avoid=[],
        aspect_ratio="3:4",
    )

    with (
        patch.object(OpenAIImageGenerationAdapter, "client", client),
        patch.object(client.images, "edit", return_value=canned_response) as mock_edit,
    ):
        adapter.generate_image(request)

    _, kwargs = mock_edit.call_args
    assert kwargs["size"] == "1024x1536"


def test_openai_image_generation_adapter_sends_multiple_reference_images(tmp_path):
    canned_response = _fake_image_response(base64.b64encode(b"bytes").decode())
    adapter = OpenAIImageGenerationAdapter(model="gpt-5.5")

    with patch("app.ai_providers.openai_adapter.get_api_key", return_value="sk-fake-test-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Composition: a bottle",
        reference_image_paths=[
            _make_reference_image_file(tmp_path, "front.jpg"),
            _make_reference_image_file(tmp_path, "side.jpg"),
        ],
        things_to_avoid=[],
        aspect_ratio="1:1",
    )

    with (
        patch.object(OpenAIImageGenerationAdapter, "client", client),
        patch.object(client.images, "edit", return_value=canned_response) as mock_edit,
    ):
        adapter.generate_image(request)

    _, kwargs = mock_edit.call_args
    assert [f[0] for f in kwargs["image"]] == ["front.jpg", "side.jpg"]


def test_openai_image_generation_adapter_capabilities():
    adapter = OpenAIImageGenerationAdapter(model="gpt-image-1")

    capabilities = adapter.capabilities

    assert capabilities.supports_reference_images is True
    assert capabilities.max_reference_images == 16
