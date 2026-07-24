import { useState } from 'react';
import { api, type Slideshow } from '../api';
import { SlideshowBlueprintModal } from './SlideshowBlueprintModal';

interface CreativeGalleryProps {
  slideshows: Slideshow[];
  loading: boolean;
  onChanged: () => void;
}

// Phase 11.9 (Product Experience, see MIGRATION_PLAN.md) - plain-
// language status, not the technical imported/queued/analyzing/ready/
// failed vocabulary SlideshowGrid (Advanced) still shows. This is the
// same underlying Slideshow.status, just read by someone who never
// heard of "analysis" or "queued" - what they want to know is whether
// it's done, still working, or needs attention.
const FRIENDLY_STATUS: Record<string, string> = {
  imported: 'Imported',
  queued: 'Working…',
  analyzing: 'Working…',
  ready: 'Done',
  failed: 'Needs attention',
};

/**
 * Phase 11.9 (Product Experience, see MIGRATION_PLAN.md) - the gallery
 * half of the new home view: past/in-progress creatives, click one to
 * view it. Deliberately not SlideshowGrid (Advanced, kept unmodified) -
 * no per-slide product picker, no Analyze/Retry button, no technical
 * status vocabulary. Opens the same, unmodified SlideshowBlueprintModal
 * every existing capability already lives in - this view only changes
 * how a creative is found, not what's inside it.
 */
export function CreativeGallery({ slideshows, loading, onChanged }: CreativeGalleryProps) {
  const [selectedSlideshowId, setSelectedSlideshowId] = useState<string | null>(null);

  if (loading) return <p>Loading your creatives…</p>;

  if (slideshows.length === 0) {
    return <p className="empty-state">No creatives yet - use the form above to make your first one.</p>;
  }

  return (
    <>
      <ul className="creative-gallery-grid">
        {slideshows.map((slideshow) => {
          const slide = slideshow.slides[0];
          if (!slide) return null;
          return (
            <li key={slideshow.id} className="creative-gallery-card">
              <button
                type="button"
                className="creative-gallery-card-button"
                onClick={() => setSelectedSlideshowId(slideshow.id)}
              >
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
                <span className={`status-badge status-${slideshow.status}`}>
                  {FRIENDLY_STATUS[slideshow.status] ?? slideshow.status}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {selectedSlideshowId && (
        <SlideshowBlueprintModal
          slideshowId={selectedSlideshowId}
          onClose={() => setSelectedSlideshowId(null)}
          onChanged={onChanged}
        />
      )}
    </>
  );
}
