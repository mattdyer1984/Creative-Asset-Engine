import { useState } from 'react';
import { api, type Creative, type Product } from '../api';
import { ProductPicker } from './ProductPicker';
import { CreativeBlueprintModal } from './CreativeBlueprintModal';

interface CreativeGridProps {
  creatives: Creative[];
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

// Statuses from which triggering analysis makes sense. "analyzing" is
// excluded since V1's pipeline runs synchronously within the request
// that set it - by the time the UI re-renders, it's already ready/failed.
const ANALYZABLE_STATUSES = new Set(['imported', 'queued', 'failed']);

/**
 * A thumbnail, filename, status badge, an Analyze action, and a "View
 * Blueprint" button opening the single assembled Creative Blueprint view
 * (plan §1 principle 7, §11 M7) - the pipeline that produced it is an
 * implementation detail the user never has to reason about here.
 */
export function CreativeGrid({ creatives, loading, onStatusChange, products }: CreativeGridProps) {
  const [analyzingIds, setAnalyzingIds] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [selectedCreativeId, setSelectedCreativeId] = useState<string | null>(null);

  const handleAnalyze = async (creativeId: string) => {
    setAnalyzingIds((prev) => new Set(prev).add(creativeId));
    setErrors((prev) => ({ ...prev, [creativeId]: '' }));
    try {
      await api.analyzeCreative(creativeId);
      onStatusChange();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [creativeId]: (err as Error).message }));
    } finally {
      setAnalyzingIds((prev) => {
        const next = new Set(prev);
        next.delete(creativeId);
        return next;
      });
    }
  };

  if (loading) return <p>Loading creatives…</p>;

  if (creatives.length === 0) {
    return <p className="empty-state">No creatives imported yet.</p>;
  }

  return (
    <>
      <ul className="creative-grid">
        {creatives.map((creative) => {
          const status = creative.blueprint.status;
          const isAnalyzing = analyzingIds.has(creative.id);

          return (
            <li key={creative.id} className="creative-card">
              <img
                src={api.creativeFileUrl(creative.id)}
                alt={creative.original_filename}
                className="creative-thumbnail"
              />
              <div className="creative-card-body">
                <span className="creative-filename">{creative.original_filename}</span>
                <span className={`status-badge status-${status}`}>
                  {STATUS_LABELS[status] ?? status}
                </span>

                <ProductPicker
                  creativeId={creative.id}
                  currentProduct={creative.product}
                  products={products}
                  onChanged={onStatusChange}
                />

                {ANALYZABLE_STATUSES.has(status) && (
                  <button
                    className="analyze-button"
                    onClick={() => handleAnalyze(creative.id)}
                    disabled={isAnalyzing}
                  >
                    {isAnalyzing ? 'Analyzing…' : status === 'failed' ? 'Retry' : 'Analyze'}
                  </button>
                )}

                <button
                  className="view-ocr-button"
                  onClick={() => setSelectedCreativeId(creative.id)}
                >
                  View Blueprint
                </button>

                {errors[creative.id] && <p className="error card-error">{errors[creative.id]}</p>}
              </div>
            </li>
          );
        })}
      </ul>

      {selectedCreativeId && (
        <CreativeBlueprintModal
          creativeId={selectedCreativeId}
          onClose={() => setSelectedCreativeId(null)}
          onChanged={onStatusChange}
        />
      )}
    </>
  );
}
