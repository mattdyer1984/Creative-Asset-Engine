"""
Prompt registry core (Phase 1 remediation, WP-3).

Prompts are the actual instructions this product ships - they decide
what every generated image looks like. Until now they were scattered
across ~10 modules as bare constants, with no identity, no version, and
no way to tell whether a change to one explains a change in output
quality. `AnalysisRun.prompt_template_version` existed but was a dead
column: NOT NULL, defaulted to "1.0", never written by anything.

**Three mechanisms, deliberately separate.** They answer different
questions, and collapsing them would lose one of the answers:

  * `content_hash` - AUTOMATIC. Changes on any edit, however small.
    Answers "is the prompt that produced this image byte-identical to
    the one in the tree today?"
  * `version` - SEMANTIC, and must be bumped by a human. Answers "was
    this change meant to alter behaviour?" A typo fix and a rewritten
    instruction both change the hash; only one deserves a new version.
  * snapshot tests - a committed rendering of each prompt against fixed
    inputs. Answers "did someone change this without noticing?"

The third exists because the first two cannot catch an accidental edit
on their own: an accidental change updates the hash just as readily as a
deliberate one, so a changed hash can never by itself legitimise the
change. The snapshot fails instead, and updating it is a deliberate act.

**The hash covers the TEMPLATE, not the rendered text.** Rendered text
embeds per-slide data, so its hash would change on every call and could
never indicate an edit. Hashing the template makes the figure mean
exactly one thing: this wording changed.

**Fragments are hashed even when unused.** A prompt assembled from
conditional pieces (story mode vs product mode, retry guidance appended
on a second attempt) has ONE identity covering every fragment it can
emit. Otherwise editing a rarely-taken branch would leave the hash
untouched and the change invisible - which is precisely the branch where
an unnoticed edit does the most damage.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field

# 16 hex chars = 64 bits. Long enough that an accidental collision across
# a few dozen prompts is not a real concern, short enough to read in a
# log line or a DB column without wrapping.
_HASH_LENGTH = 16


def content_hash_of(*parts: str) -> str:
    """
    Stable hash over one or more template fragments.

    Order matters and is part of the identity: reordering the fragments
    of an assembled prompt changes what the model reads, so it should
    change the hash.
    """
    digest = hashlib.sha256()
    for part in parts:
        # Length-prefixed so ("ab", "c") and ("a", "bc") cannot collide.
        digest.update(str(len(part)).encode())
        digest.update(b":")
        digest.update(part.encode())
    return digest.hexdigest()[:_HASH_LENGTH]


@dataclass(frozen=True)
class Prompt:
    """
    One registered prompt: identity, wording, and how to render it.

    `template` is the base text. `fragments` are optional named pieces
    that callers may append conditionally; they belong to this prompt's
    identity whether or not a given call uses them (see module docstring).
    """

    id: str
    version: str
    template: str
    description: str = ""
    fragments: Mapping[str, str] = field(default_factory=dict)
    # Declared explicitly rather than discovered by scanning for braces.
    # Several prompts contain literal JSON examples, so a brace is NOT
    # reliable evidence of a placeholder - running `.format()` over one
    # would raise on `{"role": ...}` or, worse, silently mangle it. An
    # empty tuple means "this text is final", and render() then returns
    # it verbatim without formatting at all.
    variables: tuple[str, ...] = ()

    @property
    def content_hash(self) -> str:
        """Covers the base template and every fragment, in name order."""
        ordered = [self.template]
        for name in sorted(self.fragments):
            ordered.append(name)
            ordered.append(self.fragments[name])
        return content_hash_of(*ordered)

    def render(self, **values) -> str:
        """
        Fills `{placeholders}` in the base template.

        A prompt that declares no `variables` is returned byte-for-byte
        - no formatting pass, so literal JSON braces in the text survive
        untouched. Otherwise `str.format_map` runs against a strict
        mapping, so a missing value raises loudly instead of leaving a
        stray `{brace}` in text the model will read as instructions.
        """
        if not self.variables:
            if values:
                raise TypeError(
                    f"prompt {self.id!r} takes no variables, but got: "
                    f"{', '.join(sorted(values))}"
                )
            return self.template
        missing = [name for name in self.variables if name not in values]
        if missing:
            raise KeyError(
                f"prompt {self.id!r} needs {', '.join(missing)} and none was given"
            )
        return self.template.format_map(_Strict(values, self.id))

    def with_fragments(self, *names: str, **values) -> str:
        """
        Renders the base template, then appends the named fragments in
        the order given - the assembly path for prompts that vary by
        run state (story vs product mode, retry guidance, and so on).
        """
        base_values = {k: v for k, v in values.items() if k in self.variables}
        parts = [self.render(**base_values)]
        for name in names:
            if name not in self.fragments:
                raise KeyError(f"prompt {self.id!r} has no fragment {name!r}")
            fragment = self.fragments[name]
            # Same rule as render(): only format when there is something
            # to substitute, so a fragment containing literal braces is
            # not mangled on its way into the prompt.
            parts.append(fragment.format_map(_Strict(values, self.id)) if values else fragment)
        return "\n\n".join(part for part in parts if part.strip())

    def identity(self) -> dict:
        """The three fields ProviderCall records for every paid call."""
        return {
            "prompt_id": self.id,
            "prompt_version": self.version,
            "prompt_content_hash": self.content_hash,
        }


class _Strict(dict):
    """Turns a missing placeholder into a clear error, not a silent gap."""

    def __init__(self, values: Mapping, prompt_id: str):
        super().__init__(values)
        self._prompt_id = prompt_id

    def __missing__(self, key):
        raise KeyError(
            f"prompt {self._prompt_id!r} needs a value for {{{key}}} and none was given"
        )


class PromptRegistry:
    """
    The set of registered prompts.

    Registration is by import: each stage module defines its prompts and
    calls `register`. `app.prompts` imports them all so the registry is
    complete for the lock-file and snapshot tests, which must fail when
    a prompt is added without being covered.
    """

    def __init__(self) -> None:
        self._prompts: dict[str, Prompt] = {}

    def register(self, prompt: Prompt) -> Prompt:
        existing = self._prompts.get(prompt.id)
        if existing is not None and existing != prompt:
            raise ValueError(
                f"two different prompts are both registered as {prompt.id!r} - "
                "ids must be unique, or cost and provenance data will be attributed "
                "to the wrong wording"
            )
        self._prompts[prompt.id] = prompt
        return prompt

    def get(self, prompt_id: str) -> Prompt:
        try:
            return self._prompts[prompt_id]
        except KeyError:
            raise KeyError(f"no prompt registered as {prompt_id!r}") from None

    def all(self) -> list[Prompt]:
        return [self._prompts[key] for key in sorted(self._prompts)]

    def manifest(self) -> dict[str, dict[str, str]]:
        """
        `{id: {version, content_hash}}` - what the committed lock file
        holds, and what the lock test compares against.
        """
        return {
            prompt.id: {"version": prompt.version, "content_hash": prompt.content_hash}
            for prompt in self.all()
        }


REGISTRY = PromptRegistry()


def register(
    *,
    id: str,
    version: str,
    template: str,
    description: str = "",
    variables: tuple[str, ...] = (),
    fragments: Mapping[str, str] | None = None,
) -> Prompt:
    """Defines a prompt and adds it to the registry. Returns it."""
    return REGISTRY.register(
        Prompt(
            id=id,
            version=version,
            template=template,
            description=description,
            variables=tuple(variables),
            fragments=dict(fragments or {}),
        )
    )


def get(prompt_id: str) -> Prompt:
    return REGISTRY.get(prompt_id)
