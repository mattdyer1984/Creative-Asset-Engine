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
    AdapterOutput, RequestManifest, ManifestEntry, Realization, slide_requirements,
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


from .provider_language import zone_purpose, element_phrase, humanize


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
        # Aspect is NOT invented here — it flows from the spec's canvas requirement below.
        lines: list[str] = ["[nano_banana] Generate an original TikTok-Shop image."]
        scene_bits: list[str] = []      # accumulate the scene body so it survives as prose

        # Every encoding records HOW it was realized, at the point of realization.
        def enc_line(req, line):                 # realized as a provider-facing text line
            lines.append(line)
            entries.append(ManifestEntry(req, "encoded", realization=Realization("text", line)))

        def enc_scene(req, bit):                 # realized as a scene-body fragment (merged into the prose)
            scene_bits.append(bit)
            entries.append(ManifestEntry(req, "encoded", realization=Realization("text", bit)))

        def enc_attach(req, ref):                # realized as an attached asset, not text
            entries.append(ManifestEntry(req, "encoded", realization=Realization("attachment", ref)))

        def enc_collective(req, marker):         # realized by a shared/global directive
            entries.append(ManifestEntry(req, "encoded", realization=Realization("collective", marker)))

        def enc_noop(req, why):                  # an intentional no-op — deliberately nothing to render
            entries.append(ManifestEntry(req, "encoded", realization=Realization("noop", why)))

        def uns(req, reason):
            entries.append(ManifestEntry(req, "unsupported", reason=reason))

        for req in slide_requirements(spec):
            k = req.id.kind

            if k == "canvas":
                out_aspect = req.get("output_aspect")
                src_aspect = req.get("source_aspect")
                line = f"Output aspect ratio: {out_aspect} (render the image at exactly {out_aspect})."
                if src_aspect and src_aspect != out_aspect:
                    line += f" The source was {src_aspect}; recompose for {out_aspect} rather than stretching."
                enc_line(req, line)
            elif k == "scene_concept":
                enc_scene(req, f"Scene: {req.get('concept')}")
            elif k == "subject_presence":
                if req.get("present"):
                    extent = req.get("extent") or "unspecified"
                    if extent in ("full figure", "unspecified", ""):
                        bit = "A person is present in the frame."
                    else:
                        bit = (f"Only the subject's {extent} is visible — do NOT render a full "
                               f"person or any body part that was not in the source.")
                else:
                    bit = "No human subject in frame."
                enc_scene(req, bit)
            elif k == "subject_action":
                enc_scene(req, f"The visible subject is {req.get('action')}.")
            elif k == "subject_product_relation":
                rel = req.get("relation")
                phrase = {
                    "holding": "held in the subject's hand",
                    "wearing": "worn by the subject",
                    "using": "used by the subject",
                }.get(rel, f"{rel} by the subject")
                enc_scene(req, f"The promoted product is {phrase}.")
            elif k == "subject_emotion":
                emo = ", ".join(req.get("emotion") or ())
                if emo:
                    enc_scene(req, f"Emotional register: {emo}.")
                else:
                    enc_noop(req, "no emotional register supplied — nothing to render")
            elif k == "environment":
                enc_scene(req, f"Environment: {req.get('environment')}.")
            elif k == "lighting":
                enc_scene(req, f"Lighting: {req.get('lighting')}.")
            elif k == "dynamics":
                enc_scene(req, f"Energy: {req.get('energy')}.")
            elif k == "product_presence":
                if req.get("product_allowed"):
                    enc_line(req, "The promoted product must be visible in this frame.")
                else:
                    enc_line(req, "Do NOT show the promoted product in this frame (it is withheld here).")
            elif k == "focal":
                w = req.get("weight")
                if w == "primary":
                    enc_line(req, f"Make {element_phrase(req.get('element'), spec)} the dominant focal point.")
                elif w == "absent":
                    enc_line(req, f"{element_phrase(req.get('element'), spec).capitalize()} must NOT appear in this frame.")
                else:
                    enc_noop(req, f"focal weight '{w}' carries no directive")
            elif k == "invariant":
                enc_line(req, f"Preserve: {humanize(req.get('statement'), spec)} — you choose the composition.")
            elif k == "opening":
                if caps.can_reserve_open_zone:
                    # The internal purpose enum never reaches the provider — it is
                    # translated to provider-facing language (adapter-purity family).
                    enc_line(req, f"Keep the {req.get('zone')} area visually clear and uncluttered "
                                  f"(reserved space for {zone_purpose(req.get('purpose'))}, added later); "
                                  f"render no text there.")
                else:
                    uns(req, "adapter cannot reserve a clean zone")
            elif k == "overlay_exclusion":
                # Realized collectively by the global "render NO overlay text" directive below;
                # the creator adds this copy later, so the image must not bake it in.
                enc_collective(req, "global no-overlay-text directive")
            elif k == "render_text":
                fidelity = req.get("fidelity")
                text = req.get("text") or ""
                owner = req.get("owner") or ""
                if fidelity == "exact_text":
                    if caps.can_render_exact_text:
                        enc_line(req, f'Render the exact text: "{text}".')
                    else:
                        uns(req, "provider cannot guarantee legible exact text — needs compositing "
                                 "or a different execution path")
                elif fidelity == "reference_fidelity":
                    if owner and product_has_ref.get(owner):
                        enc_line(req, f'Reproduce "{text}" faithfully as it appears on referenced product {owner}.')
                    elif owner:
                        uns(req, f"reference fidelity for '{text}' requires product {owner}'s reference, "
                                 f"which is not attached")
                    else:
                        uns(req, f"reference fidelity for '{text}' has no owning reference target")
                elif fidelity == "semantic_presence":
                    enc_line(req, f'Keep the idea of "{text}" recognisably present (exact wording not required).')
                elif fidelity == "none":
                    enc_noop(req, "decorative text — no fidelity obligation, nothing rendered")
                else:
                    uns(req, f"unresolved text fidelity '{fidelity}' — not encoded")
            elif k == "product_identity":
                if product_has_ref.get(req.id.ref):
                    enc_line(req, f"Reproduce product '{req.get('label')}' exactly from its attached reference; "
                                  f"regenerate the scene around it.")
                else:
                    uns(req, "no reference could be attached to anchor product identity")
            elif k == "reference":
                rid = req.get("reference_id")
                if rid in attached:
                    enc_attach(req, rid)
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
