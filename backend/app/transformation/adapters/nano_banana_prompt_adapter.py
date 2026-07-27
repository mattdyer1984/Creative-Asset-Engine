"""
Nano Banana prompt adapter — the ONE provider-specific module.

Consumes a single immutable GenerationSpecification slide. For every enumerated
requirement (identity + immutable payload) it emits exactly one ManifestEntry
(encoded | unsupported), so the manifest is bijective with the slide's
requirements by construction. It reads each requirement's payload via
`req.get(...)` and translates it into actual provider-request content:

  * the full scene body (concept, environment, lighting, dynamics, subject
    action/emotion) survives into the request text — not just an ID;
  * exact-text is not silently downgraded: this model cannot guarantee legible
    exact text, so such a requirement is marked `unsupported` with a reason;
  * reference-fidelity text is bound to ITS OWNING product's attached reference
    (payload `owner`), never to "any attached reference";
  * reference truncation past `max_references` is explicit (`unsupported`).

It never mutates the spec, never asks upstream to change, and makes no provider
call.
"""
from __future__ import annotations

from dataclasses import dataclass
from ..generation_spec import SlideGenerationSpec
from ..generation_request import (
    AdapterOutput, RequestManifest, ManifestEntry, slide_requirements,
)


@dataclass(frozen=True)
class NanoBananaCapabilities:
    supports_references: bool = True
    max_references: int = 4
    can_reserve_open_zone: bool = True
    can_render_exact_text: bool = False        # generative model — cannot guarantee legible exact text
    can_render_illustration: bool = True
    variable_axes: tuple = ("setting", "lighting", "person_identity", "palette",
                            "props", "framing", "viewpoint", "styling")


class NanoBananaPromptAdapter:
    name = "nano_banana"

    def __init__(self, capabilities: NanoBananaCapabilities | None = None):
        self.capabilities = capabilities or NanoBananaCapabilities()

    def write(self, spec: SlideGenerationSpec) -> AdapterOutput:
        caps = self.capabilities

        # Which references can actually be attached (explicit, deterministic truncation).
        attached: set[str] = set()
        for p in spec.products:
            room = caps.max_references - len(attached)
            if caps.supports_references and room > 0:
                attached.update(p.reference_ids[:room])
        product_has_ref = {p.ref: any(r in attached for r in p.reference_ids) for p in spec.products}

        entries: list[ManifestEntry] = []
        lines: list[str] = ["[nano_banana] Generate an original vertical 9:16 TikTok-Shop image."]
        scene_bits: list[str] = []      # accumulate the scene body so it survives as prose

        def enc(req, line=None):
            entries.append(ManifestEntry(req, "encoded"))
            if line:
                lines.append(line)

        def uns(req, reason):
            entries.append(ManifestEntry(req, "unsupported", reason))

        for req in slide_requirements(spec):
            k = req.id.kind

            if k == "scene_concept":
                scene_bits.append(f"Scene: {req.get('concept')}")
                enc(req)
            elif k == "subject_presence":
                if req.get("present"):
                    scene_bits.append("A human subject is present.")
                else:
                    scene_bits.append("No human subject in frame.")
                enc(req)
            elif k == "subject_action":
                scene_bits.append(f"The subject is {req.get('action')}.")
                enc(req)
            elif k == "subject_emotion":
                emo = ", ".join(req.get("emotion") or ())
                if emo:
                    scene_bits.append(f"Emotional register: {emo}.")
                enc(req)
            elif k == "environment":
                scene_bits.append(f"Environment: {req.get('environment')}.")
                enc(req)
            elif k == "lighting":
                scene_bits.append(f"Lighting: {req.get('lighting')}.")
                enc(req)
            elif k == "dynamics":
                scene_bits.append(f"Energy: {req.get('energy')}.")
                enc(req)
            elif k == "product_presence":
                if req.get("product_allowed"):
                    enc(req, "The promoted product must be visible in this frame.")
                else:
                    enc(req, "Do NOT show the promoted product in this frame (it is withheld here).")
            elif k == "focal":
                w = req.get("weight")
                if w == "primary":
                    enc(req, f"Make {req.get('element')} the dominant focal point.")
                elif w == "absent":
                    enc(req, f"{req.get('element')} must NOT appear in this frame.")
                else:
                    enc(req)
            elif k == "invariant":
                enc(req, f"Preserve (invariant): {req.get('statement')} — you choose the composition.")
            elif k == "opening":
                if caps.can_reserve_open_zone:
                    enc(req, f"Leave the {req.get('zone')} clear/uncluttered for '{req.get('purpose')}' "
                             f"(strictness: {req.get('strictness')}).")
                else:
                    uns(req, "adapter cannot reserve a clean zone")
            elif k == "overlay_exclusion":
                # The copy is added by the creator later; the image must not bake it in.
                enc(req)
            elif k == "render_text":
                fidelity = req.get("fidelity")
                text = req.get("text") or ""
                owner = req.get("owner") or ""
                if fidelity == "exact_text":
                    if caps.can_render_exact_text:
                        enc(req, f'Render the exact text: "{text}".')
                    else:
                        uns(req, "provider cannot guarantee legible exact text — needs compositing "
                                 "or a different execution path")
                elif fidelity == "reference_fidelity":
                    if owner and product_has_ref.get(owner):
                        enc(req, f'Reproduce "{text}" faithfully as it appears on referenced product {owner}.')
                    elif owner:
                        uns(req, f"reference fidelity for '{text}' requires product {owner}'s reference, "
                                 f"which is not attached")
                    else:
                        uns(req, f"reference fidelity for '{text}' has no owning reference target")
                elif fidelity == "semantic_presence":
                    enc(req, f'Keep the idea of "{text}" recognisably present (exact wording not required).')
                elif fidelity == "none":
                    enc(req)      # decorative / no fidelity obligation
                else:
                    uns(req, f"unresolved text fidelity '{fidelity}' — not encoded")
            elif k == "product_identity":
                if product_has_ref.get(req.id.ref):
                    enc(req, f"Reproduce product '{req.get('label')}' exactly from its attached reference; "
                             f"regenerate the scene around it.")
                else:
                    uns(req, "no reference could be attached to anchor product identity")
            elif k == "reference":
                rid = req.get("reference_id")
                if rid in attached:
                    enc(req)
                else:
                    uns(req, f"exceeds adapter max_references={caps.max_references}")
            elif k == "gap":
                uns(req, f"acknowledged upstream gap, not encodable by this provider: {req.get('reason')}")
            else:
                uns(req, f"unknown requirement kind '{k}'")

        if scene_bits:
            lines.insert(1, " ".join(scene_bits))
        if any(t.disposition == "overlay_handoff" for t in spec.texts):
            lines.append("Render NO overlay text, captions, prices or watermarks — that copy is added later.")

        variations = tuple(caps.variable_axes) if not spec.attention.reuse_source_framing else ()
        if variations:
            lines.append("Do not reuse the source framing; vary: " + ", ".join(variations) + ".")

        manifest = RequestManifest(slide_index=spec.slide_index, entries=tuple(entries),
                                   variations_requested=variations)
        return AdapterOutput(spec.slide_index, self.name, "\n".join(lines), manifest)
