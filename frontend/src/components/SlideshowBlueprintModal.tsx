import { useEffect, useState } from 'react';
import { api, type AssembledSlideshowBlueprint } from '../api';

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
  recreation_prompt: 'Recreation Prompt',
};

/**
 * New-pipeline equivalent of CreativeBlueprintModal.tsx. Slide-scoped
 * sections (Product, Creative Fingerprint, OCR) read from
 * blueprint.slides[0] - valid while Phase 2's cardinality invariant
 * holds (exactly one slide per slideshow); slideshow-scoped sections
 * (Marketing Analysis, Recreation Prompt) read from blueprint directly.
 * True multi-slide rendering (a filmstrip/carousel over blueprint.slides)
 * is a later phase (Phase 7), not this one.
 */
export function SlideshowBlueprintModal({ slideshowId, onClose, onChanged }: SlideshowBlueprintModalProps) {
  const [blueprint, setBlueprint] = useState<AssembledSlideshowBlueprint | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

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
      const result = await api.analyzeSlideshow(slideshowId);
      setBlueprint(result);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyAction(null);
    }
  };

  const handleRerun = async (stageName: string) => {
    setBusyAction(stageName);
    setError(null);
    try {
      const result = await api.rerunSlideshowStage(slideshowId, stageName);
      setBlueprint(result);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyAction(null);
    }
  };

  const slide = blueprint?.slides[0];

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
                {slide.product_appearances[0]?.product && (
                  <p className="blueprint-meta">
                    Product: {slide.product_appearances[0].product.display_name}
                  </p>
                )}
                <p className="blueprint-meta">
                  Imported {new Date(blueprint.imported_at).toLocaleString()} via{' '}
                  {slide.source_type}
                </p>
                <button
                  className="analyze-all-button"
                  onClick={handleAnalyzeAll}
                  disabled={busyAction !== null}
                >
                  {busyAction === '__all__' ? 'Analyzing…' : 'Analyze / Re-run All'}
                </button>
              </div>
            </header>

            {blueprint.status === 'failed' && blueprint.failed_stage && (
              <div className="blueprint-failure-banner">
                <strong>{STAGE_LABELS[blueprint.failed_stage] ?? blueprint.failed_stage} failed.</strong>{' '}
                {blueprint.failed_stage_error}
              </div>
            )}

            <BlueprintSection
              title="Product"
              generated={slide.product_lock_profile !== null}
              failed={blueprint.failed_stage === 'product_lock_profile'}
              error={blueprint.failed_stage === 'product_lock_profile' ? blueprint.failed_stage_error : null}
              rerunLabel="Regenerate profile"
              onRerun={() => handleRerun('product_lock_profile')}
              busy={busyAction === 'product_lock_profile'}
              extraAction={
                <button
                  className="rerun-button secondary"
                  onClick={() => handleRerun('product_isolation')}
                  disabled={busyAction !== null}
                >
                  {busyAction === 'product_isolation' ? 'Re-cropping…' : 'Re-crop product image'}
                </button>
              }
            >
              {slide.product_reference_images.length > 0 && (
                <div className="reference-images-row">
                  {slide.product_reference_images.map((img) => (
                    <img
                      key={img.id}
                      src={api.referenceImageFileUrl(
                        slide.product_appearances[0]?.product_id ?? '',
                        img.id
                      )}
                      alt="Product reference"
                      className="reference-image-thumbnail"
                    />
                  ))}
                </div>
              )}
              {slide.product_lock_profile && (
                <ProductLockProfileFields structured={slide.product_lock_profile.structured} />
              )}
            </BlueprintSection>

            <BlueprintSection
              title="Creative Fingerprint"
              generated={slide.creative_fingerprint !== null}
              failed={blueprint.failed_stage === 'creative_fingerprint'}
              error={blueprint.failed_stage === 'creative_fingerprint' ? blueprint.failed_stage_error : null}
              rerunLabel="Regenerate fingerprint"
              onRerun={() => handleRerun('creative_fingerprint')}
              busy={busyAction === 'creative_fingerprint'}
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
              busy={busyAction === 'marketing_analysis'}
            >
              {blueprint.marketing_analysis && (
                <p className="narrative-text">{blueprint.marketing_analysis.narrative_text}</p>
              )}
            </BlueprintSection>

            <BlueprintSection
              title="OCR Text"
              generated={slide.ocr_result !== null}
              failed={blueprint.failed_stage === 'ocr'}
              error={blueprint.failed_stage === 'ocr' ? blueprint.failed_stage_error : null}
              rerunLabel="Re-run OCR"
              onRerun={() => handleRerun('ocr')}
              busy={busyAction === 'ocr'}
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
              title="Recreation Prompt"
              generated={blueprint.recreation_prompt !== null}
              failed={blueprint.failed_stage === 'recreation_prompt'}
              error={blueprint.failed_stage === 'recreation_prompt' ? blueprint.failed_stage_error : null}
              rerunLabel="Regenerate prompt"
              onRerun={() => handleRerun('recreation_prompt')}
              busy={busyAction === 'recreation_prompt'}
              extraAction={
                blueprint.recreation_prompt ? (
                  <CopyJsonButton data={blueprint.recreation_prompt.structured} />
                ) : undefined
              }
            >
              {blueprint.recreation_prompt && (
                <RecreationPromptFields structured={blueprint.recreation_prompt.structured} />
              )}
            </BlueprintSection>
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
  children?: React.ReactNode;
}) {
  return (
    <section className="blueprint-section">
      <div className="blueprint-section-header">
        <h3>{title}</h3>
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

function RecreationPromptFields({ structured }: { structured: Record<string, unknown> }) {
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
