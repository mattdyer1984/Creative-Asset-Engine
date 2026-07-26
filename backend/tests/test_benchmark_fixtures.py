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
    "unknown",
    "split-comparison", "grid-collage", "side-by-side-comparison", "product-hero",
    "scene-with-caption", "shelf-snapshot", "diagram-with-callout", "screen-in-scene",
}
# Package B closed vocabulary (app/services/composition_schema.py). Kept in
# sync deliberately: the fixtures are the specification the schema must
# express, so a divergence here is a real disagreement, not a typo.
ZONE_ROLES = {
    "text", "caption", "subject", "product", "callout",
    "negative-space", "screen", "price", "graphic",
}
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

    zone_ids = set()
    for zone in contract["zones"]:
        assert zone["role"] in ZONE_ROLES
        assert zone["id"] not in zone_ids, f"duplicate zone id {zone['id']!r}"
        zone_ids.add(zone["id"])
        bounds = zone["bounds"]
        assert len(bounds) == 4
        assert all(0.0 <= value <= 1.0 for value in bounds), "zones are normalised"
        assert bounds[0] < bounds[2] and bounds[1] < bounds[3], "zones must be non-empty"

    # Endpoints must name declared zones. Free-text endpoints were the last
    # escape hatch in an otherwise closed vocabulary: they look like structure
    # and resolve to nothing, so no stage can act on them.
    for subject, relation, obj in contract["relations"]:
        assert relation in RELATIONS, f"{relation!r} is not in the relation vocabulary"
        assert subject in zone_ids, f"relation subject {subject!r} is not a declared zone"
        assert obj in zone_ids, f"relation object {obj!r} is not a declared zone"
        assert subject != obj, "a zone cannot be related to itself"
    for ranked in contract["emphasis"]:
        assert ranked in zone_ids, f"emphasis {ranked!r} is not a declared zone"


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


# --- suite governance (O5) ------------------------------------------------


def test_the_suite_declares_a_version():
    """
    A score without a suite version is not comparable to anything
    (docs/BENCHMARK_GOVERNANCE.md §5).
    """
    version = (BENCHMARKS / "VERSION").read_text().strip()
    assert version.isdigit(), "VERSION holds a single integer"
    assert int(version) >= 1


def test_the_changelog_covers_the_current_version():
    """A version bump without a changelog entry loses the evidence trail."""
    version = (BENCHMARKS / "VERSION").read_text().strip()
    changelog = (BENCHMARKS / "CHANGELOG.md").read_text()
    assert f"## v{version}" in changelog, (
        f"suite v{version} has no CHANGELOG entry - see docs/BENCHMARK_GOVERNANCE.md"
    )


# --- product annotation (suite v2) ----------------------------------------

PRODUCT_CASES = {"case02_books", "case03_mini_ac", "case06_meal_prep", "case08_fan_shelf"}
ANNOTATION_METHODS = {"candidate_selection", "reviewer_drawn"}


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_only_the_four_product_cases_declare_a_product(case):
    """
    The absence is an expectation. Product Isolation inventing a product in a
    weather-TV scene or a posture diagram is a real failure, and these four
    cases are the negative control that catches it.
    """
    has_product = "product" in _load(case)
    assert has_product == (case.name in PRODUCT_CASES), (
        f"{case.name}: product block presence does not match the approved set"
    )


@pytest.mark.parametrize("case", sorted(PRODUCT_CASES))
def test_the_product_block_is_fully_specified(case):
    product = _load(BENCHMARKS / case)["product"]
    assert product["name"].strip()

    bounds = product["appearance_bounds"]
    assert len(bounds) == 4
    assert all(0.0 <= v <= 1.0 for v in bounds), "bounds are normalised"
    assert bounds[0] < bounds[2] and bounds[1] < bounds[3]

    assert product["instance_count"] >= 1
    assert len(product["regions"]) == product["instance_count"], (
        "instance_count must be supported by a region per instance - the field "
        "exists to catch isolation finding one of five books and calling it "
        "the product"
    )


@pytest.mark.parametrize("case", sorted(PRODUCT_CASES))
def test_every_region_records_how_it_was_obtained(case):
    """
    Provenance is what makes the annotation governed. A mixed-provenance
    block must be visible rather than implied.
    """
    for region in _load(BENCHMARKS / case)["product"]["regions"]:
        assert region["method"] in ANNOTATION_METHODS, region
        rb = region["bounds"]
        assert rb[0] < rb[2] and rb[1] < rb[3]


@pytest.mark.parametrize("case", sorted(PRODUCT_CASES))
def test_appearance_bounds_enclose_every_region(case):
    product = _load(BENCHMARKS / case)["product"]
    x0, y0, x1, y1 = product["appearance_bounds"]
    for region in product["regions"]:
        rx0, ry0, rx1, ry1 = region["bounds"]
        assert x0 <= rx0 and y0 <= ry0 and x1 >= rx1 and y1 >= ry1, (
            f"{region['id']} falls outside appearance_bounds"
        )


@pytest.mark.parametrize("case", sorted(PRODUCT_CASES))
def test_generation_expectations_use_the_real_vocabularies(case):
    from app.services.text_ownership import ImageStrategy, Owner

    expectations = _load(BENCHMARKS / case)["product"]["generation_expectations"]
    assert expectations["product_native_text_owner"] in {str(o) for o in Owner}
    assert expectations["product_native_text_strategy"] in {str(s) for s in ImageStrategy}


@pytest.mark.parametrize("case", sorted(PRODUCT_CASES))
def test_scene_text_cross_checks_against_the_text_blocks(case):
    """
    A scene-text entry that no text block mentions would let the two
    annotations drift apart silently.
    """
    data = _load(BENCHMARKS / case)
    blocks = " ".join(b["text"].lower() for b in data["text_blocks"])
    for text in data["product"]["generation_expectations"]["scene_text_not_product_locked"]:
        # Substring match on the whole phrase: OCR splits and re-joins lines,
        # and a per-word test with a length filter silently passes short
        # entries like "vs" that it never actually checked.
        assert text.lower() in blocks, f"{case}: {text!r} appears in no text block"


@pytest.mark.parametrize("case", sorted(PRODUCT_CASES))
def test_expected_lock_fields_are_real_profile_fields(case):
    """
    Lock Profile fields live inside `structured_json`, not as columns, so
    they are checked against the schema the stage actually requests. A
    fixture naming a field the stage never produces would assert something
    unachievable.
    """
    from app.slideshow_stages.product_lock_profile_stage import (
        PRODUCT_LOCK_PROFILE_SCHEMA,
    )

    known = set(PRODUCT_LOCK_PROFILE_SCHEMA["properties"])
    for field in _load(BENCHMARKS / case)["product"]["expected_lock_fields"]:
        assert field in known, (
            f"{field!r} is not produced by the Product Lock Profile stage"
        )
