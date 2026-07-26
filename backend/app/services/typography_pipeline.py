"""
Live typography integration (ADR 0001 WP-1.5A).

Wires the proven L1 renderer into final-output production. Deliberately does
NOT include zone reservation, occupancy detection or background repair -
those are WP-1.5B. We must be able to prove the renderer is correctly wired
before debugging whether the provider leaves clean zones.

Behind `CAE_TYPOGRAPHY_RENDERER_ENABLED`, default off. Rollback is the flag.
"""

from __future__ import annotations

import logging

from PIL import Image

from app.services.profile_schema import TypographySystem
from app.services.render_manifest import (
    RenderedBlock,
    RenderManifest,
    SkippedBlock,
    start_manifest,
)
from app.services.text_ownership import Owner, OwnershipPlan
from app.services.editorial_renderer import TextBlock, render_typography
from app.services.typography import (
    is_known_colour,
    CapabilityLevel,
    FamilyClass,
    TextStyle,
    TypographySystem as RendererSystem,
    UnavailableFontToken,
    UnmappedFontToken,
    token_for,
)

logger = logging.getLogger(__name__)

#: Role names the L1 renderer understands, in the order they are laid out.
_DEFAULT_ROLE = "body"


def _colour_resolver(system: TypographySystem):
    """
    Turn a style's colour ROLE into a named colour, via the project's own map.

    `TextRole.colour_role` names a role the design distinguishes (`accent`,
    `body`); `system.colour_roles` says what colour that role is in this
    project. Skipping the dereference handed `accent` straight to the
    renderer, which did not recognise it and drew near-black - flattening
    benchmark 4's red accent to black while every schema-level assertion
    still passed.

    Returns `(resolve, unresolved)`, where `unresolved` collects roles the
    project never defined so the caller can warn rather than let the
    fallback pass unnoticed.
    """
    unresolved: list[str] = []

    def resolve(role: str | None) -> str | None:
        if role is None:
            return None
        named = system.colour_roles.get(role, role)
        if not is_known_colour(named):
            unresolved.append(role)
        return named

    return resolve, unresolved


def to_renderer_system(system: TypographySystem) -> tuple[RendererSystem, list[str]]:
    """
    Translate the persisted (Pydantic) system into the renderer's own dataclass.

    Independent role maps are flattened into the renderer's per-role styles
    WITHOUT collapsing marker, rule or italic roles into the text style - the
    WP-1.4 gate proved that conflation renders benchmark 4's red markers black
    and visibly flattens the hierarchy.

    Returns the system and any colour roles that could not be resolved.
    """
    styles: dict[str, TextStyle] = {}
    colour_of, unresolved = _colour_resolver(system)

    for role, text_role in system.text_roles.items():
        marker = system.marker_roles.get(role)
        rule = system.rule_roles.get(role)
        styles[role] = TextStyle(
            family=FamilyClass(str(text_role.family_class)),
            weight=text_role.weight,
            italic=text_role.italic,
            case=text_role.case,
            colour_role=colour_of(text_role.colour_role),
            alignment=text_role.alignment,
            size_ratio=text_role.size_ratio,
            tracking=text_role.tracking,
            line_spacing=text_role.line_height,
            bullet=marker.glyph if marker else None,
            bullet_colour_role=colour_of(marker.colour_role) if marker else None,
            rule_below=rule is not None,
        )

    for role, italic_role in system.italic_roles.items():
        styles[role] = TextStyle(
            family=FamilyClass(str(italic_role.family_class)),
            weight=italic_role.weight,
            italic=True,
            case=italic_role.case,
            colour_role=colour_of(italic_role.colour_role),
            alignment=italic_role.alignment,
            size_ratio=italic_role.size_ratio,
            tracking=italic_role.tracking,
            line_spacing=italic_role.line_height,
        )

    renderer_system = RendererSystem(
        primary_family=FamilyClass(str(system.primary_family_class)),
        secondary_family=(
            FamilyClass(str(system.secondary_family_class))
            if system.secondary_family_class
            else None
        ),
        styles=styles,
        capability_level=CapabilityLevel(str(system.capability_level)),
        base_size_ratio=system.base_size_ratio,
    )
    return renderer_system, sorted(set(unresolved))


def apply_typography(
    image_bytes: bytes,
    plan: OwnershipPlan,
    system: TypographySystem | None,
    *,
    role_for_block: dict[str, str] | None = None,
    profile_id: str | None = None,
    effective_policies: dict[str, str] | None = None,
    enforce_clean_zones: bool = True,
    contract=None,
) -> tuple[bytes, RenderManifest]:
    """
    Draw every deterministic-typography block, and account for every other.

    Returns the image bytes and the manifest. Blocks owned by the image or by
    Product Lock are recorded and left alone - re-typesetting them would
    fabricate branded packaging (ADR §6). Caption blocks are recorded here and
    drawn by the existing caption path, which continues to own them.
    """
    manifest = start_manifest(
        plan,
        profile_id=profile_id,
        typography_schema_version=system.schema_version if system else None,
        effective_policies=effective_policies or {},
    )
    roles = role_for_block or {}

    for decision in plan.decisions:
        if decision.owner is Owner.CAPTION:
            manifest.caption_blocks.append(decision.block_id)
        elif decision.owner is Owner.REVIEW:
            manifest.skipped_blocks.append(
                SkippedBlock(
                    block_id=decision.block_id, text=decision.text, owner=str(decision.owner),
                    reason="awaiting human review - preserved, not rendered or removed",
                )
            )

    typography_blocks = [
        d for d in plan.decisions if d.owner is Owner.TYPOGRAPHY
    ]
    if not typography_blocks:
        return image_bytes, manifest

    if system is None:
        manifest.warnings.append(
            "designed typography was routed to the deterministic renderer but the "
            "project has no analysed typography system - blocks left to the image"
        )
        for decision in typography_blocks:
            manifest.skipped_blocks.append(
                SkippedBlock(
                    block_id=decision.block_id, text=decision.text, owner=str(decision.owner),
                    reason="no typography system available",
                )
            )
        return image_bytes, manifest

    renderer_system, unresolved_colours = to_renderer_system(system)
    for role in unresolved_colours:
        manifest.warnings.append(
            f"colour role {role!r} is not defined by the project and no named "
            "colour matches it - drawn near-black, which may flatten the hierarchy"
        )
    from io import BytesIO

    # Every owner gets clean, uncontested space before it renders. Zones come
    # from the Composition Contract where there is one: an owner's region is
    # not the same as its OCR box, and a rule has no OCR box at all.
    if enforce_clean_zones:
        from app.services.graphic_ownership import enforce

        # Only clear graphic zones something will actually redraw. Without a
        # rule or divider role there is no owner for them, and clearing an
        # unowned zone deletes the element rather than cleaning it.
        graphic_owner_will_draw = bool(system.rule_roles or system.divider_roles)
        image_bytes, enforcement = enforce(
            image_bytes, plan, contract,
            graphic_owner_will_draw=graphic_owner_will_draw,
        )
        if not graphic_owner_will_draw and contract is not None:
            unowned = [
                z.zone_id for z in contract.zones if str(z.role) == "graphic"
            ]
            if unowned:
                manifest.warnings.append(
                    f"graphic zones {unowned} were left untouched - the project's "
                    "typography system defines no rule or divider role, so nothing "
                    "would have redrawn them"
                )
        manifest.render_zones = enforcement.render_zones
        manifest.zone_occupancy = enforcement.occupancy
        manifest.ownership_attempts = enforcement.attempts
        manifest.cleanup_actions = enforcement.cleanup_actions
        for block_id in enforcement.unresolved:
            manifest.warnings.append(
                f"{block_id}: no ladder rung produced clean space - rendered anyway, "
                "review the result"
            )

    image = Image.open(BytesIO(image_bytes))
    to_draw: list[TextBlock] = []

    for decision in typography_blocks:
        role = roles.get(decision.block_id, _DEFAULT_ROLE)
        if decision.bounds is None:
            manifest.skipped_blocks.append(
                SkippedBlock(
                    block_id=decision.block_id, text=decision.text, owner=str(decision.owner),
                    reason="no bounding box from OCR - cannot place deterministically",
                )
            )
            continue

        style = renderer_system.style_for(role)
        try:
            token = token_for(style.family, style.weight, style.italic)
        except (UnmappedFontToken, UnavailableFontToken) as exc:
            # Never silently substitute the caption face - see FONT_PORTABILITY.md.
            manifest.warnings.append(f"{decision.block_id}: {exc}")
            manifest.skipped_blocks.append(
                SkippedBlock(
                    block_id=decision.block_id, text=decision.text, owner=str(decision.owner),
                    reason=f"font token unavailable: {exc}",
                )
            )
            continue

        manifest.font_token_bindings.setdefault(token, "")
        to_draw.append(TextBlock(decision.text, role, decision.bounds))
        manifest.rendered_blocks.append(
            RenderedBlock(
                block_id=decision.block_id, text=decision.text, role=role,
                bounds=decision.bounds, font_token=token,
                colour_role=style.colour_role, owner=str(decision.owner),
            )
        )

    if to_draw:
        from app.services.typography import resolve_token

        for token in manifest.font_token_bindings:
            path, index = resolve_token(token)
            manifest.font_token_bindings[token] = f"{path}[{index}]"
        rendered, fit_warnings = render_typography(image, to_draw, renderer_system)
        manifest.warnings.extend(fit_warnings)
        buffer = BytesIO()
        rendered.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

    if not manifest.accounts_for_every_block():
        manifest.warnings.append(
            "manifest does not account for every source block - investigate before trusting it"
        )
    return image_bytes, manifest
