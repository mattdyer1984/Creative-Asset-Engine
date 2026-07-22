"""
Unit tests for app.services.staleness - Phase 7.4 of the Narrative pass
(see MIGRATION_PLAN.md's architecture direction for this phase).
"""

from app.models.analysis_run import (
    ANALYSIS_TYPE_CREATIVE_FINGERPRINT,
    ANALYSIS_TYPE_MARKETING_ANALYSIS,
    ANALYSIS_TYPE_NARRATIVE_STRUCTURE,
    ANALYSIS_TYPE_OCR,
    ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE,
    ANALYSIS_TYPE_RECREATION_PROMPT,
    STATUS_SUCCEEDED,
    AnalysisRun,
)
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.models.narrative_structure import NarrativeStructure
from app.models.ocr_result import OCRResult
from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.recreation_prompt import RecreationPrompt
from app.services.staleness import (
    creative_fingerprint_staleness,
    marketing_analysis_staleness,
    narrative_structure_staleness,
    product_lock_profile_staleness,
    recreation_prompt_staleness,
)


def _run(db_session, analysis_type, **kwargs):
    run = AnalysisRun(analysis_type=analysis_type, provider="fake", model_name="fake", status=STATUS_SUCCEEDED, **kwargs)
    db_session.add(run)
    db_session.flush()
    return run


def _make_product(db_session) -> Product:
    product = Product(display_name="Test Product")
    db_session.add(product)
    db_session.flush()
    return product


# --- product_lock_profile_staleness -----------------------------------------


def test_lock_profile_fresh_when_recorded_ids_match_current(db_session):
    product = _make_product(db_session)
    run = _run(db_session, ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE)
    image = ProductReferenceImage(
        analysis_run_id=run.id, product_id=product.id, isolation_method="llm_bounding_box_v1", file_path="/x.jpg"
    )
    db_session.add(image)
    db_session.flush()

    lock_profile = ProductLockProfile(
        analysis_run_id=run.id,
        product_id=product.id,
        structured_json={},
        reference_image_ids_json=[image.id],
    )
    db_session.add(lock_profile)
    db_session.commit()

    result = product_lock_profile_staleness(db_session, lock_profile)
    assert result.is_stale is False


def test_lock_profile_stale_when_isolation_reran_since(db_session):
    product = _make_product(db_session)
    run = _run(db_session, ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE)
    old_image = ProductReferenceImage(
        analysis_run_id=run.id,
        product_id=product.id,
        isolation_method="llm_bounding_box_v1",
        file_path="/x.jpg",
        is_current=False,
    )
    new_image = ProductReferenceImage(
        analysis_run_id=run.id, product_id=product.id, isolation_method="llm_bounding_box_v1", file_path="/y.jpg"
    )
    db_session.add_all([old_image, new_image])
    db_session.flush()

    lock_profile = ProductLockProfile(
        analysis_run_id=run.id,
        product_id=product.id,
        structured_json={},
        reference_image_ids_json=[old_image.id],  # stale snapshot - isolation moved on to new_image
    )
    db_session.add(lock_profile)
    db_session.commit()

    result = product_lock_profile_staleness(db_session, lock_profile)
    assert result.is_stale is True
    assert result.stale_because == ["product_isolation"]


def test_lock_profile_fresh_when_neither_has_isolation_output(db_session):
    """Product Lock Profile can run before Product Isolation ever has - empty vs. empty is fresh, not stale."""
    product = _make_product(db_session)
    run = _run(db_session, ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE)
    lock_profile = ProductLockProfile(
        analysis_run_id=run.id, product_id=product.id, structured_json={}, reference_image_ids_json=[]
    )
    db_session.add(lock_profile)
    db_session.commit()

    result = product_lock_profile_staleness(db_session, lock_profile)
    assert result.is_stale is False


# --- creative_fingerprint_staleness ------------------------------------------


def test_fingerprint_unknown_when_no_ocr_recorded(db_session):
    run = _run(db_session, ANALYSIS_TYPE_CREATIVE_FINGERPRINT)
    fingerprint = CreativeFingerprint(analysis_run_id=run.id, structured_json={}, ocr_result_id=None)
    db_session.add(fingerprint)
    db_session.commit()

    result = creative_fingerprint_staleness(db_session, fingerprint)
    assert result.is_stale is False


def test_fingerprint_fresh_when_recorded_ocr_still_current(db_session):
    ocr_run = _run(db_session, ANALYSIS_TYPE_OCR)
    ocr_result = OCRResult(analysis_run_id=ocr_run.id, raw_text="Headline")
    db_session.add(ocr_result)
    db_session.flush()

    fp_run = _run(db_session, ANALYSIS_TYPE_CREATIVE_FINGERPRINT)
    fingerprint = CreativeFingerprint(analysis_run_id=fp_run.id, structured_json={}, ocr_result_id=ocr_result.id)
    db_session.add(fingerprint)
    db_session.commit()

    result = creative_fingerprint_staleness(db_session, fingerprint)
    assert result.is_stale is False


def test_fingerprint_stale_when_recorded_ocr_no_longer_current(db_session):
    ocr_run = _run(db_session, ANALYSIS_TYPE_OCR)
    old_ocr = OCRResult(analysis_run_id=ocr_run.id, raw_text="Old headline", is_current=False)
    db_session.add(old_ocr)
    db_session.flush()

    fp_run = _run(db_session, ANALYSIS_TYPE_CREATIVE_FINGERPRINT)
    fingerprint = CreativeFingerprint(analysis_run_id=fp_run.id, structured_json={}, ocr_result_id=old_ocr.id)
    db_session.add(fingerprint)
    db_session.commit()

    result = creative_fingerprint_staleness(db_session, fingerprint)
    assert result.is_stale is True
    assert result.stale_because == ["ocr"]


# --- marketing_analysis_staleness --------------------------------------------


def test_marketing_analysis_unknown_when_no_fingerprint_recorded(db_session):
    run = _run(db_session, ANALYSIS_TYPE_MARKETING_ANALYSIS)
    ma = MarketingAnalysis(analysis_run_id=run.id, narrative_text="x", creative_fingerprint_id=None)
    db_session.add(ma)
    db_session.commit()

    assert marketing_analysis_staleness(db_session, ma).is_stale is False


def test_marketing_analysis_stale_when_fingerprint_regenerated(db_session):
    fp_run = _run(db_session, ANALYSIS_TYPE_CREATIVE_FINGERPRINT)
    old_fp = CreativeFingerprint(analysis_run_id=fp_run.id, structured_json={}, is_current=False)
    db_session.add(old_fp)
    db_session.flush()

    ma_run = _run(db_session, ANALYSIS_TYPE_MARKETING_ANALYSIS)
    ma = MarketingAnalysis(analysis_run_id=ma_run.id, narrative_text="x", creative_fingerprint_id=old_fp.id)
    db_session.add(ma)
    db_session.commit()

    result = marketing_analysis_staleness(db_session, ma)
    assert result.is_stale is True
    assert result.stale_because == ["creative_fingerprint"]


# --- narrative_structure_staleness -------------------------------------------


def test_narrative_structure_fresh_when_ocr_ids_match(db_session, slideshow_with_slide):
    slide = slideshow_with_slide.primary_slide
    ocr_run = _run(db_session, ANALYSIS_TYPE_OCR)
    ocr_result = OCRResult(analysis_run_id=ocr_run.id, slide_id=slide.id, raw_text="Headline")
    db_session.add(ocr_result)
    db_session.flush()
    slide.current_ocr_result_id = ocr_result.id

    ns_run = _run(db_session, ANALYSIS_TYPE_NARRATIVE_STRUCTURE)
    narrative = NarrativeStructure(
        analysis_run_id=ns_run.id,
        slideshow_id=slideshow_with_slide.id,
        structured_json={"slides": [], "arc_summary": ""},
        ocr_result_ids_json=[ocr_result.id],
    )
    db_session.add(narrative)
    db_session.commit()

    assert narrative_structure_staleness(db_session, narrative).is_stale is False


def test_narrative_structure_stale_when_a_slides_ocr_reran(db_session, slideshow_with_slide):
    slide = slideshow_with_slide.primary_slide
    ocr_run = _run(db_session, ANALYSIS_TYPE_OCR)
    old_ocr = OCRResult(analysis_run_id=ocr_run.id, slide_id=slide.id, raw_text="Old", is_current=False)
    new_ocr = OCRResult(analysis_run_id=ocr_run.id, slide_id=slide.id, raw_text="New")
    db_session.add_all([old_ocr, new_ocr])
    db_session.flush()
    slide.current_ocr_result_id = new_ocr.id

    ns_run = _run(db_session, ANALYSIS_TYPE_NARRATIVE_STRUCTURE)
    narrative = NarrativeStructure(
        analysis_run_id=ns_run.id,
        slideshow_id=slideshow_with_slide.id,
        structured_json={"slides": [], "arc_summary": ""},
        ocr_result_ids_json=[old_ocr.id],  # stale snapshot
    )
    db_session.add(narrative)
    db_session.commit()

    result = narrative_structure_staleness(db_session, narrative)
    assert result.is_stale is True
    assert result.stale_because == ["ocr"]


# --- recreation_prompt_staleness ---------------------------------------------


def _make_current_lock_profile_and_fingerprint(db_session, product):
    lp_run = _run(db_session, ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE)
    lock_profile = ProductLockProfile(
        analysis_run_id=lp_run.id, product_id=product.id, structured_json={}, reference_image_ids_json=[]
    )
    fp_run = _run(db_session, ANALYSIS_TYPE_CREATIVE_FINGERPRINT)
    fingerprint = CreativeFingerprint(analysis_run_id=fp_run.id, structured_json={})
    db_session.add_all([lock_profile, fingerprint])
    db_session.flush()
    return lock_profile, fingerprint


def test_recreation_prompt_fresh_when_both_dependencies_still_current(db_session):
    product = _make_product(db_session)
    lock_profile, fingerprint = _make_current_lock_profile_and_fingerprint(db_session, product)

    rp_run = _run(db_session, ANALYSIS_TYPE_RECREATION_PROMPT)
    recreation_prompt = RecreationPrompt(
        analysis_run_id=rp_run.id,
        product_lock_profile_id=lock_profile.id,
        creative_fingerprint_id=fingerprint.id,
        structured_json={},
    )
    db_session.add(recreation_prompt)
    db_session.commit()

    assert recreation_prompt_staleness(db_session, recreation_prompt).is_stale is False


def test_recreation_prompt_stale_when_lock_profile_regenerated(db_session):
    product = _make_product(db_session)
    lock_profile, fingerprint = _make_current_lock_profile_and_fingerprint(db_session, product)
    lock_profile.is_current = False  # a newer one has since become current

    rp_run = _run(db_session, ANALYSIS_TYPE_RECREATION_PROMPT)
    recreation_prompt = RecreationPrompt(
        analysis_run_id=rp_run.id,
        product_lock_profile_id=lock_profile.id,
        creative_fingerprint_id=fingerprint.id,
        structured_json={},
    )
    db_session.add(recreation_prompt)
    db_session.commit()

    result = recreation_prompt_staleness(db_session, recreation_prompt)
    assert result.is_stale is True
    assert result.stale_because == ["product_lock_profile"]


def test_recreation_prompt_stale_on_both_dependencies_at_once(db_session):
    product = _make_product(db_session)
    lock_profile, fingerprint = _make_current_lock_profile_and_fingerprint(db_session, product)
    lock_profile.is_current = False
    fingerprint.is_current = False

    rp_run = _run(db_session, ANALYSIS_TYPE_RECREATION_PROMPT)
    recreation_prompt = RecreationPrompt(
        analysis_run_id=rp_run.id,
        product_lock_profile_id=lock_profile.id,
        creative_fingerprint_id=fingerprint.id,
        structured_json={},
    )
    db_session.add(recreation_prompt)
    db_session.commit()

    result = recreation_prompt_staleness(db_session, recreation_prompt)
    assert result.is_stale is True
    assert set(result.stale_because) == {"product_lock_profile", "creative_fingerprint"}
