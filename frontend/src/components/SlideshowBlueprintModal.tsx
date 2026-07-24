import { useEffect, useState } from 'react';
import {
  api,
  type AssembledSlideshowBlueprint,
  type CreativityLevel,
  type GenerateCreativeResponseData,
  type GeneratedImageData,
  type GenerationAttemptData,
  type GenerationCandidateData,
  type GenerationReferenceSet,
  type ImageValidationResultData,
  type ProductReferenceImage,
  type QualityMode,
  type TextStrategy,
} from '../api';

interface SlideshowBlueprintModalProps {
  slideshowId: string;
  onClose: () => void;
  onChanged: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  imported: 'Imported',
  queued: 'Queued',
  analyzing: 'Analyzing…',
  ready: 'Ready',
  failed: 'Failed',
};

const STAGE_LABELS: Record<string, string> = {
  ocr: 'OCR',
  product_isolation: 'Product Isolation',
  product_lock_profile: 'Product Lock Profile',
  creative_fingerprint: 'Creative Fingerprint',
  marketing_analysis: 'Marketing Analysis',
  narrative_structure: 'Narrative Structure',
  creative_specification: 'Creative Specification',
};

const BEAT_LABELS: Record<string, string> = {
  hook: 'Hook',
  story: 'Story',
  reveal: 'Reveal',
  proof: 'Proof',
  cta: 'CTA',
  other: 'Other',
  unclassifiable: 'Unclassifiable',
};

/**
 * New-pipeline equivalent of CreativeBlueprintModal.tsx. Slide-scoped
 * sections (Product, Creative Fingerprint, OCR) read from one selected
 * slide in blueprint.slides - a Prev/Next selector when there's more
 * than one (Phase 4 - true multi-slide import, see MIGRATION_PLAN.md),
 * defaulting to the first. Slideshow-scoped sections (Marketing
 * Analysis, Creative Specification) read from blueprint directly regardless.
 * Still minimal, not a real filmstrip/carousel - that's a later phase
 * (Phase 7, frontend consolidation), not this one. Selecting a slide
 * beyond the first will show "Not generated yet" everywhere, though -
 * the Stages themselves only ever analyze the primary slide
 * (slides[0]) until Phase 5 (see Slideshow.primary_slide's docstring),
 * so there's genuinely nothing there yet, not a rendering bug.
 */
export function SlideshowBlueprintModal({ slideshowId, onClose, onChanged }: SlideshowBlueprintModalProps) {
  const [blueprint, setBlueprint] = useState<AssembledSlideshowBlueprint | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [selectedSlideIndex, setSelectedSlideIndex] = useState(0);
  // Phase 8.5 (Generation -> Validation proof of loop, see
  // MIGRATION_PLAN.md) - deliberately not part of `blueprint`: the
  // backend scopes generation/validation to the primary slide only and
  // never wires them into the analysis pipeline, so they're loaded and
  // triggered independently rather than riding the blueprint's own
  // polling/status machinery.
  const [generatedImage, setGeneratedImage] = useState<GeneratedImageData | null>(null);
  const [validationResult, setValidationResult] = useState<ImageValidationResultData | null>(null);
  // Phase 10.2-10.9 of AI Creative Engine vNext (see MIGRATION_PLAN.md's
  // ADR §11-§15) - the Decision -> Generation -> Quality retry loop,
  // deliberately separate from the Phase 8 single-shot fields above:
  // generate-creative is a different, newer endpoint (real money, N
  // candidates, real retries), not a replacement for Generate Image.
  const [qualityMode, setQualityMode] = useState<QualityMode>('fast');
  const [creativityLevel, setCreativityLevel] = useState<CreativityLevel>('conservative');
  // undefined = the classic behavior (the model renders text itself) -
  // a real, deliberate distinct choice from the explicit 'no_text'
  // strategy, not the same "no text" outcome. See GenerationPlan.
  // text_strategy's own docstring in decision_engine.py.
  const [textStrategy, setTextStrategy] = useState<TextStrategy | ''>('');
  // Phase 11.4 (see MIGRATION_PLAN.md) - a real gap the Phase 11 audit
  // found: when a slide has 2+ current products, generate-creative
  // silently targets whichever one the backend's own
  // resolve_primary_appearance resolves to (prominence == "primary",
  // ties broken by earliest-created) unless bundle_members is given -
  // that choice was completely invisible in the UI. Defaults are
  // recomputed below whenever the primary slide's product set changes,
  // matching the backend's exact default so a slide with only one
  // product (the overwhelmingly common case) behaves identically to
  // before this phase - no bundle_members sent unless the user
  // explicitly selects 2+ products.
  const [selectedBundleProductIds, setSelectedBundleProductIds] = useState<string[]>([]);
  const [bundleRoles, setBundleRoles] = useState<Record<string, string>>({});
  const [generateCreativeResult, setGenerateCreativeResult] =
    useState<GenerateCreativeResponseData | null>(null);
  // Phase 11.2 (see MIGRATION_PLAN.md) - every persisted attempt for this
  // slide, independent of `generateCreativeResult` above (which only ever
  // holds the single most recent in-memory response, lost on modal close/
  // page reload). Loaded whenever the primary slide is known, and
  // refreshed after a new generate-creative call so it never goes stale.
  const [generationHistory, setGenerationHistory] = useState<GenerationAttemptData[]>([]);
  // Phase 9.5 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §9) - the
  // Canonical Reference Library is compute-on-read (never part of
  // `blueprint`), keyed by product_id since a slide can carry 2+
  // products, each with its own independent Library.
  const [referenceLibraries, setReferenceLibraries] = useState<Record<string, ProductReferenceImage[]>>(
    {}
  );
  // Which product's Library is currently being (re-)scored, if any -
  // score-references is a background task (202) with no direct
  // completion signal, so "scoring" here just means "within the fixed
  // polling window below", not a real server-reported status.
  const [scoringProductId, setScoringProductId] = useState<string | null>(null);
  // Phase 9.6 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §4/§8/§9)
  // - which product is currently mid-upload, and which specific image is
  // mid a manual library-status write, so only that image's/product's
  // controls show a busy state rather than disabling the whole panel.
  const [uploadingProductId, setUploadingProductId] = useState<string | null>(null);
  const [updatingLibraryStatusId, setUpdatingLibraryStatusId] = useState<string | null>(null);
  // Phase 9.5 - which real Library images fed the current
  // GeneratedImage, for the "reference images used" strip.
  const [referenceSet, setReferenceSet] = useState<GenerationReferenceSet | null>(null);

  const load = () => {
    api
      .getSlideshowBlueprint(slideshowId)
      .then(setBlueprint)
      .catch((err) => setError((err as Error).message));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slideshowId]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleAnalyzeAll = async () => {
    setBusyAction('__all__');
    setError(null);
    try {
      // analyzeSlideshow now returns immediately once status flips to
      // "queued" (Phase 3.2 - see MIGRATION_PLAN.md) rather than the
      // finished blueprint, so re-fetch to pick up that status; the
      // polling effect below takes over from there while it's
      // queued/analyzing.
      await api.analyzeSlideshow(slideshowId);
      load();
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyAction(null);
    }
  };

  // Poll while a background analysis is in flight (Phase 3.2) - re-runs
  // whenever blueprint.status changes, so it naturally stops once the
  // pipeline reaches ready/failed.
  useEffect(() => {
    if (blueprint?.status !== 'queued' && blueprint?.status !== 'analyzing') return;
    const interval = setInterval(load, 1500);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slideshowId, blueprint?.status]);

  const handleRerun = async (stageName: string) => {
    setBusyAction(stageName);
    setError(null);
    try {
      // Same reasoning as handleAnalyzeAll (Phase 3.3 - mirrors 3.2):
      // rerunSlideshowStage now returns immediately once status flips to
      // "queued", so re-fetch instead of trusting the response body -
      // the polling effect above (already generic, not tied to which
      // action triggered it) takes over from there.
      await api.rerunSlideshowStage(slideshowId, stageName);
      load();
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyAction(null);
    }
  };

  const clampedSlideIndex = blueprint
    ? Math.min(selectedSlideIndex, blueprint.slides.length - 1)
    : 0;
  const slide = blueprint?.slides[clampedSlideIndex];
  const runInFlight = blueprint?.status === 'queued' || blueprint?.status === 'analyzing';
  const currentBeat = slide
    ? blueprint?.narrative_structure?.structured.slides.find((s) => s.slide_id === slide.id)?.beat
    : undefined;

  // Generation is scoped to the primary slide only (Phase 8's "one slide
  // first" boundary, enforced by the backend) - independent of whichever
  // slide the Prev/Next selector above is currently showing.
  const primarySlideId = blueprint?.slides[0]?.id;
  const primarySlideProducts = blueprint?.slides[0]?.products;
  const primarySlideProductIdsKey = primarySlideProducts
    ?.map((p) => p.appearance.product_id)
    .join(',');

  // Phase 11.4 - defaults to exactly what the backend's own
  // resolve_primary_appearance would pick when bundle_members is
  // omitted (prominence == "primary", ties broken by earliest-created),
  // so a slide with only one product sends nothing different than
  // before this phase - selecting 2+ is what actually opts into Bundle
  // Composition.
  useEffect(() => {
    if (!primarySlideProducts || primarySlideProducts.length === 0) {
      setSelectedBundleProductIds([]);
      setBundleRoles({});
      return;
    }
    const primaryMarked = primarySlideProducts.filter(
      (p) => p.appearance.prominence === 'primary'
    );
    const candidates = primaryMarked.length > 0 ? primaryMarked : primarySlideProducts;
    const earliest = candidates.reduce((a, b) => {
      if (a.appearance.created_at !== b.appearance.created_at) {
        return a.appearance.created_at < b.appearance.created_at ? a : b;
      }
      return a.appearance.id < b.appearance.id ? a : b;
    });
    setSelectedBundleProductIds([earliest.appearance.product_id]);
    setBundleRoles(
      Object.fromEntries(
        primarySlideProducts.map((p) => [
          p.appearance.product_id,
          p.appearance.product?.display_name ?? p.appearance.product_id,
        ])
      )
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [primarySlideId, primarySlideProductIdsKey]);

  const toggleBundleProduct = (productId: string) => {
    setSelectedBundleProductIds((prev) =>
      prev.includes(productId) ? prev.filter((id) => id !== productId) : [...prev, productId]
    );
  };

  useEffect(() => {
    if (!primarySlideId) return;
    setGeneratedImage(null);
    setValidationResult(null);
    api
      .getCurrentGeneratedImage(slideshowId, primarySlideId)
      .then(setGeneratedImage)
      .catch((err) => setError((err as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slideshowId, primarySlideId]);

  const loadGenerationHistory = () => {
    if (!primarySlideId) return;
    api
      .listGenerationAttempts(slideshowId, primarySlideId)
      .then(setGenerationHistory)
      .catch((err) => setError((err as Error).message));
  };

  useEffect(() => {
    loadGenerationHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slideshowId, primarySlideId]);

  useEffect(() => {
    if (!generatedImage) {
      setValidationResult(null);
      return;
    }
    api
      .getCurrentValidationResult(slideshowId, generatedImage.id)
      .then(setValidationResult)
      .catch((err) => setError((err as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slideshowId, generatedImage?.id]);

  // Phase 9.5 - "reference images used" strip's data source.
  useEffect(() => {
    if (!generatedImage) {
      setReferenceSet(null);
      return;
    }
    api
      .getGenerationReferenceSet(slideshowId, generatedImage.id)
      .then(setReferenceSet)
      .catch((err) => setError((err as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slideshowId, generatedImage?.id]);

  // Phase 9.5 - loads each current product's reference images whenever
  // the selected slide's product set changes.
  //
  // Phase 11.5 (see MIGRATION_PLAN.md) - switched from getReferenceLibrary
  // (library_status="included" only) to listReferenceImages (every current
  // image, any status) - a real gap the Phase 11 audit found: an unscored
  // upload, a rejected candidate, or a superseded image were all
  // completely invisible in the UI before this, with no way to review or
  // manually include one. ReferenceLibraryPanel itself now renders every
  // status, not just the Library subset.
  useEffect(() => {
    if (!slide) return;
    slide.products.forEach((product) => {
      const productId = product.appearance.product_id;
      api
        .listReferenceImages(productId)
        .then((images) => setReferenceLibraries((prev) => ({ ...prev, [productId]: images })))
        .catch((err) => setError((err as Error).message));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slide?.id]);

  const handleScoreReferences = async (productId: string) => {
    setError(null);
    try {
      await api.scoreReferences(productId);
      setScoringProductId(productId);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  // Fixed polling window rather than a real status check - the
  // score-references endpoint (Phase 9.2, see MIGRATION_PLAN.md) is a
  // fire-and-forget background task with no completion signal to poll
  // against, unlike blueprint analysis's queued/analyzing status.
  useEffect(() => {
    if (!scoringProductId) return;
    let attempts = 0;
    const interval = setInterval(() => {
      attempts += 1;
      api
        .listReferenceImages(scoringProductId)
        .then((images) =>
          setReferenceLibraries((prev) => ({ ...prev, [scoringProductId]: images }))
        )
        .catch((err) => setError((err as Error).message))
        .finally(() => {
          if (attempts >= 8) setScoringProductId(null);
        });
    }, 1500);
    return () => clearInterval(interval);
  }, [scoringProductId]);

  const handleUploadReferenceImage = async (productId: string, file: File) => {
    setUploadingProductId(productId);
    setError(null);
    try {
      await api.uploadReferenceImage(productId, file);
      // Phase 11.5 - an unscored candidate won't appear in the Library
      // proper (library_status="included") until Score References runs,
      // but it's a real current image now, so re-fetch the full list
      // (every status) rather than leaving it invisible until scored.
      const images = await api.listReferenceImages(productId);
      setReferenceLibraries((prev) => ({ ...prev, [productId]: images }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploadingProductId(null);
    }
  };

  const handleUpdateLibraryStatus = async (
    productId: string,
    referenceImageId: string,
    status: 'included' | 'rejected' | 'superseded'
  ) => {
    setUpdatingLibraryStatusId(referenceImageId);
    setError(null);
    try {
      await api.updateLibraryStatus(productId, referenceImageId, status);
      const images = await api.listReferenceImages(productId);
      setReferenceLibraries((prev) => ({ ...prev, [productId]: images }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUpdatingLibraryStatusId(null);
    }
  };

  // Phase 11.5 - the manual role override, mirroring
  // handleUpdateLibraryStatus exactly.
  const handleUpdateReferenceImageRole = async (
    productId: string,
    referenceImageId: string,
    role: string
  ) => {
    setUpdatingLibraryStatusId(referenceImageId);
    setError(null);
    try {
      await api.updateReferenceImageRole(productId, referenceImageId, role);
      const images = await api.listReferenceImages(productId);
      setReferenceLibraries((prev) => ({ ...prev, [productId]: images }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUpdatingLibraryStatusId(null);
    }
  };

  const handleGenerateImage = async () => {
    if (!primarySlideId) return;
    setBusyAction('generate_image');
    setError(null);
    try {
      const image = await api.generateImage(slideshowId, primarySlideId);
      setGeneratedImage(image);
      setValidationResult(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyAction(null);
    }
  };

  const handleValidateImage = async () => {
    if (!generatedImage) return;
    setBusyAction('validate_image');
    setError(null);
    try {
      setValidationResult(await api.validateGeneratedImage(slideshowId, generatedImage.id));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyAction(null);
    }
  };

  // Phase 10.2-10.9 (see MIGRATION_PLAN.md's vNext ADR §11-§15) - real,
  // paid provider calls (up to several candidates per attempt, up to
  // several retries), only ever spent when the user explicitly clicks
  // this button - never automatic, never part of any polling/analyze flow.
  const handleGenerateCreative = async () => {
    if (!primarySlideId) return;
    setBusyAction('generate_creative');
    setError(null);
    try {
      const result = await api.generateCreative(slideshowId, primarySlideId, {
        quality_mode: qualityMode,
        creativity_level: creativityLevel,
        ...(textStrategy ? { text_strategy: textStrategy } : {}),
        // Phase 11.4 - only sent when the user has explicitly selected
        // 2+ products (Bundle Composition); a single selection matches
        // the backend's own resolve_primary_appearance default, so
        // omitting bundle_members there preserves prior behavior exactly.
        ...(selectedBundleProductIds.length > 1
          ? {
              bundle_members: selectedBundleProductIds.map((productId) => ({
                product_id: productId,
                role_in_scene: bundleRoles[productId]?.trim() || productId,
              })),
            }
          : {}),
      });
      setGenerateCreativeResult(result);
      loadGenerationHistory();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyAction(null);
    }
  };

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="blueprint-backdrop" onClick={onClose}>
      <div className="blueprint-modal" onClick={(e) => e.stopPropagation()}>
        <button className="blueprint-close" onClick={onClose} aria-label="Close">
          ×
        </button>

        {error && <p className="error">{error}</p>}

        {blueprint === null || slide === undefined ? (
          <p>Loading Slideshow Blueprint…</p>
        ) : (
          <>
            {/*
              Discoverability fix, found live during Phase 11 (see
              MIGRATION_PLAN.md): this modal renders ~7800px tall once
              every section below has real content - the Generate
              Creative controls sat at the very bottom, reachable but
              never actually found by a real user scrolling through
              Product Lock Profile/Reference Library/Creative
              Fingerprint/Marketing Analysis/Narrative Structure/OCR/
              Creative Specification/the legacy Generated Image section
              first, with nothing indicating there was more below.
              Plain `<a href="#...">` was tried first and live-verified
              NOT to work here: hash-navigation only reliably scrolls
              the document's own scrolling element, and this modal's
              scroll container is a nested `.blueprint-backdrop` div,
              not the document - confirmed live (scrollTop stayed near
              0 after a real click). `scrollIntoView` on the target
              element is what's actually reliable within a nested
              scroll container. A sticky jump-nav, not a redesign -
              every section keeps its existing order and content
              unchanged.
            */}
            <nav className="blueprint-jump-nav" aria-label="Jump to section">
              {[
                ['section-products', 'Products'],
                ['section-creative-fingerprint', 'Fingerprint'],
                ['section-marketing-analysis', 'Marketing'],
                ['section-narrative-structure', 'Narrative'],
                ['section-ocr', 'OCR'],
                ['section-creative-specification', 'Spec'],
                ['section-generated-image', 'Generated Image'],
              ].map(([id, label]) => (
                <button key={id} type="button" onClick={() => scrollToSection(id)}>
                  {label}
                </button>
              ))}
              <button
                type="button"
                className="blueprint-jump-nav-primary"
                onClick={() => scrollToSection('section-generate-creative')}
              >
                Generate Creative
              </button>
            </nav>

            <header className="blueprint-header">
              <img
                src={api.slideFileUrl(blueprint.id, slide.id)}
                alt={slide.original_filename}
                className="blueprint-hero-image"
              />
              <div className="blueprint-header-info">
                <h2>{slide.original_filename}</h2>
                <span className={`status-badge status-${blueprint.status}`}>
                  {STATUS_LABELS[blueprint.status] ?? blueprint.status}
                </span>
                {slide.products.length > 0 && (
                  <p className="blueprint-meta">
                    {slide.products.length > 1 ? 'Products' : 'Product'}:{' '}
                    {slide.products
                      .map((p) => p.appearance.product?.display_name ?? p.appearance.product_id)
                      .join(', ')}
                  </p>
                )}
                <p className="blueprint-meta">
                  Imported {new Date(blueprint.imported_at).toLocaleString()} via{' '}
                  {slide.source_type}
                </p>
                <button
                  className="analyze-all-button"
                  onClick={handleAnalyzeAll}
                  disabled={busyAction !== null || runInFlight}
                >
                  {busyAction === '__all__' || runInFlight ? 'Analyzing…' : 'Analyze / Re-run All'}
                </button>
              </div>
            </header>

            {blueprint.slides.length > 1 && (
              <div className="slide-selector">
                <button
                  onClick={() => setSelectedSlideIndex((i) => Math.max(0, i - 1))}
                  disabled={clampedSlideIndex === 0}
                >
                  ← Prev
                </button>
                <span>
                  Slide {clampedSlideIndex + 1} of {blueprint.slides.length}
                  {currentBeat && (
                    <span className="beat-badge">{BEAT_LABELS[currentBeat] ?? currentBeat}</span>
                  )}
                </span>
                <button
                  onClick={() =>
                    setSelectedSlideIndex((i) => Math.min(blueprint.slides.length - 1, i + 1))
                  }
                  disabled={clampedSlideIndex === blueprint.slides.length - 1}
                >
                  Next →
                </button>
              </div>
            )}

            {blueprint.status === 'failed' && blueprint.failed_stage && (
              <div className="blueprint-failure-banner">
                <strong>{STAGE_LABELS[blueprint.failed_stage] ?? blueprint.failed_stage} failed.</strong>{' '}
                {blueprint.failed_stage_error}
              </div>
            )}

            <section className="blueprint-section" id="section-products">
              <div className="blueprint-section-header">
                <h3>Products</h3>
                <div className="blueprint-section-actions">
                  <button
                    className="rerun-button secondary"
                    onClick={() => handleRerun('product_isolation')}
                    disabled={busyAction !== null || runInFlight}
                  >
                    {busyAction === 'product_isolation' ? 'Re-cropping…' : 'Re-crop product image'}
                  </button>
                  <button
                    className="rerun-button"
                    onClick={() => handleRerun('product_lock_profile')}
                    disabled={busyAction !== null || runInFlight}
                  >
                    {busyAction === 'product_lock_profile' ? 'Working…' : 'Regenerate profile'}
                  </button>
                </div>
              </div>
              {/*
                Phase 6.2 (see MIGRATION_PLAN.md): both stages above
                reject a slide with 2+ distinct current products outright
                rather than guessing which one to isolate/profile - that
                failure surfaces here exactly like any other stage
                failure, not as a special case.
              */}
              {(blueprint.failed_stage === 'product_isolation' ||
                blueprint.failed_stage === 'product_lock_profile') && (
                <p className="section-error">{blueprint.failed_stage_error}</p>
              )}
              {slide.products.length === 0 ? (
                <p className="empty-state">No product assigned yet.</p>
              ) : (
                slide.products.map((product) => (
                  <div key={product.appearance.id} className="product-subsection">
                    <h4 className="product-subsection-title">
                      {product.appearance.product?.display_name ?? product.appearance.product_id}
                      {product.appearance.prominence === 'primary' && (
                        <span className="prominence-badge">primary</span>
                      )}
                    </h4>
                    {product.product_reference_images.length > 0 && (
                      <div className="reference-images-row">
                        {product.product_reference_images.map((img) => (
                          <img
                            key={img.id}
                            src={api.referenceImageFileUrl(product.appearance.product_id, img.id)}
                            alt="Product reference"
                            className="reference-image-thumbnail"
                          />
                        ))}
                      </div>
                    )}
                    {product.product_lock_profile ? (
                      <>
                        <StaleBadge
                          isStale={product.product_lock_profile.is_stale}
                          staleBecause={product.product_lock_profile.stale_because}
                        />
                        <ProductLockProfileFields structured={product.product_lock_profile.structured} />
                      </>
                    ) : (
                      <p className="empty-state">Lock Profile not generated yet.</p>
                    )}
                    <ReferenceLibraryPanel
                      images={referenceLibraries[product.appearance.product_id]}
                      productId={product.appearance.product_id}
                      onScore={() => handleScoreReferences(product.appearance.product_id)}
                      scoring={scoringProductId === product.appearance.product_id}
                      onUpload={(file) => handleUploadReferenceImage(product.appearance.product_id, file)}
                      uploading={uploadingProductId === product.appearance.product_id}
                      onUpdateStatus={(imageId, status) =>
                        handleUpdateLibraryStatus(product.appearance.product_id, imageId, status)
                      }
                      onUpdateRole={(imageId, role) =>
                        handleUpdateReferenceImageRole(product.appearance.product_id, imageId, role)
                      }
                      updatingStatusId={updatingLibraryStatusId}
                    />
                  </div>
                ))
              )}
            </section>

            <BlueprintSection
              id="section-creative-fingerprint"
              title="Creative Fingerprint"
              generated={slide.creative_fingerprint !== null}
              failed={blueprint.failed_stage === 'creative_fingerprint'}
              error={blueprint.failed_stage === 'creative_fingerprint' ? blueprint.failed_stage_error : null}
              rerunLabel="Regenerate fingerprint"
              onRerun={() => handleRerun('creative_fingerprint')}
              busy={busyAction === 'creative_fingerprint' || runInFlight}
              isStale={slide.creative_fingerprint?.is_stale}
              staleBecause={slide.creative_fingerprint?.stale_because}
            >
              {slide.creative_fingerprint && (
                <CreativeFingerprintFields structured={slide.creative_fingerprint.structured} />
              )}
            </BlueprintSection>

            <BlueprintSection
              id="section-marketing-analysis"
              title="Marketing Analysis"
              generated={blueprint.marketing_analysis !== null}
              failed={blueprint.failed_stage === 'marketing_analysis'}
              error={blueprint.failed_stage === 'marketing_analysis' ? blueprint.failed_stage_error : null}
              rerunLabel="Regenerate analysis"
              onRerun={() => handleRerun('marketing_analysis')}
              busy={busyAction === 'marketing_analysis' || runInFlight}
              isStale={blueprint.marketing_analysis?.is_stale}
              staleBecause={blueprint.marketing_analysis?.stale_because}
            >
              {blueprint.marketing_analysis && (
                <p className="narrative-text">{blueprint.marketing_analysis.narrative_text}</p>
              )}
            </BlueprintSection>

            <BlueprintSection
              id="section-narrative-structure"
              title="Narrative Structure"
              generated={blueprint.narrative_structure !== null}
              failed={blueprint.failed_stage === 'narrative_structure'}
              error={blueprint.failed_stage === 'narrative_structure' ? blueprint.failed_stage_error : null}
              rerunLabel="Regenerate structure"
              onRerun={() => handleRerun('narrative_structure')}
              busy={busyAction === 'narrative_structure' || runInFlight}
              isStale={blueprint.narrative_structure?.is_stale}
              staleBecause={blueprint.narrative_structure?.stale_because}
            >
              {blueprint.narrative_structure && (
                <>
                  <p className="narrative-text">{blueprint.narrative_structure.structured.arc_summary}</p>
                  <ul className="narrative-beat-list">
                    {blueprint.narrative_structure.structured.slides.map((s) => (
                      <li key={s.slide_id} className={s.slide_id === slide.id ? 'current-slide-beat' : undefined}>
                        <span className="field-label">Slide {s.slide_index + 1}</span>
                        <span className="beat-badge">{BEAT_LABELS[s.beat] ?? s.beat}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </BlueprintSection>

            <BlueprintSection
              id="section-ocr"
              title="OCR Text"
              generated={slide.ocr_result !== null}
              failed={blueprint.failed_stage === 'ocr'}
              error={blueprint.failed_stage === 'ocr' ? blueprint.failed_stage_error : null}
              rerunLabel="Re-run OCR"
              onRerun={() => handleRerun('ocr')}
              busy={busyAction === 'ocr' || runInFlight}
            >
              {slide.ocr_result && (
                <>
                  <p className="narrative-text">{slide.ocr_result.raw_text}</p>
                  {slide.ocr_result.structured_blocks.length > 0 && (
                    <table className="blocks-table">
                      <tbody>
                        {slide.ocr_result.structured_blocks.map((block, i) => (
                          <tr key={i}>
                            <td className="blocks-role">{String(block.role)}</td>
                            <td>{String(block.text)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              )}
            </BlueprintSection>

            <BlueprintSection
              id="section-creative-specification"
              title="Creative Specification"
              generated={blueprint.creative_specification !== null}
              failed={blueprint.failed_stage === 'creative_specification'}
              error={blueprint.failed_stage === 'creative_specification' ? blueprint.failed_stage_error : null}
              rerunLabel="Regenerate specification"
              onRerun={() => handleRerun('creative_specification')}
              busy={busyAction === 'creative_specification' || runInFlight}
              isStale={blueprint.creative_specification?.is_stale}
              staleBecause={blueprint.creative_specification?.stale_because}
              extraAction={
                blueprint.creative_specification ? (
                  <CopyJsonButton data={blueprint.creative_specification.structured} />
                ) : undefined
              }
            >
              {blueprint.creative_specification && (
                <CreativeSpecificationFields structured={blueprint.creative_specification.structured} />
              )}
            </BlueprintSection>

            <section className="blueprint-section" id="section-generated-image">
              <div className="blueprint-section-header">
                <h3>Generated Image</h3>
                <div className="blueprint-section-actions">
                  <button
                    className="rerun-button"
                    onClick={handleGenerateImage}
                    disabled={busyAction !== null || runInFlight || !primarySlideId}
                  >
                    {busyAction === 'generate_image'
                      ? 'Generating…'
                      : generatedImage
                        ? 'Regenerate Image'
                        : 'Generate Image'}
                  </button>
                  {generatedImage && (
                    <button
                      className="rerun-button secondary"
                      onClick={handleValidateImage}
                      disabled={busyAction !== null || runInFlight}
                    >
                      {busyAction === 'validate_image' ? 'Validating…' : 'Validate'}
                    </button>
                  )}
                </div>
              </div>
              <p className="blueprint-meta">
                Proof-of-loop, Phase 8 (see MIGRATION_PLAN.md) - always the primary slide, regardless
                of which slide is shown above.
              </p>
              {!generatedImage ? (
                <p className="empty-state">Not generated yet.</p>
              ) : (
                <div className="generated-image-panel">
                  <img
                    src={api.generatedImageFileUrl(blueprint.id, generatedImage.id)}
                    alt="AI-generated recreation"
                    className="generated-image-preview"
                  />
                  <div className="generated-image-meta">
                    <p className="blueprint-meta">
                      {generatedImage.provider} / {generatedImage.model_name} ·{' '}
                      {generatedImage.generation_time_seconds.toFixed(1)}s
                      {generatedImage.seed && ` · seed ${generatedImage.seed}`}
                    </p>
                    {referenceSet && referenceSet.images.length > 0 && (
                      <div className="reference-set-strip">
                        <p className="field-list-label">Reference images used</p>
                        <div className="reference-images-row">
                          {referenceSet.images.map((img) => (
                            <img
                              key={img.product_reference_image_id}
                              src={api.referenceImageFileUrl(img.product_id, img.product_reference_image_id)}
                              alt={img.role ?? 'Reference'}
                              title={img.role ?? undefined}
                              className="reference-image-thumbnail"
                            />
                          ))}
                        </div>
                      </div>
                    )}
                    {validationResult ? (
                      <ValidationResultPanel result={validationResult} />
                    ) : (
                      <p className="empty-state">Not validated yet.</p>
                    )}
                  </div>
                </div>
              )}
            </section>

            <section className="blueprint-section" id="section-generate-creative">
              <div className="blueprint-section-header">
                <h3>Generate Creative</h3>
              </div>
              <p className="blueprint-meta">
                Phase 10.2-10.9 (see MIGRATION_PLAN.md's vNext ADR §11-§15) - the full
                Decision → Generation → Quality retry loop: N candidates, real Product
                Fidelity + Photorealism validation, an automatically-picked winner. Every
                candidate is a real, paid provider call - always the primary slide.
              </p>
              <div className="generate-creative-controls">
                <label className="generate-creative-field">
                  Quality mode
                  <select
                    value={qualityMode}
                    onChange={(e) => setQualityMode(e.target.value as QualityMode)}
                    disabled={busyAction !== null}
                  >
                    <option value="fast">Fast (1 candidate)</option>
                    <option value="balanced">Balanced (3 candidates)</option>
                    <option value="maximum">Maximum Quality (5 candidates)</option>
                  </select>
                </label>
                <label className="generate-creative-field">
                  Creativity
                  <select
                    value={creativityLevel}
                    onChange={(e) => setCreativityLevel(e.target.value as CreativityLevel)}
                    disabled={busyAction !== null}
                  >
                    <option value="conservative">Conservative</option>
                    <option value="bold">Bold</option>
                  </select>
                </label>
                <label className="generate-creative-field">
                  Marketing text
                  <select
                    value={textStrategy}
                    onChange={(e) => setTextStrategy(e.target.value as TextStrategy | '')}
                    disabled={busyAction !== null}
                  >
                    <option value="">Classic (model renders text)</option>
                    <option value="no_text">No text overlay</option>
                    <option value="reuse_original">Reuse original text &amp; position</option>
                    <option value="ai_rewrite">AI-rewritten text</option>
                  </select>
                </label>
                <button
                  className="rerun-button"
                  onClick={handleGenerateCreative}
                  disabled={busyAction !== null || runInFlight || !primarySlideId}
                >
                  {busyAction === 'generate_creative' ? 'Generating…' : 'Generate Creative'}
                </button>
              </div>
              {primarySlideProducts && primarySlideProducts.length > 1 && (
                <div className="bundle-product-picker">
                  <p className="blueprint-meta">
                    This slide has multiple current products. By default only one is used
                    (whichever the backend would pick automatically). Select 2 or more to
                    generate a Bundle Composition scene instead.
                  </p>
                  {primarySlideProducts.map((product) => {
                    const productId = product.appearance.product_id;
                    const checked = selectedBundleProductIds.includes(productId);
                    return (
                      <div className="bundle-product-row" key={productId}>
                        <label className="bundle-product-checkbox">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleBundleProduct(productId)}
                            disabled={busyAction !== null}
                          />
                          {product.appearance.product?.display_name ?? productId}
                        </label>
                        {checked && selectedBundleProductIds.length > 1 && (
                          <input
                            type="text"
                            className="bundle-product-role"
                            placeholder="Role in scene"
                            value={bundleRoles[productId] ?? ''}
                            onChange={(e) =>
                              setBundleRoles((prev) => ({ ...prev, [productId]: e.target.value }))
                            }
                            disabled={busyAction !== null}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {generateCreativeResult && (
                <GenerateCreativeResultsPanel
                  slideshowId={slideshowId}
                  result={generateCreativeResult}
                />
              )}
              {generationHistory.length > 0 && (
                <GenerationHistoryPanel slideshowId={slideshowId} attempts={generationHistory} />
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function BlueprintSection({
  id,
  title,
  generated,
  failed,
  error,
  rerunLabel,
  onRerun,
  busy,
  extraAction,
  isStale,
  staleBecause,
  children,
}: {
  id: string;
  title: string;
  generated: boolean;
  failed: boolean;
  error?: string | null;
  rerunLabel: string;
  onRerun: () => void;
  busy: boolean;
  extraAction?: React.ReactNode;
  isStale?: boolean;
  staleBecause?: string[];
  children?: React.ReactNode;
}) {
  return (
    <section className="blueprint-section" id={id}>
      <div className="blueprint-section-header">
        <h3>
          {title}
          {generated && <StaleBadge isStale={isStale} staleBecause={staleBecause} />}
        </h3>
        <div className="blueprint-section-actions">
          {extraAction}
          <button className="rerun-button" onClick={onRerun} disabled={busy}>
            {busy ? 'Working…' : rerunLabel}
          </button>
        </div>
      </div>
      {failed && error && <p className="section-error">{error}</p>}
      {generated ? children : !failed && <p className="empty-state">Not generated yet.</p>}
    </section>
  );
}

/**
 * Phase 7.5 (see MIGRATION_PLAN.md) - reuses the existing
 * classification-badge visual language rather than inventing a new one.
 * staleBecause names the upstream stage(s) that moved on since this
 * artifact was generated - shown as a title tooltip since the badge
 * itself has no room for prose.
 */
function StaleBadge({ isStale, staleBecause }: { isStale?: boolean; staleBecause?: string[] }) {
  if (!isStale) return null;
  const reasons = (staleBecause ?? []).map((s) => STAGE_LABELS[s] ?? s).join(', ');
  return (
    <span
      className="classification-badge stale-badge"
      title={reasons ? `Out of date since ${reasons} last ran` : 'Out of date'}
    >
      stale
    </span>
  );
}

/**
 * Phase 8.4/8.5 (Generation -> Validation proof of loop, see
 * MIGRATION_PLAN.md); gains an Identity badge in Phase 9.4 of Product
 * Lock v2 (ADR §9) - shown above the existing creative Pass/Fail, so a
 * user immediately sees *which kind* of failure occurred: "wrong
 * product" (Identity) reads completely differently from "wrong
 * lighting" (the creative Pass/Fail below it), and conflating them
 * into one badge would be a real regression from what Phase 8.5 built.
 * identity_passed===null (not false) means Stage 1 never ran - a
 * GeneratedImage from before this ADR shipped - shown as its own
 * "Not checked" state, never silently rendered as a pass or a fail.
 * field_checks is still rendered directly, one row per field with its
 * own preserved/violated state and reason - this *is* the "explain why
 * it failed" the user asked for, never summarized away into just a
 * badge.
 */
function ValidationResultPanel({ result }: { result: ImageValidationResultData }) {
  return (
    <div className="validation-result-panel">
      <div className="validation-badge-row">
        <span
          className={`validation-badge identity-badge ${
            result.identity_passed === null
              ? 'validation-unknown'
              : result.identity_passed
                ? 'validation-pass'
                : 'validation-fail'
          }`}
          title="Does the generated image faithfully preserve the real product's visual identity?"
        >
          Identity:{' '}
          {result.identity_passed === null ? 'Not checked' : result.identity_passed ? 'Pass' : 'Fail'}
        </span>
        <span className={`validation-badge ${result.passed ? 'validation-pass' : 'validation-fail'}`}>
          Creative: {result.passed ? 'Pass' : 'Fail'}
        </span>
      </div>
      {result.identity_checks && result.identity_checks.length > 0 && (
        <>
          <p className="field-list-label">Identity checks</p>
          <ul className="field-check-list">
            {result.identity_checks.map((check, i) => (
              <li key={i} className={check.preserved ? 'field-check-preserved' : 'field-check-violated'}>
                <span className="field-check-icon">{check.preserved ? '✓' : '✗'}</span>
                <div>
                  <span className="field-label">{check.field_name}</span>
                  <p className="field-check-reason">{check.reason}</p>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="narrative-text">{result.overall_explanation}</p>
      {result.field_checks.length > 0 && (
        <>
          <p className="field-list-label">Creative checks</p>
          <ul className="field-check-list">
            {result.field_checks.map((check, i) => (
              <li key={i} className={check.preserved ? 'field-check-preserved' : 'field-check-violated'}>
                <span className="field-check-icon">{check.preserved ? '✓' : '✗'}</span>
                <div>
                  <span className="field-label">{check.field_name}</span>
                  <p className="field-check-reason">{check.reason}</p>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/**
 * Phase 10.2-10.9 of AI Creative Engine vNext (see MIGRATION_PLAN.md's
 * ADR §11-§15) - every attempt the retry loop made, not just the
 * winner, so a user can see the whole loop's reasoning (which
 * candidates it tried, why each was accepted/rejected), not just the
 * final pick. `winner` null means no candidate across every attempt
 * was accepted within the retry limit - a real, honest outcome,
 * rendered as its own state, never silently hidden.
 */
function GenerateCreativeResultsPanel({
  slideshowId,
  result,
}: {
  slideshowId: string;
  result: GenerateCreativeResponseData;
}) {
  return (
    <div className="generate-creative-results">
      {result.winner ? (
        <p className="generate-creative-outcome generate-creative-outcome-winner">
          ✓ A candidate was accepted.
        </p>
      ) : (
        <p className="generate-creative-outcome generate-creative-outcome-none">
          No candidate across {result.attempts.length}{' '}
          {result.attempts.length === 1 ? 'attempt' : 'attempts'} passed validation.
        </p>
      )}

      {result.final_output && (
        <div className="final-output-panel">
          <p className="field-list-label">Final Output (composited)</p>
          <img
            src={api.finalOutputFileUrl(slideshowId, result.final_output.id)}
            alt="Composited final output"
            className="generated-image-preview"
          />
          {result.final_output.text_assets.length === 0 ? (
            <p className="blueprint-meta">No text overlay rendered.</p>
          ) : (
            <p className="blueprint-meta">
              {result.final_output.text_assets.length} text element
              {result.final_output.text_assets.length === 1 ? '' : 's'} composited.
            </p>
          )}
        </div>
      )}

      {result.attempts.map((attempt, attemptIndex) => (
        <div key={attempt.id} className="generation-attempt-panel">
          <p className="field-list-label">
            Attempt {attemptIndex + 1}
            {attempt.retry_of_generation_attempt_id ? ' (retry)' : ''}
          </p>
          <div className="generation-candidate-row">
            {attempt.candidates.map((candidate) => (
              <GenerationCandidateCard
                key={candidate.generated_image.id}
                slideshowId={slideshowId}
                candidate={candidate}
                isWinner={result.winner?.id === candidate.generated_image.id}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Phase 11.3 (see MIGRATION_PLAN.md) - a real, specific gap the Phase
 * 11 audit found: each candidate already carried its own
 * quality_assessment.photorealism inline, and a rich per-field
 * validation view (ValidationResultPanel) already existed for the
 * legacy single-shot path, but the vNext retry-loop candidates only
 * ever showed a bare accepted/rejected badge and a number - the same
 * detail existed one endpoint away and was never wired in. Click a
 * candidate to fetch and expand it, lazily and cached per candidate id
 * so re-expanding doesn't re-fetch. `getCurrentValidationResult` can
 * genuinely return null for a Bundle Composition candidate (which sets
 * quality_assessment.image_validation_result_ids, plural, instead) -
 * rendered as an honest "no single-product identity check for this
 * candidate" note, not hidden or crashed on.
 */
function GenerationCandidateCard({
  slideshowId,
  candidate,
  isWinner,
  showProvider,
}: {
  slideshowId: string;
  candidate: GenerationCandidateData;
  isWinner: boolean;
  showProvider?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [validation, setValidation] = useState<ImageValidationResultData | null | undefined>(
    undefined
  );

  const handleToggle = () => {
    setExpanded((prev) => !prev);
    if (validation === undefined) {
      api
        .getCurrentValidationResult(slideshowId, candidate.generated_image.id)
        .then(setValidation)
        .catch(() => setValidation(null));
    }
  };

  return (
    <div
      className={`generation-candidate ${isWinner ? 'generation-candidate-winner' : ''}`}
    >
      <button type="button" className="generation-candidate-toggle" onClick={handleToggle}>
        <img
          src={api.generatedImageFileUrl(slideshowId, candidate.generated_image.id)}
          alt="Candidate"
          className="generation-candidate-thumbnail"
        />
        <span
          className={`validation-badge ${
            candidate.quality_assessment.accepted ? 'validation-pass' : 'validation-fail'
          }`}
        >
          {candidate.quality_assessment.accepted ? 'Accepted' : 'Rejected'}
          {isWinner && ' · Winner'}
        </span>
        <span className="blueprint-meta">
          {showProvider && `${candidate.generated_image.provider} · `}
          Score: {candidate.quality_assessment.overall_confidence_score.toFixed(2)}
        </span>
      </button>
      {expanded && (
        <div className="generation-candidate-detail">
          {candidate.quality_assessment.photorealism && (
            <PhotorealismFields photorealism={candidate.quality_assessment.photorealism} />
          )}
          {validation === undefined ? (
            <p className="blueprint-meta">Loading validation detail…</p>
          ) : validation === null ? (
            <p className="empty-state">
              No single-product identity/creative check for this candidate (Bundle Composition
              candidates validate per-product - see the reference set instead).
            </p>
          ) : (
            <ValidationResultPanel result={validation} />
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Phase 11.3 - the Photorealism dimension's real, full field set (Phase
 * 10.3, see MIGRATION_PLAN.md's vNext ADR §13's PHOTOREALISM_SCHEMA in
 * app.services.quality_engine) - never previously rendered anywhere,
 * despite being fetched into every generate-creative response all along.
 */
function PhotorealismFields({ photorealism }: { photorealism: Record<string, unknown> }) {
  const booleanChecks: [string, string][] = [
    ['realistic_lighting', 'Realistic lighting'],
    ['believable_shadows', 'Believable shadows'],
    ['material_accuracy', 'Material accuracy'],
    ['reflections_correct', 'Reflections correct'],
    ['perspective_correct', 'Perspective correct'],
    ['object_integrity', 'Object integrity'],
  ];
  const reasons = Array.isArray(photorealism.reasons) ? (photorealism.reasons as string[]) : [];

  return (
    <div className="photorealism-panel">
      <p className="field-list-label">Photorealism</p>
      <ul className="field-check-list">
        {booleanChecks.map(([key, label]) => (
          <li
            key={key}
            className={photorealism[key] ? 'field-check-preserved' : 'field-check-violated'}
          >
            <span className="field-check-icon">{photorealism[key] ? '✓' : '✗'}</span>
            <span className="field-label">{label}</span>
          </li>
        ))}
        <li
          className={
            photorealism.ai_artefacts_detected ? 'field-check-violated' : 'field-check-preserved'
          }
        >
          <span className="field-check-icon">{photorealism.ai_artefacts_detected ? '✗' : '✓'}</span>
          <span className="field-label">
            {photorealism.ai_artefacts_detected ? 'AI artefacts detected' : 'No AI artefacts detected'}
          </span>
        </li>
      </ul>
      <p className="blueprint-meta">
        Texture: {String(photorealism.texture_quality)} · Sharpness:{' '}
        {String(photorealism.image_sharpness)} · Human anatomy:{' '}
        {String(photorealism.human_anatomy).replace('_', ' ')}
      </p>
      {reasons.length > 0 && (
        <ul className="field-check-list">
          {reasons.map((reason, i) => (
            <li key={i}>
              <p className="field-check-reason">{reason}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Phase 11.2 (see MIGRATION_PLAN.md) - the full, persisted record of
 * every generate-creative call ever made for this slide, not just the
 * single most-recent in-memory response GenerateCreativeResultsPanel
 * above shows. Reopening the blueprint modal (or reloading the page)
 * used to lose that history entirely - this reads it back from
 * GET .../generation-attempts instead. Deliberately doesn't try to
 * recompute a single global "winner" across separate calls (each
 * generate-creative call has its own independent accept/reject outcome)
 * - each candidate's own accepted/rejected badge is the honest, correct
 * unit here, not a reconstructed cross-call concept.
 */
function GenerationHistoryPanel({
  slideshowId,
  attempts,
}: {
  slideshowId: string;
  attempts: GenerationAttemptData[];
}) {
  return (
    <div className="generation-history">
      <p className="field-list-label">Generation History ({attempts.length})</p>
      {attempts.map((attempt) => (
        <div key={attempt.id} className="generation-attempt-panel">
          <p className="field-list-label">
            {attempt.quality_mode}
            {attempt.retry_of_generation_attempt_id ? ' (retry)' : ''} ·{' '}
            {new Date(attempt.created_at).toLocaleString()}
          </p>
          <div className="generation-candidate-row">
            {attempt.candidates.map((candidate) => (
              <GenerationCandidateCard
                key={candidate.generated_image.id}
                slideshowId={slideshowId}
                candidate={candidate}
                isWinner={false}
                showProvider
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Phase 9.5 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §9) - the
 * Canonical Reference Library is compute-on-read
 * (library_status="included"), so `images` is just whatever the last
 * fetch returned, not a persisted artifact with its own is_stale
 * concept. Grouped by role and showing quality_score/quality_reasons_json
 * directly is the "why was this scored this way" surface the ADR calls
 * for - never collapsed into a single number.
 *
 * Phase 9.6 adds: a direct upload control (Priority 3 acquisition -
 * uploads enter as ordinary unscored candidates, same as every other
 * source, so there's nothing to render for one until Score References
 * runs), manual include/reject/supersede controls per image (the
 * human-in-the-loop override the ADR requires), and a non-blocking
 * "offer to upgrade" banner on any image the Stage flagged as a
 * higher-quality near-duplicate of an older included image -
 * confirming it is an ordinary manual supersede write on the *older*
 * image, never a silent swap.
 *
 * Phase 11.5 (see MIGRATION_PLAN.md) - closes a real gap the Phase 11
 * audit found: `images` now comes from listReferenceImages (every
 * current image, any status), not just the included-only Library, so
 * an unscored upload, a rejected candidate, or a superseded image are
 * all reviewable here instead of silently disappearing. Each card shows
 * its real library_status and isolation_method (candidate/isolation
 * crop/user upload/source import - the actual evidence source, not
 * inferred), an Include action alongside Reject/Supersede (the
 * plumbing already existed via updateLibraryStatus; only the "included"
 * call was never exposed as a button), and role is now directly
 * editable (a real, additive backend endpoint - role previously had no
 * manual-override path at all, unlike library_status).
 */
function ReferenceLibraryPanel({
  images,
  productId,
  onScore,
  scoring,
  onUpload,
  uploading,
  onUpdateStatus,
  onUpdateRole,
  updatingStatusId,
}: {
  images: ProductReferenceImage[] | undefined;
  productId: string;
  onScore: () => void;
  scoring: boolean;
  onUpload: (file: File) => void;
  uploading: boolean;
  onUpdateStatus: (imageId: string, status: 'included' | 'rejected' | 'superseded') => void;
  onUpdateRole: (imageId: string, role: string) => void;
  updatingStatusId: string | null;
}) {
  const grouped = new Map<string, ProductReferenceImage[]>();
  (images ?? []).forEach((img) => {
    const role = img.role ?? 'unassigned';
    if (!grouped.has(role)) grouped.set(role, []);
    grouped.get(role)!.push(img);
  });
  const imagesById = new Map((images ?? []).map((img) => [img.id, img]));
  const includedCount = (images ?? []).filter((img) => img.library_status === 'included').length;

  const handleFileSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) onUpload(file);
    event.target.value = '';
  };

  const statusLabel = (status: ProductReferenceImage['library_status']) =>
    status === null ? 'Unscored' : status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <div className="reference-library-panel">
      <div className="reference-library-header">
        <span className="field-label">
          Reference Images{images && images.length > 0 ? ` (${includedCount} in Library)` : ''}
        </span>
        <div className="reference-library-header-actions">
          <label className="file-picker-button secondary">
            {uploading ? 'Uploading…' : 'Upload Image'}
            <input type="file" accept="image/*" onChange={handleFileSelected} disabled={uploading} hidden />
          </label>
          <button className="rerun-button secondary" onClick={onScore} disabled={scoring}>
            {scoring ? 'Scoring…' : 'Score References'}
          </button>
        </div>
      </div>
      {!images || images.length === 0 ? (
        <p className="empty-state">No reference images yet.</p>
      ) : (
        Array.from(grouped.entries()).map(([role, roleImages]) => (
          <div key={role} className="reference-library-role-group">
            <span className="tag">{role}</span>
            <div className="reference-images-row">
              {roleImages.map((img) => {
                const upgradeTarget = img.upgrade_candidate_of_id
                  ? imagesById.get(img.upgrade_candidate_of_id)
                  : undefined;
                const busy = updatingStatusId === img.id;
                return (
                  <div key={img.id} className="reference-library-item">
                    <img
                      src={api.referenceImageFileUrl(productId, img.id)}
                      alt="Reference"
                      className="reference-image-thumbnail"
                    />
                    <div className="reference-library-item-badges">
                      <span className={`library-status-badge library-status-${img.library_status ?? 'unscored'}`}>
                        {statusLabel(img.library_status)}
                      </span>
                      <span className="isolation-method-badge">{img.isolation_method}</span>
                      {img.quality_score !== null && (
                        <span className="quality-score-badge">{img.quality_score.toFixed(2)}</span>
                      )}
                    </div>
                    {img.quality_reasons_json && img.quality_reasons_json.length > 0 && (
                      <p className="field-check-reason">{img.quality_reasons_json.join('; ')}</p>
                    )}
                    <input
                      key={`${img.id}-${img.role ?? ''}`}
                      type="text"
                      className="reference-role-input"
                      placeholder="Role (e.g. front)"
                      defaultValue={img.role ?? ''}
                      disabled={busy}
                      onBlur={(e) => {
                        const value = e.target.value.trim();
                        if (value !== (img.role ?? '')) onUpdateRole(img.id, value);
                      }}
                    />
                    <div className="reference-library-item-actions">
                      {img.library_status !== 'included' && (
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => onUpdateStatus(img.id, 'included')}
                        >
                          Include
                        </button>
                      )}
                      {img.library_status !== 'rejected' && (
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => onUpdateStatus(img.id, 'rejected')}
                        >
                          Reject
                        </button>
                      )}
                      {img.library_status !== 'superseded' && (
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => onUpdateStatus(img.id, 'superseded')}
                        >
                          Supersede
                        </button>
                      )}
                    </div>
                    {upgradeTarget && (
                      <div className="upgrade-prompt">
                        <p className="field-check-reason">
                          Looks like a better version of an existing image.
                        </p>
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => onUpdateStatus(upgradeTarget.id, 'superseded')}
                        >
                          Use this instead
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function LabeledField({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="field-row">
      <span className="field-label">{label}</span>
      <span className="field-value">{value}</span>
    </div>
  );
}

function TagList({ label, items }: { label: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="field-row">
      <span className="field-label">{label}</span>
      <div className="tag-list">
        {items.map((item, i) => (
          <span key={i} className="tag">
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function ProductLockProfileFields({ structured }: { structured: Record<string, unknown> }) {
  const s = structured as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  return (
    <div className="field-grid">
      <LabeledField label="Category" value={s.product_category} />
      <LabeledField label="Type" value={s.product_type} />
      <LabeledField label="Shape & Proportions" value={s.shape_and_proportions} />
      <LabeledField
        label="Packaging"
        value={[s.packaging?.type, s.packaging?.closure, s.packaging?.notes].filter(Boolean).join(' · ')}
      />
      <TagList label="Materials" items={s.materials} />
      <LabeledField label="Surface Finish" value={s.surface_finish} />
      <TagList label="Primary Colors" items={s.colors?.primary} />
      <TagList label="Secondary Colors" items={s.colors?.secondary} />
      <LabeledField
        label="Branding"
        value={[s.branding?.brand_name, s.branding?.logo_placement, s.branding?.logo_description]
          .filter(Boolean)
          .join(' · ')}
      />
      <TagList label="Distinguishing Features" items={s.distinguishing_features} />
      <LabeledField label="Viewing Angle" value={s.viewing_angle} />
      <LabeledField label="Perspective" value={s.perspective} />
      <LabeledField label="Lighting" value={s.lighting_characteristics} />
      <LabeledField label="Scale in Frame" value={s.approximate_scale_in_frame} />
      {s.immutable_characteristics && s.immutable_characteristics.length > 0 && (
        <div className="immutable-callout">
          <span className="immutable-label">Must never change</span>
          <ul>
            {s.immutable_characteristics.map((item: string, i: number) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CreativeFingerprintFields({ structured }: { structured: Record<string, unknown> }) {
  const s = structured as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  return (
    <div className="field-grid">
      <LabeledField label="Visual Style" value={s.visual_style} />
      <LabeledField label="Marketing Objective" value={s.marketing_objective} />
      <TagList label="Emotional Appeal" items={s.emotional_appeal} />
      <LabeledField label="Target Audience" value={s.target_audience} />
      <TagList label="Color Palette" items={s.color_palette} />
      <LabeledField label="Typography Style" value={s.typography_style} />
      <LabeledField label="Layout & Composition" value={s.layout_and_composition} />
      <LabeledField label="Background" value={s.background_environment} />
      <LabeledField label="Lighting Style" value={s.lighting_style} />
      <LabeledField label="Graphic Style" value={s.graphic_style} />
      <LabeledField label="Product Prominence" value={s.product_prominence} />
      <LabeledField label="Marketing Angle" value={s.marketing_angle} />
      <LabeledField label="Visual Hierarchy" value={s.visual_hierarchy} />
      <TagList label="Trust Elements" items={s.trust_elements} />
      <TagList label="Promotional Devices" items={s.promotional_devices} />
    </div>
  );
}

function CreativeSpecificationFields({ structured }: { structured: Record<string, unknown> }) {
  const s = structured as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  return (
    <div className="field-grid">
      <LabeledField label="Subject" value={s.subject} />
      <LabeledField label="Composition" value={s.composition} />
      <LabeledField label="Style Direction" value={s.style_direction} />
      <TagList label="Color Palette" items={s.color_palette} />
      <LabeledField label="Lighting" value={s.lighting} />
      <LabeledField label="Camera & Perspective" value={s.camera_and_perspective} />
      <LabeledField label="Background" value={s.background_environment} />
      <LabeledField label="Mood" value={s.mood} />
      {s.text_overlays && s.text_overlays.length > 0 && (
        <div className="field-row">
          <span className="field-label">Text Overlays</span>
          <div>
            {s.text_overlays.map((overlay: { role: string; content: string }, i: number) => (
              <div key={i} className="text-overlay-item">
                <span className="tag">{overlay.role}</span> {overlay.content}
              </div>
            ))}
          </div>
        </div>
      )}
      <TagList label="Things to Avoid" items={s.things_to_avoid} />
      <LabeledField label="Aspect Ratio" value={s.aspect_ratio} />
    </div>
  );
}

function CopyJsonButton({ data }: { data: unknown }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button className="copy-button" onClick={handleCopy}>
      {copied ? 'Copied!' : 'Copy JSON'}
    </button>
  );
}
