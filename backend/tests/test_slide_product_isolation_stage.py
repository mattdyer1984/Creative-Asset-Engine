"""
Unit tests for SlideProductIsolationStage (new pipeline, Phase 2.4a) -
mirrors tests/test_product_isolation_stage.py's coverage of the old
ProductIsolationStage.
"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.models.analysis_run import STATUS_SUCCEEDED, AnalysisRun
from app.models.product import Product
from app.models.product_appearance import ProductAppearance
from app.models.product_reference_image import ProductReferenceImage
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.slideshow_stages.product_isolation_stage import (
    ISOLATION_METHOD,
    _MULTI_PRODUCT_ERROR,
    SlideProductIsolationStage,
    _crop_bounding_boxes,
)
from tests.fakes import FakeAIProviderRegistry, FakeProductIsolationProvider


def _add_second_current_appearance(db_session, slideshow_with_product):
    """
    slideshow_with_product's fixture already gives the slide one current
    ProductAppearance - this adds a second, distinct-product one, to
    exercise Phase 6.2's multi-product rejection path (see
    MIGRATION_PLAN.md's Phase 6.2 plan revision).
    """
    second_product = Product(display_name="Second Product")
    db_session.add(second_product)
    db_session.flush()

    slide = slideshow_with_product.primary_slide
    db_session.add(
        ProductAppearance(
            slide_id=slide.id,
            product_id=second_product.id,
            prominence="secondary",
            confidence=1.0,
            is_current=True,
        )
    )
    db_session.commit()


def test_fails_gracefully_without_a_product_assigned(db_session, slideshow_with_slide, monkeypatch):
    """slideshow_with_slide (not slideshow_with_product) has no ProductAppearance."""
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "No product assigned" in result.error
    # No AnalysisRun should even be created for a prerequisite that was never met.
    assert db_session.scalars(select(AnalysisRun)).first() is None


def test_succeeds_and_crops_reference_image(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow_with_product)

    assert result.succeeded is True

    slide = slideshow_with_product.primary_slide
    reference_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(
                ProductReferenceImage.source_slide_id == slide.id
            )
        )
    )
    assert len(reference_images) == 1
    ref = reference_images[0]
    assert ref.is_current is True
    assert ref.isolation_method == ISOLATION_METHOD
    assert ref.source_slide_id == slide.id

    analysis_run = db_session.get(AnalysisRun, ref.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "product_isolation"
    assert analysis_run.slide_id == slide.id


def test_fails_gracefully_when_no_product_detected_anywhere(db_session, slideshow_with_product, monkeypatch):
    """
    The only slide in this slideshow has a product assigned but none
    detected - with no other slide to fall back on, that's a real,
    actionable failure (nothing to build a Reference Library from).
    """
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=FakeProductIsolationProvider(bounding_boxes=[])),
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "No product could be detected in any slide" in result.error

    # The slide's own ProductAppearance was still retracted (consistent
    # with the per-slide handling), and its AnalysisRun still succeeded -
    # only the STAGE's overall result is a failure.
    slide = slideshow_with_product.primary_slide
    appearance = db_session.scalars(
        select(ProductAppearance).where(ProductAppearance.slide_id == slide.id)
    ).first()
    assert appearance.is_current is False
    analysis_run = db_session.scalars(select(AnalysisRun)).first()
    assert analysis_run.status == STATUS_SUCCEEDED


def test_rerun_produces_new_version_and_flips_previous(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideProductIsolationStage()
    stage.run(db_session, slideshow_with_product)
    stage.run(db_session, slideshow_with_product)

    product_id = slideshow_with_product.primary_slide.product_appearances[0].product_id
    all_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(ProductReferenceImage.product_id == product_id)
        )
    )
    assert len(all_images) == 2
    current = [img for img in all_images if img.is_current]
    assert len(current) == 1


def test_multiple_crops_are_all_persisted_and_current(db_session, slideshow_with_product, monkeypatch):
    two_boxes = [
        {"x_min": 0.1, "y_min": 0.1, "x_max": 0.4, "y_max": 0.9, "confidence": 0.9, "notes": "left bottle"},
        {"x_min": 0.6, "y_min": 0.1, "x_max": 0.9, "y_max": 0.9, "confidence": 0.85, "notes": "right bottle"},
    ]
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=FakeProductIsolationProvider(bounding_boxes=two_boxes)),
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow_with_product)

    assert result.succeeded is True
    slide = slideshow_with_product.primary_slide
    images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(ProductReferenceImage.source_slide_id == slide.id)
        )
    )
    assert len(images) == 2
    assert all(img.is_current for img in images)


def test_fails_clearly_with_multiple_distinct_products_assigned(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Phase 6.2: a slide with 2+ distinct current products fails with an
    explicit, honest error rather than silently isolating the same crop
    twice under two different product_ids (see MIGRATION_PLAN.md's
    Phase 6.2 plan revision for why looping wasn't safe to implement).
    """
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    _add_second_current_appearance(db_session, slideshow_with_product)

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert result.error == _MULTI_PRODUCT_ERROR
    # No AnalysisRun should even be created - this fails before any provider call.
    assert db_session.scalars(select(AnalysisRun)).first() is None


def _make_two_slide_slideshow_with_shared_product(db_session, tmp_path):
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md): mirrors the actual
    bug - a frontend import flow that blanket-assigns one chosen product
    to every slide, including a non-primary "story" slide that doesn't
    actually show it. Two real, distinct (decodable) JPEGs, both slides
    carrying a current ProductAppearance for the same product.
    """
    from PIL import Image

    product = Product(display_name="Sunrise Orange Juice")
    db_session.add(product)
    db_session.flush()

    slideshow = Slideshow(imported_at=datetime.now(timezone.utc))
    db_session.add(slideshow)
    db_session.flush()

    slides = []
    for i, color in enumerate([(210, 160, 120), (80, 140, 90)]):
        image_path = tmp_path / f"slide-{i}.jpg"
        Image.new("RGB", (400, 400), color=color).save(image_path)
        slide = Slide(
            slideshow_id=slideshow.id,
            slide_index=i,
            stored_file_path=str(image_path),
            original_filename=f"slide-{i}.jpg",
            source_type="local_file",
            source_locator=f"slide-{i}.jpg",
        )
        db_session.add(slide)
        db_session.flush()
        db_session.add(
            ProductAppearance(
                slide_id=slide.id, product_id=product.id, prominence="primary", confidence=1.0, is_current=True
            )
        )
        slides.append(slide)
    db_session.commit()
    for slide in slides:
        db_session.refresh(slide)
    return slideshow, product, slides


class _ByContentFakeIsolationProvider:
    """Returns distinct bounding boxes (or none) keyed by the image_bytes it receives."""

    model = "fake-isolation-model"
    provider = "openai"

    def __init__(self, boxes_by_content: dict[bytes, list[dict]]):
        self._boxes_by_content = boxes_by_content

    def isolate_product(self, image_bytes: bytes, *, usage_sink: dict | None = None) -> list[dict]:
        return self._boxes_by_content[image_bytes]


def test_non_primary_slide_with_no_product_detected_is_skipped_not_failed(db_session, tmp_path, monkeypatch):
    """
    The actual real-world bug: a non-primary "story" slide has a
    (mistakenly, or blanket-assigned) ProductAppearance, but the product
    genuinely isn't in that slide's image. This must no longer hard-fail
    the whole stage/slideshow - it should retract that slide's
    ProductAppearance and let the primary slide's own isolation succeed.
    """
    slideshow, product, slides = _make_two_slide_slideshow_with_shared_product(db_session, tmp_path)
    primary_bytes = Path(slides[0].stored_file_path).read_bytes()
    story_bytes = Path(slides[1].stored_file_path).read_bytes()

    real_box = [{"x_min": 0.1, "y_min": 0.1, "x_max": 0.9, "y_max": 0.9, "confidence": 0.95, "notes": "bottle"}]
    fake_provider = _ByContentFakeIsolationProvider({primary_bytes: real_box, story_bytes: []})
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=fake_provider),
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow)

    assert result.succeeded is True

    db_session.refresh(slides[0])
    db_session.refresh(slides[1])

    # Primary slide: real reference image persisted.
    primary_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(ProductReferenceImage.source_slide_id == slides[0].id)
        )
    )
    assert len(primary_images) == 1

    # Story slide: no reference image, and its ProductAppearance was retracted.
    story_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(ProductReferenceImage.source_slide_id == slides[1].id)
        )
    )
    assert story_images == []
    story_appearance = db_session.scalars(
        select(ProductAppearance).where(ProductAppearance.slide_id == slides[1].id)
    ).first()
    assert story_appearance.is_current is False

    # Both AnalysisRun rows should reflect success, not failure.
    runs = list(db_session.scalars(select(AnalysisRun)))
    assert len(runs) == 2
    assert all(r.status == STATUS_SUCCEEDED for r in runs)


def test_primary_slide_with_no_product_detected_is_also_skipped_not_failed(db_session, tmp_path, monkeypatch):
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md): a real TikTok
    slideshow can lead with a text-only "hook" slide (the primary slide,
    slides[0]) and show the product on a LATER slide instead - the
    primary slide has no structural claim to being the one that shows
    the product. This must succeed overall (the non-primary slide's real
    detection is enough), with the primary slide's own mistaken
    ProductAppearance retracted exactly like any other slide's.
    """
    slideshow, product, slides = _make_two_slide_slideshow_with_shared_product(db_session, tmp_path)
    primary_bytes = Path(slides[0].stored_file_path).read_bytes()
    story_bytes = Path(slides[1].stored_file_path).read_bytes()

    # No box on the primary ("hook") slide, a real box on the second
    # ("product") slide - the exact real scenario this fix targets.
    real_box = [{"x_min": 0.1, "y_min": 0.1, "x_max": 0.9, "y_max": 0.9, "confidence": 0.95, "notes": "bottle"}]
    fake_provider = _ByContentFakeIsolationProvider({primary_bytes: [], story_bytes: real_box})
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=fake_provider),
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow)

    assert result.succeeded is True

    primary_appearance = db_session.scalars(
        select(ProductAppearance).where(ProductAppearance.slide_id == slides[0].id)
    ).first()
    assert primary_appearance.is_current is False

    second_slide_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(ProductReferenceImage.source_slide_id == slides[1].id)
        )
    )
    assert len(second_slide_images) == 1


def test_fails_when_no_slide_at_all_has_a_detectable_product(db_session, tmp_path, monkeypatch):
    """The genuine, still-necessary failure case: not one slide in the whole slideshow shows the product."""
    slideshow, product, slides = _make_two_slide_slideshow_with_shared_product(db_session, tmp_path)
    primary_bytes = Path(slides[0].stored_file_path).read_bytes()
    story_bytes = Path(slides[1].stored_file_path).read_bytes()

    fake_provider = _ByContentFakeIsolationProvider({primary_bytes: [], story_bytes: []})
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=fake_provider),
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow)

    assert result.succeeded is False
    assert "No product could be detected in any slide" in result.error

    # Both appearances retracted, both AnalysisRuns still succeeded -
    # only the stage's overall result is a failure.
    for slide in slides:
        appearance = db_session.scalars(
            select(ProductAppearance).where(ProductAppearance.slide_id == slide.id)
        ).first()
        assert appearance.is_current is False
    runs = list(db_session.scalars(select(AnalysisRun)))
    assert len(runs) == 2
    assert all(r.status == STATUS_SUCCEEDED for r in runs)


def test_crop_bounding_boxes_normalizes_an_inverted_box_instead_of_crashing():
    """
    Real bug found live (see MIGRATION_PLAN.md): the isolation model
    occasionally returns y_min > y_max (or x_min > x_max) - uncorrected,
    the padded top/bottom computed from that cross each other and PIL's
    own crop() raises "Coordinate 'lower' is less than 'upper'".
    """
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (400, 400), color=(210, 160, 120))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    image_bytes = buffer.getvalue()

    inverted_box = {
        "x_min": 0.1,
        "y_min": 0.9,  # inverted - larger than y_max
        "x_max": 0.9,
        "y_max": 0.1,
        "confidence": 0.9,
        "notes": "inverted box",
    }

    crops = _crop_bounding_boxes(image_bytes, [inverted_box])

    assert len(crops) == 1
    cropped = Image.open(BytesIO(crops[0]))
    assert cropped.size[0] > 0
    assert cropped.size[1] > 0


def test_crop_bounding_boxes_still_crops_a_normal_box_correctly():
    """Same normalization logic must be a no-op for the ordinary, already-correctly-ordered case."""
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (400, 400), color=(210, 160, 120))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    image_bytes = buffer.getvalue()

    normal_box = {"x_min": 0.1, "y_min": 0.1, "x_max": 0.9, "y_max": 0.9, "confidence": 0.9, "notes": "normal"}

    crops = _crop_bounding_boxes(image_bytes, [normal_box])

    assert len(crops) == 1
    cropped = Image.open(BytesIO(crops[0]))
    # Roughly 0.8 * 400 = 320px, plus 5% padding on each side.
    assert 300 < cropped.size[0] < 360
    assert 300 < cropped.size[1] < 360


# --- Reference retirement (incident bd1f62a2) ------------------------


def test_sibling_slides_crops_survive_the_same_run(db_session):
    """
    The incident: one product across three slides produced six crops, and
    five were retired unscored because retirement ran INSIDE the per-slide
    loop. The single survivor scored 0.458 against a 0.5 floor and blocked
    generation entirely, while four never-scored candidates - including
    the largest crop - sat retired in the database.
    """
    from app.models.product_reference_image import ProductReferenceImage
    from app.slideshow_stages.product_isolation_stage import _retire_superseded_references

    rows = []
    for slide_no in (1, 2, 2, 3):
        image = ProductReferenceImage(
            product_id="p1", source_slide_id=f"slide{slide_no}",
            isolation_method="llm_bounding_box_v1", file_path="/tmp/x.jpg", is_current=True,
        )
        db_session.add(image)
        rows.append(image)
    db_session.flush()

    # Everything above came from THIS run.
    _retire_superseded_references(db_session, {"p1": [r.id for r in rows]})
    db_session.flush()
    db_session.expire_all()

    assert all(r.is_current for r in rows), "a run must not retire its own crops"


def test_a_new_run_supersedes_the_previous_runs_crops(db_session):
    """The behaviour that was intended all along, and must be preserved."""
    from app.models.product_reference_image import ProductReferenceImage
    from app.slideshow_stages.product_isolation_stage import _retire_superseded_references

    old = ProductReferenceImage(
        product_id="p2", source_slide_id="slideA", isolation_method="llm_bounding_box_v1",
        file_path="/tmp/old.jpg", is_current=True,
    )
    new = ProductReferenceImage(
        product_id="p2", source_slide_id="slideA", isolation_method="llm_bounding_box_v1",
        file_path="/tmp/new.jpg", is_current=True,
    )
    db_session.add_all([old, new])
    db_session.flush()

    _retire_superseded_references(db_session, {"p2": [new.id]})
    db_session.flush()
    db_session.expire_all()  # bulk UPDATE(synchronize_session=False)

    assert not old.is_current, "the previous run's crop should be superseded"
    assert new.is_current


def test_product_url_and_uploaded_references_are_never_retired(db_session):
    """
    Only slideshow crops are superseded by a new isolation pass. A clean
    product-URL image or a hand-uploaded reference is not this stage's to
    invalidate - and destroying them is what left the reference pool
    containing nothing but slideshow crops.
    """
    from app.models.product_reference_image import ProductReferenceImage
    from app.slideshow_stages.product_isolation_stage import _retire_superseded_references

    from_url = ProductReferenceImage(
        product_id="p3", source_slide_id=None, source_product_source_import_id="imp1",
        isolation_method="product_url", file_path="/tmp/url.jpg", is_current=True,
    )
    uploaded = ProductReferenceImage(
        product_id="p3", source_slide_id=None, isolation_method="user_upload",
        file_path="/tmp/up.jpg", is_current=True,
    )
    crop = ProductReferenceImage(
        product_id="p3", source_slide_id="slideZ", isolation_method="llm_bounding_box_v1",
        file_path="/tmp/crop.jpg", is_current=True,
    )
    db_session.add_all([from_url, uploaded, crop])
    db_session.flush()

    fresh = ProductReferenceImage(
        product_id="p3", source_slide_id="slideZ", isolation_method="llm_bounding_box_v1",
        file_path="/tmp/fresh.jpg", is_current=True,
    )
    db_session.add(fresh)
    db_session.flush()

    _retire_superseded_references(db_session, {"p3": [fresh.id]})
    db_session.flush()
    db_session.expire_all()

    assert from_url.is_current, "a product-URL reference must survive isolation"
    assert uploaded.is_current, "a user upload must survive isolation"
    assert not crop.is_current, "the superseded slideshow crop should retire"


def test_no_new_crops_means_nothing_is_retired(db_session):
    """Retiring on an empty run would empty the library for no reason."""
    from app.models.product_reference_image import ProductReferenceImage
    from app.slideshow_stages.product_isolation_stage import _retire_superseded_references

    existing = ProductReferenceImage(
        product_id="p4", source_slide_id="slideQ", isolation_method="llm_bounding_box_v1",
        file_path="/tmp/e.jpg", is_current=True,
    )
    db_session.add(existing)
    db_session.flush()

    _retire_superseded_references(db_session, {"p4": []})
    db_session.flush()
    db_session.expire_all()
    assert existing.is_current
