import { useEffect, useState } from 'react';
import {
  api,
  type GenerateCreativeRequest,
  type GenerateCreativeResponseData,
  type MainIssue,
} from '../api';

const MAIN_ISSUE_OPTIONS: { value: MainIssue; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'product_accuracy', label: 'Product Accuracy' },
  { value: 'composition', label: 'Composition' },
  { value: 'realism', label: 'Realism' },
  { value: 'lighting', label: 'Lighting' },
  { value: 'text', label: 'Text' },
  { value: 'background', label: 'Background' },
  { value: 'originality', label: 'Originality' },
  { value: 'other', label: 'Other' },
];

interface GenerationResultsModalProps {
  slideshowId: string;
  slideId: string;
  initialResult: GenerateCreativeResponseData;
  regenerateRequest: GenerateCreativeRequest;
  onClose: () => void;
  onChanged: () => void;
  onOpenAdvanced: () => void;
}

/**
 * Phase 12.5 (Human Feedback & Learning System, see MIGRATION_PLAN.md) -
 * the mandatory-review-first primary post-generation workflow the spec
 * calls for: Generate -> this modal -> Human Review -> Download/
 * Regenerate/Close, replacing CreateCreativeFlow's previous inline
 * result card. Full-screen (not the capped-width .blueprint-modal
 * pattern) since this is the primary workflow surface after every
 * generation, not a secondary detail view.
 */
export function GenerationResultsModal({
  slideshowId,
  slideId,
  initialResult,
  regenerateRequest,
  onClose,
  onChanged,
  onOpenAdvanced,
}: GenerationResultsModalProps) {
  const [result, setResult] = useState<GenerateCreativeResponseData>(initialResult);
  const [learningModeEnabled, setLearningModeEnabled] = useState<boolean | null>(null);
  const [review, setReview] = useState<{
    overall_score: number;
    main_issue: MainIssue;
    comment: string | null;
  } | null>(null);
  const [reviewLoaded, setReviewLoaded] = useState(false);

  const [showBefore, setShowBefore] = useState(false);
  const [zoomed, setZoomed] = useState(false);

  const [score, setScore] = useState(50);
  const [mainIssue, setMainIssue] = useState<MainIssue>('none');
  const [comment, setComment] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [regenerating, setRegenerating] = useState(false);
  const [regenerateError, setRegenerateError] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then((settings) => setLearningModeEnabled(settings.learning_mode_enabled));
  }, []);

  useEffect(() => {
    setReviewLoaded(false);
    setReview(null);
    api
      .getGenerationLog(result.generation_log_id)
      .then((detail) => {
        setReview(detail.review);
        setReviewLoaded(true);
      })
      .catch(() => setReviewLoaded(true));
  }, [result.generation_log_id]);

  const afterImageUrl = result.final_output
    ? api.finalOutputFileUrl(slideshowId, result.final_output.id)
    : result.winner
      ? api.generatedImageFileUrl(slideshowId, result.winner.id)
      : null;
  const beforeImageUrl = api.slideFileUrl(slideshowId, slideId);
  const currentImageUrl = showBefore || !afterImageUrl ? beforeImageUrl : afterImageUrl;

  // Forward-compatible N-slide carousel (see MIGRATION_PLAN.md's Phase
  // 12 context note) - generate-creative is still scoped to one slide
  // (Phase 8's boundary, unchanged here), so this always renders
  // exactly one entry today, not a claim that multi-slide works.
  const carouselSlides = [{ key: slideId, thumbUrl: afterImageUrl ?? beforeImageUrl }];

  const closeBlocked = learningModeEnabled === true && reviewLoaded && review === null;

  const handleBackdropClick = () => {
    if (!closeBlocked) onClose();
  };

  const handleSaveReview = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await api.submitGenerationReview(result.generation_log_id, {
        overall_score: score,
        main_issue: mainIssue,
        comment: comment.trim() ? comment.trim() : null,
      });
      setReview(saved);
      onChanged();
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    setRegenerateError(null);
    try {
      const regenerated = await api.generateCreative(slideshowId, slideId, regenerateRequest);
      setResult(regenerated);
      setShowBefore(false);
      setZoomed(false);
      onChanged();
    } catch (err) {
      setRegenerateError((err as Error).message);
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div className="results-modal-backdrop" onClick={handleBackdropClick}>
      <div className="results-modal" onClick={(e) => e.stopPropagation()}>
        {!closeBlocked && (
          <button className="results-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        )}

        <div className="results-modal-viewer">
          {currentImageUrl ? (
            <div
              className={`results-modal-image-frame${zoomed ? ' zoomed' : ''}`}
              onClick={() => setZoomed((z) => !z)}
            >
              <img src={currentImageUrl} alt={showBefore ? 'Original slide' : 'Generated creative'} />
            </div>
          ) : (
            <p className="empty-state">
              We ran the generation, but nothing passed our quality checks this time.
            </p>
          )}

          {afterImageUrl && (
            <div className="results-modal-before-after">
              <button
                type="button"
                className={showBefore ? '' : 'active'}
                onClick={() => setShowBefore(false)}
              >
                After
              </button>
              <button
                type="button"
                className={showBefore ? 'active' : ''}
                onClick={() => setShowBefore(true)}
              >
                Before
              </button>
            </div>
          )}

          <div className="results-modal-carousel">
            {carouselSlides.map((slide) => (
              <div key={slide.key} className="results-modal-carousel-thumb active">
                {slide.thumbUrl && <img src={slide.thumbUrl} alt="" />}
              </div>
            ))}
          </div>
        </div>

        <div className="results-modal-review">
          {review ? (
            <div className="results-modal-review-saved">
              <h3>Review saved</h3>
              <p>
                <strong>{review.overall_score}/100</strong> &middot;{' '}
                {MAIN_ISSUE_OPTIONS.find((o) => o.value === review.main_issue)?.label ?? review.main_issue}
              </p>
              {review.comment && <p className="results-modal-review-comment">"{review.comment}"</p>}
            </div>
          ) : (
            <>
              <h3>Review this generation</h3>
              <label className="results-modal-score-label">
                Overall Score
                <div className="results-modal-score-row">
                  <input
                    type="range"
                    min={0}
                    max={100}
                    value={score}
                    onChange={(e) => setScore(Number(e.target.value))}
                  />
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={score}
                    onChange={(e) => setScore(Math.max(0, Math.min(100, Number(e.target.value))))}
                  />
                </div>
              </label>

              <span className="create-flow-step-label">Main Issue</span>
              <div className="results-modal-issue-grid">
                {MAIN_ISSUE_OPTIONS.map((option) => (
                  <label key={option.value} className="results-modal-issue-option">
                    <input
                      type="radio"
                      checked={mainIssue === option.value}
                      onChange={() => setMainIssue(option.value)}
                    />
                    {option.label}
                  </label>
                ))}
              </div>

              <label className="results-modal-comment-label">
                Comment (optional)
                <textarea
                  placeholder="e.g. Product slightly too small, text feels weaker than original…"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={2}
                />
              </label>

              {saveError && <p className="error card-error">{saveError}</p>}

              <button className="rerun-button" disabled={saving} onClick={handleSaveReview}>
                {saving ? 'Saving…' : 'Save Review'}
              </button>
            </>
          )}
        </div>

        {regenerateError && <p className="error card-error">{regenerateError}</p>}

        <div className="results-modal-footer">
          {currentImageUrl && (
            <a href={currentImageUrl} download className="rerun-button">
              Download Current Slide
            </a>
          )}
          <a
            href={api.generationLogZipUrl(result.generation_log_id)}
            download
            className="results-modal-primary-download"
          >
            Download All (.zip)
          </a>
          <button
            className="rerun-button secondary"
            onClick={() => api.openGenerationLogFolder(result.generation_log_id)}
          >
            Open Generation Log
          </button>
          <button className="rerun-button secondary" disabled={regenerating} onClick={handleRegenerate}>
            {regenerating ? 'Regenerating…' : 'Regenerate'}
          </button>
          <button className="rerun-button secondary" onClick={onOpenAdvanced}>
            Advanced
          </button>
          <button className="rerun-button secondary" disabled={closeBlocked} onClick={onClose}>
            Close
          </button>
        </div>
        {closeBlocked && (
          <p className="results-modal-close-hint">
            Save a review to close this window (Learning Mode is on).
          </p>
        )}
      </div>
    </div>
  );
}
