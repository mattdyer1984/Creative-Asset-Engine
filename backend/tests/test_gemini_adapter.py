"""
Unit tests for GeminiOCRAdapter/GeminiVisionAnalysisAdapter (real-world-
driven cost/quality change, see MIGRATION_PLAN.md) - same no-real-
network-call discipline as test_nano_banana_adapter.py: the mocked
`generate_content` response only needs a real `.text` attribute, since
that's the only thing these adapters read off it (unlike nano_banana's
image adapter, which reads `candidates[0].content.parts[...].inline_data`).
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from app.ai_providers.gemini_adapter import GeminiOCRAdapter, GeminiVisionAnalysisAdapter


def _make_image_bytes() -> bytes:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color=(200, 150, 100)).save(buf, format="JPEG")
    return buf.getvalue()


def _fake_response(payload: dict, usage_metadata=None):
    return SimpleNamespace(text=json.dumps(payload), usage_metadata=usage_metadata)


def test_ocr_adapter_reuses_the_nano_banana_api_key():
    adapter = GeminiOCRAdapter()
    with patch(
        "app.ai_providers.gemini_adapter.get_api_key", return_value="fake-key"
    ) as mock_get_key:
        _ = adapter.client
    mock_get_key.assert_called_once_with("nano_banana")


def test_ocr_adapter_extracts_text_and_structured_blocks():
    payload = {
        "raw_text": "Sunrise Juice",
        "structured_blocks": [
            {
                "text": "Sunrise",
                "role": "logo_text",
                "bounding_box": {"x_min": 0.1, "y_min": 0.1, "x_max": 0.4, "y_max": 0.2},
            }
        ],
    }
    adapter = GeminiOCRAdapter()
    with patch("app.ai_providers.gemini_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    # Real-world-diagnosed fix (see MIGRATION_PLAN.md): `client` is now a
    # fresh-per-access property (no longer memoized, for thread-safety) -
    # pinning the class attribute to this one already-configured client
    # for the test's duration makes every `.client` access return the
    # same object, so patching its methods below still reaches the
    # adapter's own real call.
    with (
        patch.object(GeminiOCRAdapter, "client", client),
        patch.object(client.models, "generate_content", return_value=_fake_response(payload)) as mock_call,
    ):
        result = adapter.extract_text(_make_image_bytes())

    assert result.raw_text == "Sunrise Juice"
    assert result.structured_blocks == payload["structured_blocks"]

    _, kwargs = mock_call.call_args
    assert kwargs["model"] == "gemini-flash-latest"
    assert kwargs["config"].response_mime_type == "application/json"
    assert kwargs["config"].response_json_schema is not None
    contents = kwargs["contents"]
    assert len(contents) == 2  # prompt text + one PIL image
    assert isinstance(contents[0], str)
    assert isinstance(contents[1], Image.Image)


def test_vision_analysis_adapter_single_image():
    payload = {"product_category": "beverage"}
    adapter = GeminiVisionAnalysisAdapter()
    with patch("app.ai_providers.gemini_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    with (
        patch.object(GeminiVisionAnalysisAdapter, "client", client),
        patch.object(client.models, "generate_content", return_value=_fake_response(payload)) as mock_call,
    ):
        result = adapter.analyze_creative(
            image_bytes=_make_image_bytes(),
            prompt_spec={"prompt": "Analyze this product.", "schema_name": "product_lock_profile"},
            response_schema={"type": "object", "properties": {}},
        )

    assert result == payload
    _, kwargs = mock_call.call_args
    assert kwargs["model"] == "gemini-pro-latest"
    contents = kwargs["contents"]
    assert contents[0] == "Analyze this product."
    assert len(contents) == 2  # prompt + one image


def test_vision_analysis_adapter_multi_image():
    """
    Mirrors OpenAIVisionAnalysisAdapter's multi-image support (Phase 9.4,
    identity_validation's list[bytes] case) - both images must reach
    `contents` as PIL.Image.Image objects.
    """
    payload = {"identity_passed": True}
    adapter = GeminiVisionAnalysisAdapter()
    with patch("app.ai_providers.gemini_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    with (
        patch.object(GeminiVisionAnalysisAdapter, "client", client),
        patch.object(client.models, "generate_content", return_value=_fake_response(payload)) as mock_call,
    ):
        result = adapter.analyze_creative(
            image_bytes=[_make_image_bytes(), _make_image_bytes()],
            prompt_spec={"prompt": "Compare these images.", "schema_name": "identity_validation"},
            response_schema={"type": "object", "properties": {}},
        )

    assert result == payload
    _, kwargs = mock_call.call_args
    contents = kwargs["contents"]
    assert len(contents) == 3  # prompt + two images
    assert all(isinstance(c, Image.Image) for c in contents[1:])


def test_ocr_adapter_populates_usage_sink_from_usage_metadata():
    """
    Optimisation & Stability Pass, Tier 2.2 (see MIGRATION_PLAN.md) -
    confirms the real google-genai response attribute names
    (usage_metadata.prompt_token_count/candidates_token_count), not just
    that the plumbing compiles.
    """
    adapter = GeminiOCRAdapter()
    with patch("app.ai_providers.gemini_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    usage_metadata = SimpleNamespace(prompt_token_count=120, candidates_token_count=45)
    response = _fake_response(
        {"raw_text": "x", "structured_blocks": []}, usage_metadata=usage_metadata
    )
    usage_sink: dict = {}

    with (
        patch.object(GeminiOCRAdapter, "client", client),
        patch.object(client.models, "generate_content", return_value=response),
    ):
        adapter.extract_text(_make_image_bytes(), usage_sink=usage_sink)

    assert usage_sink == {"prompt_tokens": 120, "completion_tokens": 45}


def test_ocr_adapter_usage_sink_untouched_when_response_has_no_usage_metadata():
    """A None usage_sink (the default, every pre-existing call site) must stay a no-op."""
    adapter = GeminiOCRAdapter()
    with patch("app.ai_providers.gemini_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    with (
        patch.object(GeminiOCRAdapter, "client", client),
        patch.object(
            client.models, "generate_content", return_value=_fake_response({"raw_text": "x", "structured_blocks": []})
        ),
    ):
        # No usage_sink passed at all - must not raise.
        adapter.extract_text(_make_image_bytes())


def test_vision_analysis_adapter_reuses_caller_supplied_schema_verbatim():
    schema = {
        "type": "object",
        "properties": {"foo": {"type": "string"}},
        "required": ["foo"],
        "additionalProperties": False,
    }
    adapter = GeminiVisionAnalysisAdapter()
    with patch("app.ai_providers.gemini_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    with (
        patch.object(GeminiVisionAnalysisAdapter, "client", client),
        patch.object(client.models, "generate_content", return_value=_fake_response({"foo": "bar"})) as mock_call,
    ):
        adapter.analyze_creative(
            image_bytes=_make_image_bytes(),
            prompt_spec={"prompt": "p", "schema_name": "s"},
            response_schema=schema,
        )

    _, kwargs = mock_call.call_args
    assert kwargs["config"].response_json_schema == schema
