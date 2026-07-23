import { useState } from 'react';
import { api, type Product, type Slideshow } from '../api';
import { SlideProductPicker } from './SlideProductPicker';
import { SlideshowBlueprintModal } from './SlideshowBlueprintModal';

interface SlideshowGridProps {
  slideshows: Slideshow[];
  loading: boolean;
  onStatusChange: () => void;
  products: Product[];
}

const STATUS_LABELS: Record<string, string> = {
  imported: 'Imported',
  queued: 'Queued',
  analyzing: 'Analyzing…',
  ready: 'Ready',
  failed: 'Failed',
};

// Statuses from which triggering analysis makes sense. "queued" and
// "analyzing" are both excluded - as of Phase 3.2 (async execution
// boundary, see MIGRATION_PLAN.md) these are real, observable states a
// background run can sit in for a while, not transient ones that are
// already ready/failed by the time the UI re-renders - triggering a
// second run while one is already in flight is rejected by the backend
// with 409 anyway, so this just keeps the button from offering it.
const ANALYZABLE_STATUSES = new Set(['imported', 'failed']);

/**
 * New-pipeline equivalent of CreativeGrid.tsx. Renders one card per
 * Slideshow, still showing only slides[0]'s thumbnail even for a
 * multi-slide Slideshow (Phase 4 - see MIGRATION_PLAN.md) - just with a
 * small slide-count badge so a multi-slide import isn't indistinguishable
 * from a single-slide one. A real filmstrip/carousel is a later phase
 * (Phase 7, frontend consolidation), not this one.
 */
export function SlideshowGrid({ slideshows, loading, onStatusChange, products }: SlideshowGridProps) {
  const [analyzingIds, setAnalyzingIds] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [selectedSlideshowId, setSelectedSlideshowId] = useState<string | null>(null);

  const handleAnalyze = async (slideshowId: string) => {
    setAnalyzingIds((prev) => new Set(prev).add(slideshowId));
    setErrors((prev) => ({ ...prev, [slideshowId]: '' }));
    try {
      await api.analyzeSlideshow(slideshowId);
      onStatusChange();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [slideshowId]: (err as Error).message }));
    } finally {
      setAnalyzingIds((prev) => {
        const next = new Set(prev);
        next.delete(slideshowId);
        return next;
      });
    }
  };

  if (loading) return <p>Loading slideshows…</p>;

  if (slideshows.length === 0) {
    return <p className="empty-state">No slideshows imported yet.</p>;
  }

  return (
    <>
      <ul className="creative-grid">
        {slideshows.map((slideshow) => {
          const slide = slideshow.slides[0];
          const status = slideshow.status;
          const isAnalyzing = analyzingIds.has(slideshow.id);

          return (
            <li key={slideshow.id} className="creative-card">
              <div className="creative-thumbnail-wrap">
                <img
                  src={api.slideFileUrl(slideshow.id, slide.id)}
                  alt={slide.original_filename}
                  className="creative-thumbnail"
                />
                {slideshow.slides.length > 1 && (
                  <span className="slide-count-badge">{slideshow.slides.length} slides</span>
                )}
              </div>
              <div className="creative-card-body">
                <span className="creative-filename">{slide.original_filename}</span>
                <span className={`status-badge status-${status}`}>
                  {STATUS_LABELS[status] ?? status}
                </span>

                <SlideProductPicker
                  slideshowId={slideshow.id}
                  slideId={slide.id}
                  currentAppearances={slide.current_product_appearances}
                  products={products}
                  onChanged={onStatusChange}
                />

                {ANALYZABLE_STATUSES.has(status) && (
                  <button
                    className="analyze-button"
                    onClick={() => handleAnalyze(slideshow.id)}
                    disabled={isAnalyzing}
                  >
                    {isAnalyzing ? 'Analyzing…' : status === 'failed' ? 'Retry' : 'Analyze'}
                  </button>
                )}

                <button
                  className="view-ocr-button"
                  onClick={() => setSelectedSlideshowId(slideshow.id)}
                >
                  View Blueprint
                </button>

                {errors[slideshow.id] && <p className="error card-error">{errors[slideshow.id]}</p>}
              </div>
            </li>
          );
        })}
      </ul>

      {selectedSlideshowId && (
        <SlideshowBlueprintModal
          slideshowId={selectedSlideshowId}
          onClose={() => setSelectedSlideshowId(null)}
          onChanged={onStatusChange}
        />
      )}
    </>
  );
}
