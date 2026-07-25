import { useEffect, useState } from 'react';
import {
  api,
  type GenerateCreativeResponseData,
  type GenerationReviewData,
  type MainIssue,
} from '../api';
import type { SlideGenerationOutcome } from './CreateCreativeFlow';

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
  slides: SlideGenerationOutcome[];
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
 *
 * Generate All (see MIGRATION_PLAN.md) widened this from one slide to a
 * real carousel across every slide the batch attempted - every piece of
 * per-generation state below is keyed by slideId (was singular),
 * mirroring the carousel pattern already proven in
 * SlideshowBlueprintModal.tsx (selectedSlideIndex + Prev/Next +
 * thumbnail strip) rather than inventing a new one.
 */
export function GenerationResultsModal({
  slideshowId,
  slides,
  onClose,
  onChanged,
  onOpenAdvanced,
}: GenerationResultsModalProps) {
  const [selectedSlideIndex, setSelectedSlideIndex] = useState(0);
  const clampedSlideIndex = Math.min(selectedSlideIndex, slides.length - 1);
  const activeSlide = slides[clampedSlideIndex];

  const [resultBySlide, setResultBySlide] = useState<Record<string, GenerateCreativeResponseData | null>>(
    () => Object.fromEntries(slides.map((s) => [s.slideId, s.response]))
  );
  const [learningModeEnabled, setLearningModeEnabled] = useState<boolean | null>(null);
  const [reviewBySlide, setReviewBySlide] = useState<Record<string, GenerationReviewData | null>>({});
  const [reviewLoadedBySlide, setReviewLoadedBySlide] = useState<Record<string, boolean>>({});

  const [showBefore, setShowBefore] = useState(false);
  const [zoomed, setZoomed] = useState(false);

  const [scoreBySlide, setScoreBySlide] = useState<Record<string, number>>({});
  const [mainIssueBySlide, setMainIssueBySlide] = useState<Record<string, MainIssue>>({});
  const [commentBySlide, setCommentBySlide] = useState<Record<string, string>>({});
  const [savingBySlide, setSavingBySlide] = useState<Record<string, boolean>>({});
  const [saveErrorBySlide, setSaveErrorBySlide] = useState<Record<string, string | null>>({});

  const [feedbackBySlide, setFeedbackBySlide] = useState<Record<string, string>>({});
  const [regeneratingBySlide, setRegeneratingBySlide] = useState<Record<string, boolean>>({});
  const [regenerateErrorBySlide, setRegenerateErrorBySlide] = useState<Record<string, string | null>>({});

  useEffect(() => {
    api.getSettings().then((settings) => setLearningModeEnabled(settings.learning_mode_enabled));
  }, []);

  const refreshReview = (slideId: string, generationLogId: string) => {
    setReviewLoadedBySlide((prev) => ({ ...prev, [slideId]: false }));
    api
      .getGenerationLog(generationLogId)
      .then((detail) => {
        setReviewBySlide((prev) => ({ ...prev, [slideId]: detail.review }));
        setReviewLoadedBySlide((prev) => ({ ...prev, [slideId]: true }));
      })
      .catch(() => {
        // Real bug found live (see MIGRATION_PLAN.md): this used to mark
        // the slide as "loaded" even on a failed fetch, which
        // closeBlocked below reads identically to "loaded, genuinely no
        // review yet" - a single network hiccup on any slide in a
        // multi-slide batch permanently locked the whole modal, since
        // Learning Mode defaults to enabled for every user. Leaving
        // reviewLoadedBySlide unset here means this slide simply never
        // participates in the close gate instead of wrongly blocking it.
      });
  };

  // Loads every slide's review up front (not just the active one) - the
  // Learning Mode close gate below needs to know whether EVERY slide has
  // been reviewed, not just whichever one happens to be showing.
  useEffect(() => {
    for (const slide of slides) {
      const generationLogId = resultBySlide[slide.slideId]?.generation_log_id;
      if (generationLogId) refreshReview(slide.slideId, generationLogId);
    }
    // Only ever run once per slide set - regenerate below refreshes its
    // own slide's review explicitly instead of re-running this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reset the before/after + zoom view whenever the active slide changes,
  // same reasoning as the old single-slide reset-on-regenerate behavior.
  useEffect(() => {
    setShowBefore(false);
    setZoomed(false);
  }, [clampedSlideIndex]);

  // Real bug found live (see MIGRATION_PLAN.md): "there's no way to
  // close the modal down once it appears on screen." Learning Mode's
  // mandatory-review gate (closeBlocked below) defaults to enabled for
  // every user (app_setting.py's own default), and the X/backdrop/
  // footer-button close paths are all genuinely disabled while it's
  // active - by design, to encourage review, but with no escape hatch
  // at all that was a real dead end. Escape always closes regardless of
  // closeBlocked - a near-universal modal expectation, and a guaranteed
  // way out that doesn't remove the visual nudge for the normal
  // click-driven flow.
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!activeSlide) return null;

  const activeResult = resultBySlide[activeSlide.slideId];
  const activeReview = reviewBySlide[activeSlide.slideId] ?? null;
  const activeScore = scoreBySlide[activeSlide.slideId] ?? 50;
  const activeMainIssue = mainIssueBySlide[activeSlide.slideId] ?? 'none';
  const activeComment = commentBySlide[activeSlide.slideId] ?? '';
  const activeSaving = savingBySlide[activeSlide.slideId] ?? false;
  const activeSaveError = saveErrorBySlide[activeSlide.slideId] ?? null;
  const activeFeedback = feedbackBySlide[activeSlide.slideId] ?? '';
  const activeRegenerating = regeneratingBySlide[activeSlide.slideId] ?? false;
  const activeRegenerateError = regenerateErrorBySlide[activeSlide.slideId] ?? null;

  const afterImageUrl = activeResult?.final_output
    ? api.finalOutputFileUrl(slideshowId, activeResult.final_output.id)
    : activeResult?.winner
      ? api.generatedImageFileUrl(slideshowId, activeResult.winner.id)
      : null;

  // When nothing was accepted, this used to show the ORIGINAL SLIDE in the
  // result slot with one sentence of explanation - so a failed run looked
  // like a result that had barely changed, and the candidates we actually
  // generated (and paid for) were invisible. Every candidate the backend
  // returns is now kept and shown, clearly labelled.
  const bestFailedCandidate = (() => {
    if (afterImageUrl || !activeResult) return null;
    const candidates = (activeResult.attempts ?? []).flatMap((attempt) => attempt.candidates ?? []);
    if (candidates.length === 0) return null;
    return candidates.reduce((best, candidate) =>
      (candidate.quality_assessment?.overall_confidence_score ?? 0) >
      (best.quality_assessment?.overall_confidence_score ?? 0)
        ? candidate
        : best
    );
  })();

  const failedCandidateUrl = bestFailedCandidate
    ? api.generatedImageFileUrl(slideshowId, bestFailedCandidate.generated_image.id)
    : null;

  const beforeImageUrl = api.slideFileUrl(slideshowId, activeSlide.slideId);
  // The original is shown only when explicitly toggled, or when there is
  // genuinely nothing generated. It must never silently occupy the result
  // slot as though it were output.
  const resultImageUrl = afterImageUrl ?? failedCandidateUrl;
  const currentImageUrl = showBefore || !resultImageUrl ? beforeImageUrl : resultImageUrl;

  const imageLabel =
    showBefore || !resultImageUrl
      ? 'Original slide'
      : afterImageUrl
        ? 'Generated candidate - passed automated checks'
        : 'Generated candidate - failed automated checks';

  // Why the best candidate was rejected. Computed server-side: the
  // per-field checks live on ImageValidationResult, which the client only
  // ever receives an id for, so the UI cannot derive these itself.
  const failureReasons: string[] = bestFailedCandidate?.rejection_reasons ?? [];

  // Learning Mode's mandatory-review gate now spans every slide that has
  // a real generation_log_id (an attempt that actually ran, whether or
  // not it won), not just the one currently showing - closing the modal
  // shouldn't let an unreviewed slide slip through just because the user
  // never clicked over to it.
  const closeBlocked =
    learningModeEnabled === true &&
    slides.some((slide) => {
      const generationLogId = resultBySlide[slide.slideId]?.generation_log_id;
      if (!generationLogId) return false;
      return reviewLoadedBySlide[slide.slideId] === true && reviewBySlide[slide.slideId] == null;
    });

  const handleBackdropClick = () => {
    if (!closeBlocked) onClose();
  };

  const handleSaveReview = async () => {
    const result = activeResult;
    if (!result) return;
    setSavingBySlide((prev) => ({ ...prev, [activeSlide.slideId]: true }));
    setSaveErrorBySlide((prev) => ({ ...prev, [activeSlide.slideId]: null }));
    try {
      const saved = await api.submitGenerationReview(result.generation_log_id, {
        overall_score: activeScore,
        main_issue: activeMainIssue,
        comment: activeComment.trim() ? activeComment.trim() : null,
      });
      setReviewBySlide((prev) => ({ ...prev, [activeSlide.slideId]: saved }));
      onChanged();
    } catch (err) {
      setSaveErrorBySlide((prev) => ({ ...prev, [activeSlide.slideId]: (err as Error).message }));
    } finally {
      setSavingBySlide((prev) => ({ ...prev, [activeSlide.slideId]: false }));
    }
  };

  const handleRegenerate = async () => {
    const slideId = activeSlide.slideId;
    setRegeneratingBySlide((prev) => ({ ...prev, [slideId]: true }));
    setRegenerateErrorBySlide((prev) => ({ ...prev, [slideId]: null }));
    try {
      const feedback = activeFeedback.trim();
      const regenerated = await api.generateCreative(slideshowId, slideId, {
        ...activeSlide.regenerateRequest,
        ...(feedback ? { regenerate_feedback: feedback } : {}),
      });
      setResultBySlide((prev) => ({ ...prev, [slideId]: regenerated }));
      setFeedbackBySlide((prev) => ({ ...prev, [slideId]: '' }));
      setShowBefore(false);
      setZoomed(false);
      refreshReview(slideId, regenerated.generation_log_id);
      onChanged();
    } catch (err) {
      setRegenerateErrorBySlide((prev) => ({ ...prev, [slideId]: (err as Error).message }));
    } finally {
      setRegeneratingBySlide((prev) => ({ ...prev, [slideId]: false }));
    }
  };

  const generationLogIds = slides
    .map((slide) => resultBySlide[slide.slideId]?.generation_log_id)
    .filter((id): id is string => Boolean(id));

  return (
    <div className="results-modal-backdrop" onClick={handleBackdropClick}>
      <div className="results-modal" onClick={(e) => e.stopPropagation()}>
        {!closeBlocked && (
          <button className="results-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        )}

        <div className="results-modal-viewer">
          {activeSlide.error && (
            <p className="results-modal-no-winner-banner">
              This slide couldn't be generated: {activeSlide.error}
            </p>
          )}
          {!activeSlide.error && !afterImageUrl && (
            <div className="results-modal-no-winner-banner">
              <p>
                {failedCandidateUrl
                  ? 'These candidates did not pass our automated quality checks. The best one is shown below so you can judge it yourself - you can still accept it, regenerate, or add clearer product references.'
                  : 'Nothing was generated for this slide, so the original is shown for reference.'}
              </p>
              {failureReasons.length > 0 && (
                <ul className="results-modal-failure-reasons">
                  {failureReasons.slice(0, 6).map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {currentImageUrl ? (
            <div
              className={`results-modal-image-frame${zoomed ? ' zoomed' : ''}`}
              onClick={() => setZoomed((z) => !z)}
            >
              <span
                className={
                  imageLabel.startsWith('Original')
                    ? 'results-modal-image-label is-original'
                    : imageLabel.endsWith('passed automated checks')
                      ? 'results-modal-image-label is-passed'
                      : 'results-modal-image-label is-failed'
                }
              >
                {imageLabel}
              </span>
              <img
                src={currentImageUrl}
                alt={imageLabel}
              />
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

          {slides.length > 1 && (
            <div className="slide-selector">
              <button
                onClick={() => setSelectedSlideIndex((i) => Math.max(0, i - 1))}
                disabled={clampedSlideIndex === 0}
                aria-label="Previous slide"
              >
                ← Prev
              </button>
              <div className="slide-carousel" role="tablist" aria-label="Slides">
                {slides.map((slide, i) => {
                  const thumbResult = resultBySlide[slide.slideId];
                  const thumbAfterUrl = thumbResult?.final_output
                    ? api.finalOutputFileUrl(slideshowId, thumbResult.final_output.id)
                    : thumbResult?.winner
                      ? api.generatedImageFileUrl(slideshowId, thumbResult.winner.id)
                      : null;
                  const failed = slide.error !== null;
                  return (
                    <button
                      key={slide.slideId}
                      type="button"
                      role="tab"
                      aria-selected={i === clampedSlideIndex}
                      className={`slide-carousel-thumb${i === clampedSlideIndex ? ' active' : ''}${failed ? ' failed' : ''}`}
                      onClick={() => setSelectedSlideIndex(i)}
                      title={failed ? `Slide ${i + 1} · failed: ${slide.error}` : `Slide ${i + 1}`}
                    >
                      <img
                        src={thumbAfterUrl ?? api.slideFileUrl(slideshowId, slide.slideId)}
                        alt={`Slide ${i + 1}`}
                        className="slide-carousel-thumb-image"
                      />
                      <span className="slide-carousel-thumb-index">{failed ? '!' : i + 1}</span>
                    </button>
                  );
                })}
              </div>
              <button
                onClick={() => setSelectedSlideIndex((i) => Math.min(slides.length - 1, i + 1))}
                disabled={clampedSlideIndex === slides.length - 1}
                aria-label="Next slide"
              >
                Next →
              </button>
            </div>
          )}
          {slides.length > 1 && (
            <p className="slide-carousel-caption">
              Slide {clampedSlideIndex + 1} of {slides.length}
            </p>
          )}
        </div>

        <div className="results-modal-review">
          {activeSlide.error ? (
            <p className="empty-state">This slide failed - nothing to review yet.</p>
          ) : activeReview ? (
            <div className="results-modal-review-saved">
              <h3>Review saved</h3>
              <p>
                <strong>{activeReview.overall_score}/100</strong> &middot;{' '}
                {MAIN_ISSUE_OPTIONS.find((o) => o.value === activeReview.main_issue)?.label ??
                  activeReview.main_issue}
              </p>
              {activeReview.comment && (
                <p className="results-modal-review-comment">"{activeReview.comment}"</p>
              )}
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
                    value={activeScore}
                    onChange={(e) =>
                      setScoreBySlide((prev) => ({ ...prev, [activeSlide.slideId]: Number(e.target.value) }))
                    }
                  />
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={activeScore}
                    onChange={(e) =>
                      setScoreBySlide((prev) => ({
                        ...prev,
                        [activeSlide.slideId]: Math.max(0, Math.min(100, Number(e.target.value))),
                      }))
                    }
                  />
                </div>
              </label>

              <span className="create-flow-step-label">Main Issue</span>
              <div className="results-modal-issue-grid">
                {MAIN_ISSUE_OPTIONS.map((option) => (
                  <label key={option.value} className="results-modal-issue-option">
                    <input
                      type="radio"
                      checked={activeMainIssue === option.value}
                      onChange={() =>
                        setMainIssueBySlide((prev) => ({ ...prev, [activeSlide.slideId]: option.value }))
                      }
                    />
                    {option.label}
                  </label>
                ))}
              </div>

              <label className="results-modal-comment-label">
                Comment (optional)
                <textarea
                  placeholder="e.g. Product slightly too small, text feels weaker than original…"
                  value={activeComment}
                  onChange={(e) =>
                    setCommentBySlide((prev) => ({ ...prev, [activeSlide.slideId]: e.target.value }))
                  }
                  rows={2}
                />
              </label>

              {activeSaveError && <p className="error card-error">{activeSaveError}</p>}

              <button className="rerun-button" disabled={activeSaving} onClick={handleSaveReview}>
                {activeSaving ? 'Saving…' : 'Save Review'}
              </button>
            </>
          )}

          <label className="results-modal-comment-label">
            What's wrong with this one? (optional, used on Regenerate)
            <textarea
              placeholder="e.g. The bottle looks too dark, make it brighter…"
              value={activeFeedback}
              onChange={(e) =>
                setFeedbackBySlide((prev) => ({ ...prev, [activeSlide.slideId]: e.target.value }))
              }
              rows={2}
            />
          </label>
        </div>

        {activeRegenerateError && <p className="error card-error">{activeRegenerateError}</p>}

        <div className="results-modal-footer">
          {currentImageUrl && (
            <a href={currentImageUrl} download className="rerun-button">
              Download Current Slide
            </a>
          )}
          {generationLogIds.length > 0 && (
            <a
              href={
                generationLogIds.length > 1
                  ? api.generationLogZipBatchUrl(generationLogIds)
                  : api.generationLogZipUrl(generationLogIds[0])
              }
              download
              className="results-modal-primary-download"
            >
              Download All (.zip)
            </a>
          )}
          {activeResult && (
            <button
              className="rerun-button secondary"
              onClick={() => api.openGenerationLogFolder(activeResult.generation_log_id)}
            >
              Open Generation Log
            </button>
          )}
          <button className="rerun-button secondary" disabled={activeRegenerating} onClick={handleRegenerate}>
            {activeRegenerating ? 'Regenerating…' : 'Regenerate'}
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
            Save a review for every slide to close this window (Learning Mode is on).
          </p>
        )}
      </div>
    </div>
  );
}
