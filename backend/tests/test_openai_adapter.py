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

import json
from types import SimpleNamespace
from unittest.mock import patch

from app.ai_providers.openai_adapter import OpenAIOCRAdapter


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
