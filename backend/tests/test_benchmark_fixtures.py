"""
Benchmark fixture integrity (ADR 0001 WP-0.1).

The benchmarks are the specification, so the schema has to be tight enough
that two people annotating the same case independently produce the same
structure. These tests enforce the closed vocabularies and the structural
rules that make that possible - they do not judge the annotations themselves,
which is a human review task.

They also assert the set-level findings in ADR §3, so that adding a case which
contradicts them is a deliberate act rather than an accident.
"""

import pathlib

import pytest
import yaml

BENCHMARKS = pathlib.Path(__file__).parent / "benchmarks"
CASES = sorted(p for p in BENCHMARKS.iterdir() if p.is_dir())

SOURCE_PROJECT_TYPES = {"designed_editorial", "ugc_photographic", "hybrid"}
TEXT_MODES = {"designed_typography", "platform_caption"}
TEXT_CLASSES = {"product_native", "designed_typography", "platform_caption", "environmental"}
HANDLING = {"product_lock", "deterministic_typography", "deterministic_overlay", "model_generated"}
OVERLAY_POLICIES = {"keep", "remove", "replace", "review_individually"}
COPY_POLICIES = {"preserve_verbatim", "preserve_meaning", "user_replacement"}
INTENTS = {
    "discovery", "comparison", "education", "warning", "aspiration",
    "transformation", "humour", "social_proof", "demonstration", "product_reveal",
}
DEVICES = {
    "split-comparison", "grid-collage", "side-by-side-comparison", "product-hero",
    "scene-with-caption", "shelf-snapshot", "diagram-with-callout", "screen-in-scene",
}
ZONE_ROLES = {"text-zone", "subject-zone", "product-zone", "negative-space", "callout-zone"}
RELATIONS = {
    "above", "below", "left-of", "right-of", "attached-to", "points-to",
    "splits", "flanks", "contains",
}
FAMILIES = {"serif", "grotesque", "geometric-sans", "condensed-sans", "slab", "script", "display"}
PRODUCTION_VALUES = {"match", "refine", "elevate"}
CAPABILITY_LEVELS = {"L1", "L2", "L3"}


def _load(case: pathlib.Path) -> dict:
    return yaml.safe_load((case / "ground_truth.yaml").read_text())


def test_eight_cases_are_present():
    assert len(CASES) == 8, "the v0 benchmark set is the eight gold-standard pairs"


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_case_has_both_images_and_an_annotation(case):
    for required in ("original.jpg", "recreation.jpg", "ground_truth.yaml"):
        assert (case / required).exists(), f"{case.name} is missing {required}"


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_case_id_matches_its_directory(case):
    assert _load(case)["case_id"] == case.name


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_closed_vocabularies_are_respected(case):
    """
    Every enumerated field must use a term from the schema. A new term is
    added to schema.yaml WITH THE CASE AS EVIDENCE, never invented inline -
    free text is where annotator disagreement hides.
    """
    data = _load(case)
    assert data["source_project_type"] in SOURCE_PROJECT_TYPES
    assert data["primary_text_mode"] in TEXT_MODES
    assert data["overlay_policy"] in OVERLAY_POLICIES
    assert data["copy_policy"] in COPY_POLICIES
    assert data["creative_intent"] in INTENTS
    assert data["production_value_strategy"] in PRODUCTION_VALUES

    contract = data["composition_contract"]
    assert contract["device"] in DEVICES
    for zone in contract["zones"]:
        assert zone["role"] in ZONE_ROLES
        bounds = zone["bounds"]
        assert len(bounds) == 4
        assert all(0.0 <= value <= 1.0 for value in bounds), "zones are normalised"
        assert bounds[0] < bounds[2] and bounds[1] < bounds[3], "zones must be non-empty"
    for subject, relation, obj in contract["relations"]:
        assert relation in RELATIONS, f"{relation!r} is not in the relation vocabulary"
        assert subject and obj


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_text_blocks_are_fully_specified(case):
    data = _load(case)
    assert data["text_blocks"], "every benchmark has text"
    for block in data["text_blocks"]:
        assert block["text"].strip()
        assert block["class"] in TEXT_CLASSES
        assert block["expected_handling_mechanism"] in HANDLING
        assert isinstance(block["optional"], bool)


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_only_platform_captions_are_optional(case):
    """
    ADR §4 acceptance criterion 1: baked-in text is never removed by default.
    An annotation marking product packaging or designed typography as optional
    would licence exactly the regression this programme exists to fix.
    """
    for block in _load(case)["text_blocks"]:
        if block["optional"]:
            assert block["class"] == "platform_caption", (
                f"{case.name}: only a platform caption may be optional, "
                f"got {block['class']!r}"
            )


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_handling_mechanism_matches_the_class(case):
    """Product-native text is owned by Product Lock, never re-typeset (§6)."""
    allowed = {
        "product_native": {"product_lock"},
        "designed_typography": {"deterministic_typography", "model_generated"},
        "platform_caption": {"deterministic_overlay"},
        "environmental": {"model_generated", "product_lock"},
    }
    for block in _load(case)["text_blocks"]:
        assert block["expected_handling_mechanism"] in allowed[block["class"]], (
            f"{case.name}: {block['class']} cannot be handled by "
            f"{block['expected_handling_mechanism']}"
        )


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_designed_projects_declare_a_typography_system(case):
    """A designed creative without a typography system cannot be rebuilt."""
    data = _load(case)
    system = data["typography_system"]
    if data["source_project_type"] == "designed_editorial":
        assert system is not None
        assert system["primary_family"] in FAMILIES
        assert system["secondary_family"] in FAMILIES | {None}
        assert system["capability_level"] in CAPABILITY_LEVELS
        assert system["colour_roles"]
    else:
        assert system is None, "a UGC caption project has no design typography"


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_invariants_and_transformations_are_disjoint(case):
    """The same thing cannot be both required and free to change."""
    data = _load(case)
    required = {s.lower() for s in data["required_invariants"]}
    allowed = {s.lower() for s in data["allowed_transformations"]}
    assert not (required & allowed), f"{case.name}: contradictory annotation"
    assert data["required_invariants"]
    assert data["allowed_transformations"]
    assert data["forbidden_transformations"]
    assert data["human_rationale"].strip()


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_every_case_preserves_wording_verbatim(case):
    """ADR §3 finding: 8/8 pairs preserve wording. A case that does not is a
    genuine discovery and should fail here until the ADR is revised."""
    assert _load(case)["copy_policy"] == "preserve_verbatim"


def test_the_set_splits_cleanly_into_two_text_modes():
    """
    ADR §3: four designed-editorial, four UGC-caption, and no pair mixes
    designed typography with a platform caption. This is the evidence behind
    text mode being a project-level property (§12.1).
    """
    modes = [_load(case)["primary_text_mode"] for case in CASES]
    assert modes.count("designed_typography") == 4
    assert modes.count("platform_caption") == 4

    for case in CASES:
        data = _load(case)
        classes = {block["class"] for block in data["text_blocks"]}
        assert not ({"designed_typography"} <= classes and {"platform_caption"} <= classes), (
            f"{case.name} mixes designed typography with a platform caption - "
            "if real, ADR §3 needs revising"
        )


def test_production_value_matches_the_recorded_finding():
    """ADR §3: deliberately raised in 2 of 8."""
    strategies = [_load(case)["production_value_strategy"] for case in CASES]
    assert strategies.count("elevate") == 2
    assert strategies.count("refine") == 6
