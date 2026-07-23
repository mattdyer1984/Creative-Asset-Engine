import { useEffect, useState } from 'react';
import {
  api,
  type AssembledSlideshowBlueprint,
  type GeneratedImageData,
  type ImageValidationResultData,
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

            <section className="blueprint-section">
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
                  </div>
                ))
              )}
            </section>

            <BlueprintSection
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

            <section className="blueprint-section">
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
                    {validationResult ? (
                      <ValidationResultPanel result={validationResult} />
                    ) : (
                      <p className="empty-state">Not validated yet.</p>
                    )}
                  </div>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function BlueprintSection({
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
    <section className="blueprint-section">
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
 * MIGRATION_PLAN.md) - field_checks is rendered directly, one row per
 * field with its own preserved/violated state and reason. This *is* the
 * "explain why it failed" the user asked for - never summarized away
 * into just a Pass/Fail badge.
 */
function ValidationResultPanel({ result }: { result: ImageValidationResultData }) {
  return (
    <div className="validation-result-panel">
      <span className={`validation-badge ${result.passed ? 'validation-pass' : 'validation-fail'}`}>
        {result.passed ? 'Pass' : 'Fail'}
      </span>
      <p className="narrative-text">{result.overall_explanation}</p>
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
