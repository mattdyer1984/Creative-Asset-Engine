"""
Unit test for NanoBananaImageGenerationAdapter (Phase 10.1 of the AI
Creative Engine vNext, see MIGRATION_PLAN.md's ADR §10) - same
real-SDK-shape discipline as test_openai_adapter.py: no real network
call, but the mocked response is shaped like a real
google.genai.types.GenerateContentResponse, confirmed via direct
introspection of the installed google-genai==2.14.0 SDK (see the
adapter's own module docstring for what that introspection covered).
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.ai_providers.base import GenerationRequest
from app.ai_providers.nano_banana_adapter import NanoBananaImageGenerationAdapter


def _make_reference_image_file(tmp_path, filename="ref.jpg") -> str:
    from PIL import Image

    path = tmp_path / filename
    Image.new("RGB", (200, 200), color=(210, 160, 120)).save(path)
    return str(path)


def _fake_generate_content_response(image_bytes: bytes):
    """
    Mimics the real response shape:
    response.candidates[0].content.parts[i].inline_data.data - see
    nano_banana_adapter.py's _extract_image_bytes for why this exact
    shape.
    """
    part = SimpleNamespace(inline_data=SimpleNamespace(data=image_bytes, mime_type="image/png"))
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(candidates=[candidate])


def test_generate_image_sends_prompt_and_reference_images(tmp_path):
    fake_bytes = b"fake-generated-png-bytes"
    canned_response = _fake_generate_content_response(fake_bytes)
    adapter = NanoBananaImageGenerationAdapter(model="gemini-3.1-flash-lite-image")

    with patch("app.ai_providers.nano_banana_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Composition: a bottle on a sunlit counter",
        reference_image_paths=[_make_reference_image_file(tmp_path)],
        things_to_avoid=["cluttered background"],
        # "3:4" (not "4:5") - a real, documented value from
        # google-genai's own ImageConfig.aspect_ratio docstring; "4:5"
        # (used by OpenAI's Images API) isn't in Gemini's supported set.
        aspect_ratio="3:4",
    )

    # Real-world-diagnosed fix (see MIGRATION_PLAN.md): `client` is now a
    # fresh-per-access property (no longer memoized, for thread-safety) -
    # pinning the class attribute to this one already-configured client
    # for the test's duration makes every `.client` access return the
    # same object, so patching its methods below still reaches the
    # adapter's own real call.
    with (
        patch.object(NanoBananaImageGenerationAdapter, "client", client),
        patch.object(client.models, "generate_content", return_value=canned_response) as mock_generate_content,
    ):
        result = adapter.generate_image(request)

    assert result.image_bytes == fake_bytes
    assert result.provider == "nano_banana"
    assert result.model == "gemini-3.1-flash-lite-image"
    assert result.seed is None
    assert "Composition: a bottle on a sunlit counter" in result.prompt_used
    assert "Preserve the exact product shown in the reference images" in result.prompt_used
    assert "Avoid: cluttered background" in result.prompt_used

    _, kwargs = mock_generate_content.call_args
    assert kwargs["model"] == "gemini-3.1-flash-lite-image"
    contents = kwargs["contents"]
    assert contents[0] == result.prompt_used
    assert len(contents) == 2  # prompt + one reference image
    assert kwargs["config"].response_modalities == ["IMAGE"]
    assert kwargs["config"].image_config.aspect_ratio == "3:4"


def test_aspect_ratio_matched_by_substring_against_supported_values(tmp_path):
    canned_response = _fake_generate_content_response(b"bytes")
    adapter = NanoBananaImageGenerationAdapter()

    with patch("app.ai_providers.nano_banana_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Composition: a bottle",
        reference_image_paths=[_make_reference_image_file(tmp_path)],
        things_to_avoid=[],
        aspect_ratio="9:16 vertical marketing ad",
    )

    with (
        patch.object(NanoBananaImageGenerationAdapter, "client", client),
        patch.object(client.models, "generate_content", return_value=canned_response) as mock_call,
    ):
        adapter.generate_image(request)

    _, kwargs = mock_call.call_args
    assert kwargs["config"].image_config.aspect_ratio == "9:16"


def test_unrecognized_aspect_ratio_falls_back_to_square(tmp_path):
    canned_response = _fake_generate_content_response(b"bytes")
    adapter = NanoBananaImageGenerationAdapter()

    with patch("app.ai_providers.nano_banana_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Composition: a bottle",
        reference_image_paths=[_make_reference_image_file(tmp_path)],
        things_to_avoid=[],
        aspect_ratio="unknown-ratio",
    )

    with (
        patch.object(NanoBananaImageGenerationAdapter, "client", client),
        patch.object(client.models, "generate_content", return_value=canned_response) as mock_call,
    ):
        adapter.generate_image(request)

    _, kwargs = mock_call.call_args
    assert kwargs["config"].image_config.aspect_ratio == "1:1"


def test_raises_a_clear_error_when_the_response_has_no_image_part(tmp_path):
    adapter = NanoBananaImageGenerationAdapter()
    text_only_response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[SimpleNamespace(inline_data=None, text="I can't generate that.")]
                )
            )
        ]
    )

    with patch("app.ai_providers.nano_banana_adapter.get_api_key", return_value="fake-key"):
        client = adapter.client

    request = GenerationRequest(
        creative_intent="Composition: a bottle",
        reference_image_paths=[_make_reference_image_file(tmp_path)],
        things_to_avoid=[],
        aspect_ratio="1:1",
    )

    with (
        patch.object(NanoBananaImageGenerationAdapter, "client", client),
        patch.object(client.models, "generate_content", return_value=text_only_response),
    ):
        try:
            adapter.generate_image(request)
            assert False, "expected a RuntimeError"
        except RuntimeError as exc:
            assert "no image data" in str(exc)


def test_capabilities():
    adapter = NanoBananaImageGenerationAdapter()

    capabilities = adapter.capabilities

    assert capabilities.supports_reference_images is True
    assert capabilities.max_reference_images > 0
    assert "1:1" in capabilities.supported_resolutions
