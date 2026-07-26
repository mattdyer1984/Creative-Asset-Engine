"""
Every response schema we send must be one the provider will accept.

Phase F found this the only way it can be found. `TYPOGRAPHY_SYSTEM_SCHEMA`
listed four of its nine properties in `required`; OpenAI structured outputs
reject that outright with a 400, and four of eight benchmark cases failed
100% against the real provider while every unit test passed - because a fake
provider does not validate the schema it is handed.

So the schemas are validated here instead, structurally, without a provider.
A test that only exercises fakes cannot see this class of defect at all.
"""

import pytest

from app.slideshow_stages.composition_contract_stage import COMPOSITION_CONTRACT_SCHEMA
from app.slideshow_stages.creative_profile_stage import TYPOGRAPHY_SYSTEM_SCHEMA
from app.slideshow_stages.scene_intelligence_stage import SCENE_REGION_SCHEMA

#: Every schema this codebase sends as a `response_format`. A new one added
#: without being listed here is uncovered, which is how the typography schema
#: reached production unvalidated.
RESPONSE_SCHEMAS = {
    "composition_contract": COMPOSITION_CONTRACT_SCHEMA,
    "typography_system": TYPOGRAPHY_SYSTEM_SCHEMA,
    "scene_intelligence": SCENE_REGION_SCHEMA,
}


def _object_nodes(node, path="$"):
    """Every object-with-properties node in a schema, depth first."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            yield path, node
        for key, value in node.items():
            yield from _object_nodes(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _object_nodes(value, f"{path}[{index}]")


@pytest.mark.parametrize("name", sorted(RESPONSE_SCHEMAS))
def test_every_property_is_required(name):
    """
    OpenAI structured outputs forbid optional properties: `required` must
    list every key in `properties`, at every level including
    `additionalProperties` sub-schemas. A missing one is a 400, not a
    degraded response.
    """
    for path, node in _object_nodes(RESPONSE_SCHEMAS[name]):
        properties = set(node["properties"])
        required = set(node.get("required") or [])
        assert properties == required, (
            f"{name} at {path}: `required` must list every property. "
            f"Missing {sorted(properties - required)}; "
            f"unexpected {sorted(required - properties)}"
        )


@pytest.mark.parametrize("name", sorted(RESPONSE_SCHEMAS))
def test_additional_properties_is_closed(name):
    """An open object lets the model return anything and calls it valid."""
    for path, node in _object_nodes(RESPONSE_SCHEMAS[name]):
        assert node.get("additionalProperties") is False, (
            f"{name} at {path}: additionalProperties must be False"
        )


@pytest.mark.parametrize("name", sorted(RESPONSE_SCHEMAS))
def test_the_schema_is_json_serialisable(name):
    """It is sent over the wire; a non-serialisable member fails at call time."""
    import json

    json.dumps(RESPONSE_SCHEMAS[name])


@pytest.mark.parametrize("name", sorted(RESPONSE_SCHEMAS))
def test_no_open_ended_maps(name):
    """
    Strict structured outputs cannot express `additionalProperties: {schema}`
    - an open map. The typography schema used three of them and was rejected
    outright; the domain model keeps its open role maps, but they travel as
    arrays of {role, ...} and are rebuilt on receipt.
    """
    def walk(node, path="$"):
        if isinstance(node, dict):
            extra = node.get("additionalProperties")
            assert extra is None or extra is False, (
                f"{name} at {path}: open-ended map - strict mode rejects it. "
                "Send an array of named objects instead."
            )
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(RESPONSE_SCHEMAS[name])
