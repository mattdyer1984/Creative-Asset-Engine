"""
Prompt registry guarantees (Phase 1 remediation, WP-3).

Three mechanisms, tested here because each catches what the others
cannot:

  * the LOCK test catches a prompt edited without a deliberate version
    decision - the hash moves, the lock file does not, the test fails;
  * the SNAPSHOT test catches an accidental edit, which would otherwise
    sail through: an accidental change updates the content hash exactly
    as readily as a deliberate one, so a changed hash can never by
    itself legitimise the change;
  * the COVERAGE test catches a new prompt that neither of the above is
    watching, which would make both of them quietly incomplete.

Updating a prompt is therefore a three-step, deliberate act: change the
text, bump the version, refresh the lock and the snapshot.
"""

import json
import pathlib

import pytest

from app.prompts import REGISTRY

SNAPSHOT_DIR = pathlib.Path(__file__).parent / "snapshots" / "prompts"
LOCK_PATH = pathlib.Path(__file__).parent.parent / "app" / "prompts" / "prompts.lock"

# Fixed inputs per prompt. Deliberately boring and stable - a snapshot
# whose inputs drift proves nothing about the prompt.
_FIELD_LINES = "\n".join(
    f'- field_name "{name}": expected value = {value}'
    for name, value in [("brand", "Acme"), ("silhouette", "tall slim can")]
)
RENDER_INPUTS: dict[str, dict] = {
    "analysis.marketing_analysis": {"fingerprint_json": '{"style": "clean studio"}'},
    "analysis.narrative_structure": {
        "slides_json": '[{"slide_index": 0, "text": "hook"}]'
    },
    "validation.creative_fidelity": {"field_lines": _FIELD_LINES},
    "generation.creative_intelligence": {
        "preserved_text": "- keep the logo",
        "transformable_text": "- swap the background",
        "visual_style": "clean studio",
        "marketing_narrative": "everyday indulgence",
        "product_category": "beverage",
        "guidance": "PLACEHOLDER",  # overridden per fragment below
    },
}

# Prompts whose snapshot is taken once per fragment, because the
# fragment is the part that varies.
PER_FRAGMENT = {"generation.creative_intelligence": "guidance"}


def _image_compilation_shapes() -> dict[str, str]:
    """
    All four shapes of the assembled image prompt. Snapshotting only one
    branch would leave the other free to drift unnoticed - and the
    story-mode branch is exactly the rarely-exercised one where that
    would hurt most.
    """
    from app.prompts.generation import compile_image_prompt

    shapes = {}
    for story in (False, True):
        for avoid in ([], ["blurry", "extra limbs"]):
            name = (
                f"generation.image_compilation."
                f"{'story' if story else 'product'}{'_avoid' if avoid else ''}"
            )
            shapes[name] = compile_image_prompt(
                "A clean studio shot.", story_mode=story, things_to_avoid=avoid
            )
    return shapes


# Prompts assembled by a helper rather than rendered straight from a
# template: snapshot every shape the helper can emit.
ASSEMBLED = {"generation.image_compilation": _image_compilation_shapes}


def _snapshot_names(prompt) -> list[tuple[str, str]]:
    """(snapshot name, rendered text) pairs for one prompt."""
    if prompt.id in ASSEMBLED:
        return sorted(ASSEMBLED[prompt.id]().items())
    inputs = dict(RENDER_INPUTS.get(prompt.id, {}))
    fragment_var = PER_FRAGMENT.get(prompt.id)
    if fragment_var is None:
        return [(prompt.id, prompt.render(**inputs))]
    return [
        (f"{prompt.id}.{name}", prompt.render(**{**inputs, fragment_var: text}))
        for name, text in sorted(prompt.fragments.items())
    ]


def test_both_image_providers_compile_the_same_prompt():
    """
    This text used to exist twice, byte-for-byte identical, in the
    OpenAI and Nano Banana adapters. Editing one and not the other would
    have made the two providers quietly disagree about what to generate,
    surfacing only as "the fallback produces worse images". They share
    one definition now; this asserts they cannot drift apart again.
    """
    from app.ai_providers.nano_banana_adapter import NanoBananaImageGenerationAdapter
    from app.ai_providers.openai_adapter import OpenAIImageGenerationAdapter

    class _Request:
        def __init__(self, story_mode, things_to_avoid):
            self.creative_intent = "A clean studio shot."
            self.story_mode = story_mode
            self.things_to_avoid = things_to_avoid

    openai = OpenAIImageGenerationAdapter.__new__(OpenAIImageGenerationAdapter)
    nano = NanoBananaImageGenerationAdapter.__new__(NanoBananaImageGenerationAdapter)

    for story_mode in (False, True):
        for things_to_avoid in ([], ["blurry", "extra limbs"]):
            request = _Request(story_mode, things_to_avoid)
            assert openai._compile_openai_prompt(request) == nano._compile_prompt(request), (
                f"the two image providers disagree (story_mode={story_mode}, "
                f"things_to_avoid={bool(things_to_avoid)})"
            )


@pytest.mark.parametrize("prompt", REGISTRY.all(), ids=lambda p: p.id)
def test_prompt_matches_its_committed_snapshot(prompt):
    """
    The accidental-edit guard. If this fails and you MEANT to change the
    prompt: bump its version, refresh prompts.lock, and re-record the
    snapshot. If you did not mean to change it, you just caught a bug.
    """
    for name, rendered in _snapshot_names(prompt):
        path = SNAPSHOT_DIR / f"{name}.txt"
        assert path.exists(), (
            f"{prompt.id} has no committed snapshot at {path.name}. "
            "Every registered prompt needs one, or an edit to it goes unnoticed."
        )
        assert rendered == path.read_text(), (
            f"{prompt.id} no longer renders as its committed snapshot.\n"
            "If this change was deliberate: bump the prompt's version, update "
            "prompts.lock, and re-record the snapshot.\n"
            "If it was not: this is the accidental edit the snapshot exists to catch."
        )


def test_lock_file_matches_the_registry():
    """
    The deliberate-bump guard. The lock records each prompt's version
    and content hash; editing text without touching the lock fails here.
    """
    locked = json.loads(LOCK_PATH.read_text())
    current = REGISTRY.manifest()

    assert current == locked, (
        "prompts.lock is out of date with the registry.\n"
        "A changed content_hash means the wording changed - decide whether it "
        "deserves a version bump, then update prompts.lock deliberately.\n"
        f"registry: {json.dumps(current, indent=2, sort_keys=True)}\n"
        f"locked:   {json.dumps(locked, indent=2, sort_keys=True)}"
    )


def test_every_registered_prompt_is_covered():
    """
    Guards the guards. A prompt registered but absent from the lock or
    the snapshot directory would make both tests above vacuously pass
    for it.
    """
    locked = json.loads(LOCK_PATH.read_text())
    for prompt in REGISTRY.all():
        assert prompt.id in locked, f"{prompt.id} is registered but not in prompts.lock"
        for name, _ in _snapshot_names(prompt):
            assert (SNAPSHOT_DIR / f"{name}.txt").exists(), (
                f"{prompt.id} is registered but has no snapshot {name}.txt"
            )


def test_content_hash_changes_when_wording_changes():
    """The hash must actually be sensitive to an edit - otherwise it is decoration."""
    from app.prompts.core import Prompt

    base = Prompt(id="t", version="1.0", template="Describe the product.")
    edited = Prompt(id="t", version="1.0", template="Describe the product!")
    assert base.content_hash != edited.content_hash


def test_content_hash_covers_unused_fragments():
    """
    An edit to a branch that did not fire on this call must still move
    the hash - that branch is the one where an unnoticed change does the
    most damage, precisely because it is rarely exercised.
    """
    from app.prompts.core import Prompt

    base = Prompt(id="t", version="1.0", template="Base.", fragments={"story": "A."})
    edited = Prompt(id="t", version="1.0", template="Base.", fragments={"story": "B."})
    assert base.content_hash != edited.content_hash


def test_a_prompt_with_no_variables_is_returned_verbatim():
    """
    Several prompts contain literal JSON braces. Running str.format over
    them would raise, or worse, mangle the example the model is meant to
    copy - so a prompt declaring no variables must skip formatting.
    """
    from app.prompts.core import Prompt

    text = 'Return {"surface": "physical"} exactly.'
    assert Prompt(id="t", version="1.0", template=text).render() == text


def test_a_missing_variable_fails_loudly():
    """Better a clear error than a stray {brace} the model reads as instructions."""
    from app.prompts.core import Prompt

    prompt = Prompt(
        id="t", version="1.0", template="Check {field}.", variables=("field",)
    )
    with pytest.raises(KeyError, match="field"):
        prompt.render()


def test_duplicate_ids_are_rejected():
    """Two prompts under one id would misattribute cost and provenance."""
    from app.prompts.core import Prompt, PromptRegistry

    registry = PromptRegistry()
    registry.register(Prompt(id="dupe", version="1.0", template="A"))
    with pytest.raises(ValueError, match="unique"):
        registry.register(Prompt(id="dupe", version="1.0", template="B"))
