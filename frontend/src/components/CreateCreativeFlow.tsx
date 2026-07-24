import { useEffect, useState } from 'react';
import { resolveDefaultBundleSelection } from '../bundleDefaults';
import {
  api,
  type GenerateCreativeRequest,
  type GenerateCreativeResponseData,
  type Product,
  type TextStrategy,
} from '../api';
import { GenerationResultsModal } from './GenerationResultsModal';
import { SlideshowBlueprintModal } from './SlideshowBlueprintModal';

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

type Phase =
  | 'form'
  | 'importing'
  | 'resolving_product'
  | 'analyzing'
  | 'building_references'
  | 'generating'
  | 'done'
  | 'error';

const PROGRESS_LABELS: Record<Exclude<Phase, 'form' | 'done' | 'error'>, string> = {
  importing: 'Importing your slideshow…',
  resolving_product: 'Understanding your product…',
  analyzing: 'Analyzing your creative…',
  building_references: 'Building product references…',
  generating: 'Creating your images…',
};

// Generate All (see MIGRATION_PLAN.md) - one result per slide the
// slideshow attempted to generate. A slide with no resolvable product
// legitimately fails per-slide (response null, error set) rather than
// aborting the whole batch - the carousel (GenerationResultsModal)
// shows that honestly instead of hiding it.
export interface SlideGenerationOutcome {
  slideId: string;
  response: GenerateCreativeResponseData | null;
  error: string | null;
  regenerateRequest: GenerateCreativeRequest;
}

// Score References (Phase 9.2) is a background task with no completion
// signal - same fixed-polling-window reasoning as
// SlideshowBlueprintModal's own scoringProductId effect.
const REFERENCE_SCORING_POLL_ATTEMPTS = 10;
const REFERENCE_SCORING_POLL_INTERVAL_MS = 1500;

const TEXT_STRATEGY_OPTIONS: { value: TextStrategy; label: string; description: string }[] = [
  { value: 'reuse_original', label: 'Keep original text', description: 'Reuse the text and placement from the source slideshow.' },
  { value: 'ai_rewrite', label: 'AI-improve the text', description: 'Rewrite the on-screen text to read better.' },
  { value: 'no_text', label: 'Remove all text', description: 'Generate a clean image with no text overlay.' },
];

/**
 * Phase 11.8 (Product Experience, see MIGRATION_PLAN.md) - the
 * simplified "paste a link, pick a product, choose text handling, hit
 * Generate" flow the product owner asked for, replacing the previous
 * requirement to manually import, assign a product, analyze, and open
 * a 7-section modal to find the real Generate Creative button. This
 * component orchestrates the *existing* endpoints client-side - no new
 * backend pipeline - chaining import -> resolve/assign product ->
 * analyze (polled) -> generate-creative into one button with
 * plain-language progress, never internal stage names.
 */
export function CreateCreativeFlow({ onCreated }: { onCreated: () => void }) {
  const [sourceMode, setSourceMode] = useState<'url' | 'upload'>('url');
  const [slideshowUrl, setSlideshowUrl] = useState('');
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);

  const [productMode, setProductMode] = useState<'url' | 'existing'>('url');
  const [productUrl, setProductUrl] = useState('');
  const [existingProductId, setExistingProductId] = useState('');
  const [products, setProducts] = useState<Product[]>([]);

  const [textStrategy, setTextStrategy] = useState<TextStrategy>('reuse_original');

  const [phase, setPhase] = useState<Phase>('form');
  const [error, setError] = useState<string | null>(null);
  // Generate All (see MIGRATION_PLAN.md) - one outcome per slide,
  // replacing the old singular result/resultSlideId/resultRequest state.
  const [results, setResults] = useState<SlideGenerationOutcome[] | null>(null);
  const [resultSlideshowId, setResultSlideshowId] = useState<string | null>(null);
  const [generatingProgress, setGeneratingProgress] = useState<{ current: number; total: number } | null>(
    null
  );
  // Critical TikTok Slideshow Import Fix (see MIGRATION_PLAN.md) - the
  // required pre-generation confirmation. Set once import succeeds (so
  // it reflects the real, gate-verified slide count, not a guess) and
  // shown for the rest of the flow. Generate All (see MIGRATION_PLAN.md)
  // now attempts every imported slide, not just the primary one - a
  // slide with no resolvable product simply fails per-slide, shown
  // honestly in the results carousel rather than silently skipped here.
  const [importedSlideCount, setImportedSlideCount] = useState<number | null>(null);
  // Phase 11.10 (Product Experience, see MIGRATION_PLAN.md) - opens the
  // existing, unmodified SlideshowBlueprintModal (Advanced) for anyone
  // who wants the full technical picture behind this result - every
  // capability that existed before this flow stays reachable, just not
  // first.
  const [showAdvancedModal, setShowAdvancedModal] = useState(false);

  useEffect(() => {
    api.listProducts().then(setProducts).catch(() => undefined);
  }, []);

  const busy = phase !== 'form' && phase !== 'done' && phase !== 'error';

  const canGenerate =
    (sourceMode === 'url' ? slideshowUrl.trim().length > 0 : uploadFiles.length > 0) &&
    (productMode === 'url' ? productUrl.trim().length > 0 : existingProductId.length > 0);

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    setUploadFiles(event.target.files ? Array.from(event.target.files) : []);
  };

  const handleGenerate = async () => {
    setError(null);
    setResults(null);
    setGeneratingProgress(null);
    try {
      setPhase('importing');
      const slideshows =
        sourceMode === 'url'
          ? await api.importSlideshowFromUrl(slideshowUrl.trim())
          : await api.importSlideshows(uploadFiles, undefined, true);
      const slideshow = slideshows[0];
      if (!slideshow) throw new Error("Import didn't return a slideshow.");
      const primarySlideId = slideshow.slides[0]?.id;
      if (!primarySlideId) throw new Error('Imported slideshow has no slides.');
      setImportedSlideCount(slideshow.slides.length);

      setPhase('resolving_product');
      if (productMode === 'url') {
        // createListingSourceImport is get-or-create by URL (see
        // app.services.listing_import's own docstring) - pasting a product
        // URL that was already resolved in an earlier session returns that
        // SAME already-resolved Listing, not a fresh one. Found live: this
        // used to fall through to resolveListingToNewProduct unconditionally,
        // which 400s ("Listing is already resolved") since that transition
        // is one-shot - a real dead end once a product's URL had been used
        // once, and the list of existing products was never checked as an
        // alternative. Reusing an already-resolved listing's product/bundle
        // directly, before ever attempting a new resolution, fixes this.
        const listing = await api.createListingSourceImport(productUrl.trim());
        const detail = await api.getListing(listing.id);
        if (detail.resolved_product_id) {
          await api.addSlideProduct(slideshow.id, primarySlideId, detail.resolved_product_id);
        } else if (detail.resolved_bundle_id) {
          const bundleView = await api.getBundleView(detail.resolved_bundle_id);
          for (const member of bundleView.members) {
            await api.addSlideProduct(slideshow.id, primarySlideId, member.product_id);
          }
        } else if (detail.pending_bundle_hints.length > 0) {
          const members = detail.pending_bundle_hints.map((hint) => ({
            new_product_display_name: hint.label,
          }));
          const resolved = await api.resolveListingToNewBundle(
            listing.id,
            detail.pending_bundle_title ?? 'Bundle',
            members
          );
          if (!resolved.resolved_bundle_id) throw new Error("Couldn't resolve the product bundle.");
          const bundleView = await api.getBundleView(resolved.resolved_bundle_id);
          for (const member of bundleView.members) {
            await api.addSlideProduct(slideshow.id, primarySlideId, member.product_id);
          }
        } else {
          const resolved = await api.resolveListingToNewProduct(
            listing.id,
            detail.pending_product_title ?? 'New Product'
          );
          if (!resolved.resolved_product_id) throw new Error("Couldn't resolve the product.");
          await api.addSlideProduct(slideshow.id, primarySlideId, resolved.resolved_product_id);
        }
      } else {
        await api.addSlideProduct(slideshow.id, primarySlideId, existingProductId);
      }

      setPhase('analyzing');
      await api.analyzeSlideshow(slideshow.id);
      let blueprint = await api.getSlideshowBlueprint(slideshow.id);
      while (blueprint.status === 'queued' || blueprint.status === 'analyzing') {
        await sleep(1500);
        blueprint = await api.getSlideshowBlueprint(slideshow.id);
      }
      if (blueprint.status === 'failed') {
        throw new Error(blueprint.failed_stage_error ?? 'Something went wrong while analyzing your creative.');
      }

      // Score References (Phase 9.2) is a separate, required step: the
      // slide's own Product Isolation crops (part of the analyze
      // pipeline above) only ever enter the Canonical Reference Library
      // once scored - generate-creative 422s on an empty Library
      // otherwise. Found live: a real generate-creative call against a
      // freshly-analyzed product failed with exactly this error before
      // this step was added. Generate All (see MIGRATION_PLAN.md) widens
      // this across every slide's own selection, not just the primary
      // slide's - each slide can carry a genuinely different product
      // (multi per-slide product detection, Phase 6), and a product
      // left unscored here 422s that slide's own generate-creative call
      // later with exactly the error this step exists to prevent.
      setPhase('building_references');
      const perSlideSelection = blueprint.slides.map((slide) => resolveDefaultBundleSelection(slide.products));
      const allProductIds = Array.from(
        new Set(perSlideSelection.flatMap((selection) => selection.selectedProductIds))
      );
      for (const productId of allProductIds) {
        await api.scoreReferences(productId);
      }
      for (const productId of allProductIds) {
        // Poll until scoring has actually finished (every current
        // candidate has a real library_status), not just until one gets
        // included - a candidate can legitimately score too low and get
        // rejected. Found live: a real crop scored 0.08 and was
        // correctly rejected - polling only for "included" would have
        // misreported that real, honest outcome as a timeout.
        let attempts = 0;
        let images = await api.listReferenceImages(productId);
        while (images.some((image) => image.library_status === null) && attempts < REFERENCE_SCORING_POLL_ATTEMPTS) {
          await sleep(REFERENCE_SCORING_POLL_INTERVAL_MS);
          images = await api.listReferenceImages(productId);
          attempts += 1;
        }
        if (!images.some((image) => image.library_status === 'included')) {
          throw new Error(
            "We couldn't build a usable reference image for this product - try a different product, or add a reference image for it in Advanced mode."
          );
        }
      }

      setPhase('generating');
      const outcomes: SlideGenerationOutcome[] = [];
      for (let i = 0; i < blueprint.slides.length; i++) {
        const slide = blueprint.slides[i];
        setGeneratingProgress({ current: i + 1, total: blueprint.slides.length });
        const { selectedProductIds, roles } = perSlideSelection[i];
        const bundleMembers =
          selectedProductIds.length > 1
            ? selectedProductIds.map((productId) => ({
                product_id: productId,
                role_in_scene: roles[productId] ?? productId,
              }))
            : undefined;
        const request: GenerateCreativeRequest = {
          quality_mode: 'fast',
          creativity_level: 'conservative',
          text_strategy: textStrategy,
          ...(bundleMembers ? { bundle_members: bundleMembers } : {}),
        };
        try {
          const response = await api.generateCreative(slideshow.id, slide.id, request);
          outcomes.push({ slideId: slide.id, response, error: null, regenerateRequest: request });
        } catch (err) {
          outcomes.push({
            slideId: slide.id,
            response: null,
            error: (err as Error).message,
            regenerateRequest: request,
          });
        }
      }

      setResults(outcomes);
      setResultSlideshowId(slideshow.id);
      setGeneratingProgress(null);
      setPhase('done');
      onCreated();
    } catch (err) {
      setError((err as Error).message);
      setPhase('error');
    }
  };

  const handleReset = () => {
    setPhase('form');
    setError(null);
    setResults(null);
    setResultSlideshowId(null);
    setGeneratingProgress(null);
    setShowAdvancedModal(false);
    setImportedSlideCount(null);
  };

  if (phase === 'done' && results && resultSlideshowId) {
    return (
      <>
        <GenerationResultsModal
          slideshowId={resultSlideshowId}
          slides={results}
          onClose={handleReset}
          onChanged={onCreated}
          onOpenAdvanced={() => setShowAdvancedModal(true)}
        />
        {showAdvancedModal && (
          <SlideshowBlueprintModal
            slideshowId={resultSlideshowId}
            onClose={() => setShowAdvancedModal(false)}
            onChanged={onCreated}
          />
        )}
      </>
    );
  }

  return (
    <div className="create-flow">
      <h2>Create a New Creative</h2>

      <div className="create-flow-step">
        <span className="create-flow-step-label">1. Slideshow</span>
        <div className="create-flow-mode-toggle">
          <label>
            <input
              type="radio"
              checked={sourceMode === 'url'}
              onChange={() => setSourceMode('url')}
              disabled={busy}
            />
            Paste a TikTok slideshow URL
          </label>
          <label>
            <input
              type="radio"
              checked={sourceMode === 'upload'}
              onChange={() => setSourceMode('upload')}
              disabled={busy}
            />
            Upload images instead
          </label>
        </div>
        {sourceMode === 'url' ? (
          <input
            type="url"
            placeholder="https://www.tiktok.com/@.../photo/..."
            value={slideshowUrl}
            onChange={(e) => setSlideshowUrl(e.target.value)}
            disabled={busy}
          />
        ) : (
          <input type="file" accept="image/*" multiple onChange={handleFilesSelected} disabled={busy} />
        )}
      </div>

      <div className="create-flow-step">
        <span className="create-flow-step-label">2. Product</span>
        <div className="create-flow-mode-toggle">
          <label>
            <input
              type="radio"
              checked={productMode === 'url'}
              onChange={() => setProductMode('url')}
              disabled={busy}
            />
            Paste a product URL
          </label>
          <label>
            <input
              type="radio"
              checked={productMode === 'existing'}
              onChange={() => setProductMode('existing')}
              disabled={busy}
            />
            Choose an existing product
          </label>
        </div>
        {productMode === 'url' ? (
          <input
            type="url"
            placeholder="https://shop.tiktok.com/..."
            value={productUrl}
            onChange={(e) => setProductUrl(e.target.value)}
            disabled={busy}
          />
        ) : (
          <select value={existingProductId} onChange={(e) => setExistingProductId(e.target.value)} disabled={busy}>
            <option value="">Select a product…</option>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.display_name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="create-flow-step">
        <span className="create-flow-step-label">3. Text</span>
        <div className="create-flow-text-strategy">
          {TEXT_STRATEGY_OPTIONS.map((option) => (
            <label key={option.value} className="create-flow-text-strategy-option">
              <input
                type="radio"
                checked={textStrategy === option.value}
                onChange={() => setTextStrategy(option.value)}
                disabled={busy}
              />
              <span>
                <strong>{option.label}</strong>
                <span className="create-flow-text-strategy-description">{option.description}</span>
              </span>
            </label>
          ))}
        </div>
      </div>

      {error && <p className="error card-error">{error}</p>}

      {busy && importedSlideCount !== null && importedSlideCount > 1 && (
        <p className="create-flow-import-confirmation">
          {importedSlideCount} source slides imported — every slide with a resolvable product will be
          generated.
        </p>
      )}

      <button className="create-flow-generate-button" onClick={handleGenerate} disabled={busy || !canGenerate}>
        {phase === 'generating' && generatingProgress
          ? `Creating your images… (${generatingProgress.current} of ${generatingProgress.total})`
          : busy
            ? PROGRESS_LABELS[phase as Exclude<Phase, 'form' | 'done' | 'error'>]
            : 'Generate'}
      </button>
    </div>
  );
}
