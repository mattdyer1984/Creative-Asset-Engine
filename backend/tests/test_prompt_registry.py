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
    "generation.text_rewrite": {
        "block_list": '1. [headline] "Try it today"\n2. [cta] "Buy now"'
    },
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


def _creative_specification_shapes() -> dict[str, str]:
    """Both variants: with a Product Lock Profile, and story mode without."""
    import json

    from app.prompts.generation import compile_creative_specification_prompt

    fingerprint = json.dumps({"style": "clean studio"})
    return {
        "generation.creative_specification.product": compile_creative_specification_prompt(
            lock_profile_json=json.dumps({"brand": "Acme"}), fingerprint_json=fingerprint
        ),
        "generation.creative_specification.story": compile_creative_specification_prompt(
            lock_profile_json=None, fingerprint_json=fingerprint
        ),
    }


_COMPILER_SPEC = {
    "composition": "centered hero shot",
    "style_direction": "clean editorial",
    "lighting": "soft daylight",
    "camera_and_perspective": "eye level, 50mm",
    "background_environment": "marble countertop",
    "mood": "fresh and calm",
    "color_palette": ["warm white", "sage"],
    "text_overlays": [{"role": "headline", "content": "Try it today"}],
    "things_to_avoid": ["blurry", "clutter"],
}


def _generation_compiler_shapes() -> dict[str, str]:
    """
    The most consequential prompt in the application, snapshotted across
    every fragment that can fire. Twelve conditional fragments means a
    single-shape snapshot would leave most of the text unguarded - and
    the fragments that fire rarely (bundle composition, the absolute
    text-suppression override) are precisely the ones where an
    unnoticed edit would be hardest to trace back from a bad image.
    """
    from app.prompts.generation import GENERATION_COMPILER

    bundle = [
        {"role_in_scene": "hero", "image_count": 2, "branding_text": ["ACME", "500ml"]},
        {"role_in_scene": "companion", "image_count": 1},
    ]
    shapes = {
        "minimal": dict(),
        "full_spec": dict(),
        "bundle": dict(bundle_members=bundle),
        "suppressed_text": dict(suppress_overlay_text=True),
        "branding": dict(branding_text=["ACME", "ORIGINAL"]),
        "feedback_and_retry": dict(
            user_feedback="the can looked squashed",
            retry_reason="Product identity wasn't preserved: cap shape looked rounded",
        ),
    }
    out = {}
    for name, kwargs in shapes.items():
        spec = {"composition": "close up"} if name == "minimal" else _COMPILER_SPEC
        out[f"generation.compiler.{name}"] = GENERATION_COMPILER.assemble(spec, **kwargs)
    return out


# Prompts assembled by a helper rather than rendered straight from a
# template: snapshot every shape the helper can emit.
ASSEMBLED = {
    "generation.image_compilation": _image_compilation_shapes,
    "generation.creative_specification": _creative_specification_shapes,
    "generation.compiler": _generation_compiler_shapes,
}


# Prompts that are purely a set of alternative fragments, exactly one of
# which is selected per call - no surrounding template to render. Each
# fragment gets its own snapshot so editing the rarely-selected branch
# still fails a test.
FRAGMENT_ONLY = {"generation.retry_reason"}


def _snapshot_names(prompt) -> list[tuple[str, str]]:
    """(snapshot name, rendered text) pairs for one prompt."""
    if prompt.id in ASSEMBLED:
        return sorted(ASSEMBLED[prompt.id]().items())
    if prompt.id in FRAGMENT_ONLY:
        return sorted(
            (f"{prompt.id}.{name}", text) for name, text in prompt.fragments.items()
        )
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


def test_every_recording_call_site_supplies_prompt_identity():
    """
    Guards WP-3's actual deliverable. It is easy to add a new paid call
    and forget the prompt, leaving a row that records what it cost but
    not what produced it - and nothing else would fail.

    Sites that emit no ProviderCall at all are exempt, and must say so
    explicitly: either they pass no usage (nothing billable to record)
    or emit_provider_call=False (they record their own finer-grained
    rows). Anything else must name its prompt.
    """
    import ast
    import pathlib

    app_dir = pathlib.Path(__file__).parent.parent / "app"
    offenders = []

    for path in sorted(app_dir.rglob("*.py")):
        if path.name == "execution.py" and path.parent.name == "stages":
            continue  # the choke point itself - it forwards the argument
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in {"record_provider_call", "mark_succeeded"}:
                continue
            keywords = {k.arg: k for k in node.keywords}
            if "prompt" in keywords:
                continue
            # Exempt: emits nothing.
            if name == "mark_succeeded":
                emits = keywords.get("emit_provider_call")
                if "usage" not in keywords or (
                    emits is not None
                    and isinstance(emits.value, ast.Constant)
                    and emits.value.value is False
                ):
                    continue
            offenders.append(f"{path.relative_to(app_dir.parent)}:{node.lineno} {name}()")

    assert not offenders, (
        "these paid-call sites record cost but not which prompt produced it:\n  "
        + "\n  ".join(offenders)
        + "\nPass prompt=<registered Prompt>, or make it explicit that the site "
        "emits no ProviderCall."
    )


def test_generated_images_record_identity_for_every_contributing_prompt():
    """
    A generated image's text comes from two definitions - the compiler
    builds the creative intent, the adapter wraps it. Recording only one
    would let the other change without the recorded identity moving, so
    "which prompt made this image?" would answer confidently and wrongly.
    """
    from app.prompts.generation import (
        GENERATION_COMPILER,
        IMAGE_COMPILATION,
        generated_image_identity,
    )

    identity = generated_image_identity()
    assert identity["prompt_id"] == "generation.compiler+generation.image_compilation"
    assert identity["prompt_version"] == f"{GENERATION_COMPILER.version}+{IMAGE_COMPILATION.version}"
    # Neither contributor's own hash may masquerade as the composite.
    assert identity["prompt_content_hash"] not in (
        GENERATION_COMPILER.content_hash,
        IMAGE_COMPILATION.content_hash,
    )


def test_editing_either_contributing_prompt_moves_the_recorded_hash():
    """The composite is only useful if it is sensitive to both halves."""
    from app.prompts.core import Prompt, composite_identity

    compiler = Prompt(id="c", version="1.0", template="Compile.")
    wrapper = Prompt(id="w", version="1.0", template="Wrap.")
    baseline = composite_identity(compiler, wrapper)["prompt_content_hash"]

    edited_compiler = composite_identity(
        Prompt(id="c", version="1.0", template="Compile!"), wrapper
    )["prompt_content_hash"]
    edited_wrapper = composite_identity(
        compiler, Prompt(id="w", version="1.0", template="Wrap!")
    )["prompt_content_hash"]

    assert baseline != edited_compiler, "an edit to the compiler must be visible"
    assert baseline != edited_wrapper, "an edit to the wrapper must be visible"
    assert edited_compiler != edited_wrapper


def test_the_generation_compiler_is_registered():
    """
    The single most consequential prompt in the application. It had no
    identity because it is assembled from twelve conditional fragments -
    which is the reason it needs one, not a reason it cannot have one.
    """
    from app.prompts import REGISTRY

    compiler = REGISTRY.get("generation.compiler")
    assert compiler.renderer is not None, "its assembly must live with its definition"
    # Fragments that a given call never reaches are still hashed.
    for fragment in ("bundle_header", "suppress_overlay_text", "retry_reason"):
        assert fragment in compiler.fragments


def test_a_generated_image_can_be_traced_back_to_its_prompt_definition():
    """
    The point of the whole exercise: given a stored image, can you get
    back to the exact prompt definition that produced it, and confirm
    whether that definition has changed since?
    """
    from app.models.generated_image import GeneratedImage
    from app.prompts.generation import GENERATION_COMPILER, generated_image_identity

    image = GeneratedImage(
        slideshow_id="s", slide_id="sl", provider="nano_banana",
        model_name="gemini-3.1-flash-image-preview",
        prompt_used="Composition: centered hero shot\n...",
        generation_time_seconds=12.0, file_path="/tmp/x.png",
        **generated_image_identity(),
    )

    # The rendered text is still there - it is what you read when one
    # specific image looks wrong.
    assert image.prompt_used.startswith("Composition:")
    # And the identity says which definition produced it.
    assert "generation.compiler" in image.prompt_id
    assert image.prompt_version == generated_image_identity()["prompt_version"]
    assert image.prompt_content_hash == generated_image_identity()["prompt_content_hash"]

    # "Has the prompt changed since this image was made?" is now answerable.
    assert image.prompt_content_hash == generated_image_identity()["prompt_content_hash"]
    assert GENERATION_COMPILER.content_hash  # contributor still resolvable by id
