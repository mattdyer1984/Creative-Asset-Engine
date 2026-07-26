"""
Creative Project Profile persistence (ADR 0001 WP-1.1).

The guarantee under test: re-running analysis never discards a human
decision. Everything else here supports that - versioning, schema handling,
and the per-role typography merge.
"""

import pytest

from app.models.analysis_run import AnalysisRun
from app.models.slideshow import Slideshow
from app.services.creative_project_profile import (
    DEFAULT_COPY_POLICY,
    DEFAULT_OVERLAY_POLICY,
    DEFAULT_PRODUCTION_VALUE,
    ProfileSchemaMismatch,
    apply_user_decisions,
    effective_copy_policy,
    effective_overlay_policy,
    effective_production_value_strategy,
    effective_primary_text_mode,
    effective_typography_system,
    get_current_profile,
    record_analysis,
    reset_user_decisions,
)
from app.services.profile_schema import (
    SCHEMA_VERSION,
    BlockClassificationEvidence,
    CapabilityLevel,
    ClassificationEvidence,
    CopyPolicy,
    FamilyClass,
    MarkerRole,
    OverlayPolicy,
    ProductionValueStrategy,
    RuleRole,
    TextMode,
    TextRole,
    TypographySystem,
    UserTypographyOverrides,
    merge_typography,
)


@pytest.fixture
def slideshow(db_session):
    row = Slideshow()
    db_session.add(row)
    db_session.flush()
    return row


def _run(db_session) -> str:
    run = AnalysisRun(
        analysis_type="creative_project_profile", provider="gemini",
        model_name="test", status="succeeded",
    )
    db_session.add(run)
    db_session.flush()
    return run.id


def _case04_system() -> TypographySystem:
    """Benchmark 4's system, with the independent roles the gate proved necessary."""
    return TypographySystem(
        primary_family_class=FamilyClass.SERIF,
        secondary_family_class=FamilyClass.SERIF,
        capability_level=CapabilityLevel.L1,
        base_size_ratio=0.030,
        colour_roles={"accent": "dark-red", "body": "near-black"},
        text_roles={
            "numeral": TextRole(family_class=FamilyClass.SERIF, colour_role="dark-red",
                                size_ratio=2.5),
            "headline": TextRole(family_class=FamilyClass.SERIF, colour_role="near-black",
                                 size_ratio=1.75),
            "bullet": TextRole(family_class=FamilyClass.SERIF, colour_role="near-black",
                               size_ratio=0.72),
        },
        italic_roles={
            "emphasis": TextRole(family_class=FamilyClass.SERIF, italic=True,
                                 colour_role="dark-red", size_ratio=1.75),
        },
        marker_roles={"bullet": MarkerRole(glyph="•", colour_role="dark-red")},
        rule_roles={"numeral": RuleRole(colour_role="dark-red", width_ratio=0.42)},
        size_scale={"headline_to_body": 2.9},
        case_rules=["sentence-case-headline"],
        weight_hierarchy=["regular-headline", "italic-emphasis", "regular-body"],
    )


# --- versioning and current-record behaviour -------------------------


def test_recording_analysis_creates_a_current_profile(db_session, slideshow):
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        primary_text_mode=TextMode.DESIGNED_TYPOGRAPHY, text_mode_confidence=1.0,
        typography_system=_case04_system(),
    )
    assert profile.is_current
    assert profile.schema_version == SCHEMA_VERSION
    assert get_current_profile(db_session, slideshow.id) is profile


def test_re_analysis_supersedes_rather_than_updates(db_session, slideshow):
    """History stays auditable - an analyser regression must be visible."""
    first = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        primary_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
    )
    second = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        primary_text_mode=TextMode.PLATFORM_CAPTION,
    )
    db_session.flush()
    assert second.id != first.id
    assert not first.is_current
    assert get_current_profile(db_session, slideshow.id) is second


# --- THE guarantee ---------------------------------------------------


def test_user_decisions_survive_re_analysis(db_session, slideshow):
    """
    A user who set the overlay policy to `remove` must not find it silently
    restored because the slideshow was analysed again.
    """
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        primary_text_mode=TextMode.PLATFORM_CAPTION,
    )
    apply_user_decisions(
        db_session, profile,
        overlay_policy=OverlayPolicy.REMOVE,
        copy_policy=CopyPolicy.PRESERVE_MEANING,
        production_value_strategy=ProductionValueStrategy.ELEVATE,
        primary_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
        typography_overrides=UserTypographyOverrides(
            marker_roles={"bullet": MarkerRole(glyph="—", colour_role="green")}
        ),
    )

    reanalysed = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        primary_text_mode=TextMode.PLATFORM_CAPTION, typography_system=_case04_system(),
    )

    assert effective_overlay_policy(reanalysed) is OverlayPolicy.REMOVE
    assert effective_copy_policy(reanalysed) is CopyPolicy.PRESERVE_MEANING
    assert effective_production_value_strategy(reanalysed) is ProductionValueStrategy.ELEVATE
    assert effective_primary_text_mode(reanalysed) is TextMode.DESIGNED_TYPOGRAPHY
    assert reanalysed.user_typography_overrides_json["marker_roles"]["bullet"]["glyph"] == "—"


def test_analysis_still_updates_its_own_fields_across_re_analysis(db_session, slideshow):
    """User decisions are preserved; analyser output is not frozen."""
    record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        primary_text_mode=TextMode.PLATFORM_CAPTION, text_mode_confidence=0.6,
    )
    second = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        primary_text_mode=TextMode.DESIGNED_TYPOGRAPHY, text_mode_confidence=0.95,
    )
    assert second.analysed_primary_text_mode == "designed_typography"
    assert second.analysed_text_mode_confidence == 0.95


def test_resetting_is_the_only_way_to_lose_a_user_decision(db_session, slideshow):
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session)
    )
    apply_user_decisions(db_session, profile, overlay_policy=OverlayPolicy.REMOVE)
    reset_user_decisions(db_session, profile)
    assert profile.user_overlay_policy is None
    assert effective_overlay_policy(profile) is DEFAULT_OVERLAY_POLICY


def test_defaults_apply_when_no_human_has_decided(db_session, slideshow):
    """ADR §13: suggested, visible, overridable - never silent."""
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session)
    )
    assert effective_copy_policy(profile) is DEFAULT_COPY_POLICY
    assert effective_overlay_policy(profile) is DEFAULT_OVERLAY_POLICY
    assert effective_production_value_strategy(profile) is DEFAULT_PRODUCTION_VALUE
    assert DEFAULT_COPY_POLICY is CopyPolicy.PRESERVE_VERBATIM
    assert DEFAULT_PRODUCTION_VALUE is ProductionValueStrategy.REFINE


# --- round-trip persistence of the complete typography system --------


def test_the_complete_typography_system_round_trips(db_session, slideshow):
    """Every independent role must survive the database unchanged."""
    original = _case04_system()
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        typography_system=original,
    )
    db_session.flush()
    db_session.expire_all()

    restored = effective_typography_system(get_current_profile(db_session, slideshow.id))
    assert restored == original


def test_marker_rule_and_italic_roles_stay_independent(db_session, slideshow):
    """
    The WP-1.4 gate proved these cannot be folded back into the text style:
    markers inheriting the text colour rendered black where benchmark 4 has
    red, visibly flattening the hierarchy.
    """
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        typography_system=_case04_system(),
    )
    system = effective_typography_system(profile)
    assert system.marker_roles["bullet"].colour_role == "dark-red"
    assert system.text_roles["bullet"].colour_role == "near-black"
    assert system.rule_roles["numeral"].colour_role == "dark-red"
    assert system.italic_roles["emphasis"].italic is True


def test_classification_evidence_round_trips(db_session, slideshow):
    evidence = ClassificationEvidence(
        blocks=[
            BlockClassificationEvidence(
                text="1.", text_class="designed_typography", confidence=1.0,
                reasons=["editorial: standalone list numeral"],
            )
        ],
        project_mode_reasons=["4 of 5 blocks read as designed typography"],
    )
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        classification_evidence=evidence,
    )
    db_session.flush()
    restored = ClassificationEvidence.model_validate(profile.classification_evidence_json)
    assert restored == evidence


# --- schema versioning -----------------------------------------------


def test_a_future_schema_version_is_refused_not_coerced(db_session, slideshow):
    """
    Silently reading an old shape as current is how a field quietly means
    something different from what its writer intended.
    """
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
        typography_system=_case04_system(),
    )
    profile.analysed_typography_system_json = {
        **profile.analysed_typography_system_json, "schema_version": "99.0",
    }
    with pytest.raises(ProfileSchemaMismatch, match="99.0"):
        effective_typography_system(profile)


def test_absent_analysis_returns_none_rather_than_an_empty_system(db_session, slideshow):
    """An empty system would read as a finding; absence must be explicit."""
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session)
    )
    assert effective_typography_system(profile) is None
    assert effective_primary_text_mode(profile) is None


# --- the per-role merge ----------------------------------------------


def test_overriding_one_role_leaves_the_others_analysed():
    analysed = _case04_system()
    merged = merge_typography(
        analysed,
        UserTypographyOverrides(marker_roles={"bullet": MarkerRole(glyph="—", colour_role="green")}),
    )
    assert merged.marker_roles["bullet"].glyph == "—"
    assert merged.text_roles["headline"] == analysed.text_roles["headline"]
    assert merged.rule_roles["numeral"] == analysed.rule_roles["numeral"]


def test_merging_never_mutates_the_analysed_system():
    """The analysed system must stay intact for comparison and for the UI."""
    analysed = _case04_system()
    before = analysed.model_dump(mode="json")
    merge_typography(analysed, UserTypographyOverrides(primary_family_class=FamilyClass.GROTESQUE))
    assert analysed.model_dump(mode="json") == before


def test_no_overrides_returns_the_analysed_system_unchanged():
    analysed = _case04_system()
    assert merge_typography(analysed, None) == analysed


def test_user_decisions_survive_repeated_re_analysis(db_session, slideshow):
    """
    ADR §14a: user values carry forward on EVERY cycle, not merely the first.
    A carry-forward that worked once and then dropped the value on the second
    pass would be worse than none - it would look correct in testing and fail
    in use.
    """
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session)
    )
    apply_user_decisions(
        db_session, profile,
        overlay_policy=OverlayPolicy.REMOVE,
        copy_policy=CopyPolicy.PRESERVE_MEANING,
        production_value_strategy=ProductionValueStrategy.MATCH,
        typography_overrides=UserTypographyOverrides(
            colour_roles={"accent": "green"},
            marker_roles={"bullet": MarkerRole(glyph="›", colour_role="green")},
        ),
    )

    current = profile
    for cycle in range(5):
        current = record_analysis(
            db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session),
            primary_text_mode=TextMode.PLATFORM_CAPTION,
            typography_system=_case04_system(),
        )
        assert effective_overlay_policy(current) is OverlayPolicy.REMOVE, f"lost at cycle {cycle}"
        assert effective_copy_policy(current) is CopyPolicy.PRESERVE_MEANING
        assert effective_production_value_strategy(current) is ProductionValueStrategy.MATCH
        system = effective_typography_system(current)
        assert system.marker_roles["bullet"].glyph == "›", f"override lost at cycle {cycle}"
        assert system.colour_roles["accent"] == "green"
        # …while the analysed half is genuinely refreshed each time.
        assert current.analysed_primary_text_mode == "platform_caption"

    # Exactly one current row survives five cycles.
    from app.models.creative_project_profile import CreativeProjectProfile
    rows = db_session.query(CreativeProjectProfile).filter_by(slideshow_id=slideshow.id).all()
    assert sum(1 for r in rows if r.is_current) == 1
    # 1 initial analysis + 5 cycles. apply_user_decisions updates in place
    # and creates no row - a user decision is a standing instruction, not
    # a new observation to version.
    assert len(rows) == 6


def test_a_reset_does_not_resurrect_on_the_next_analysis(db_session, slideshow):
    """Once reset, a decision stays gone until the user makes a new one."""
    profile = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session)
    )
    apply_user_decisions(db_session, profile, overlay_policy=OverlayPolicy.REMOVE)
    reset_user_decisions(db_session, profile)
    after = record_analysis(
        db_session, slideshow_id=slideshow.id, analysis_run_id=_run(db_session)
    )
    assert after.user_overlay_policy is None
    assert effective_overlay_policy(after) is DEFAULT_OVERLAY_POLICY
