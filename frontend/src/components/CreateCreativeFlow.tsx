import { useEffect, useState } from 'react';
import { resolveDefaultBundleSelection } from '../bundleDefaults';
import {
  api,
  type GenerateCreativeRequest,
  type GenerateCreativeResponseData,
  type Product,
  type ProductReferenceImage,
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
//
// Real bug found live (see MIGRATION_PLAN.md): the backend scores every
// candidate image strictly sequentially (reference_scoring_stage.py's
// own run_reference_scoring, a plain for loop - the same-role
// duplicate/supersede check has a real ordering dependency between
// candidates, so it isn't safe to blindly parallelize), and each
// candidate costs 1-2 real vision calls. Under real, observed API
// latency (10-19s per call seen live this session) a handful of
// candidates can genuinely take 60-90+ seconds - the old 15s window
// (10 * 1500ms) gave up and showed "couldn't build a usable reference
// image" even though scoring was still correctly running and would
// have succeeded seconds later, confirmed live via direct DB
// inspection. Widened, not just because "more is safer" - to actually
// cover the real, measured worst case.
const REFERENCE_SCORING_POLL_ATTEMPTS = 60;
const REFERENCE_SCORING_POLL_INTERVAL_MS = 1500;

// The main analysis poll below used to have no cap at all, unlike every
// other poller in this file - it only had terminal-state detection
// ('ready'/'failed'), so a Slideshow that (through a backend bug) never
// reached either would spin this loop forever with no visible error.
// 200 * 1500ms = 5 minutes, generous relative to any real analysis run
// observed so far, while still guaranteeing the user sees *something*.
const ANALYSIS_POLL_ATTEMPTS = 200;
const ANALYSIS_POLL_INTERVAL_MS = 1500;

// Real-world-diagnosed speed fix (see MIGRATION_PLAN.md) - Generate All
// used to await api.generateCreative one slide at a time; real timing
// data showed each call taking ~70-125s, so a 4-slide slideshow took
// 5-8 minutes end to end. Each generate-creative call is a fully
// independent HTTP request (its own backend DB session, its own
// product/spec resolution - proven by §0's fix), so running several at
// once is safe. Bounded rather than fully unlimited (Promise.all across
// every slide) on purpose: the backend is plain SQLite with no unusual
// write-concurrency tuning, and the AI providers have their own real
// rate limits - a small, fixed concurrency cap gets most of the
// wall-clock win without hammering either.
const GENERATE_ALL_CONCURRENCY = 3;

// Runs `fn` over `items` with at most `limit` in flight at once,
// returning results in the SAME order as `items` regardless of which
// one finishes first - a plain worker-pool, not `items.map` wrapped in
// a concurrency library, since this is the only place in the codebase
// that needs bounded parallelism.
async function mapWithConcurrency<T, R>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<R>,
  onItemDone?: (completedCount: number) => void
): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let nextIndex = 0;
  let completedCount = 0;

  async function worker() {
    while (nextIndex < items.length) {
      const current = nextIndex;
      nextIndex += 1;
      results[current] = await fn(items[current], current);
      completedCount += 1;
      onItemDone?.(completedCount);
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
  return results;
}

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
/**
 * Why reference building failed, in terms the user can act on.
 *
 * This used to be one sentence for every cause: "We couldn't build a
 * usable reference image for this product." That covered at least six
 * genuinely different situations - nothing downloaded, nothing detected,
 * scoring still running, scoring never ran, every crop scored too low,
 * provider failure - and told the user which one applied in none of
 * them. The single most common real case (crops rejected because
 * promotional text covered the product) is fixable in seconds if you
 * know that is what happened.
 */
function describeReferenceFailure(images: ProductReferenceImage[]): string {
  if (images.length === 0) {
    return (
      'We could not find any usable product imagery. No images were downloaded from the ' +
      'product URL, and no product was detected in the slideshow. Add a clear product photo ' +
      'in Advanced mode and we will use the slideshow for composition only.'
    );
  }

  const unscored = images.filter((image) => image.library_status === null);
  if (unscored.length === images.length) {
    return (
      `Reference scoring did not complete for any of the ${images.length} candidate image(s) - ` +
      'this usually means the AI provider returned an error. Your slideshow is saved; try again ' +
      'in a moment.'
    );
  }

  const rejected = images.filter((image) => image.library_status === 'rejected');
  if (rejected.length > 0) {
    const best = rejected.reduce((a, b) => ((a.quality_score ?? 0) >= (b.quality_score ?? 0) ? a : b));
    const reasons = (best.quality_reasons_json ?? [])
      .filter((reason) => !/^\d+x\d+|^role:|^composition:/.test(reason))
      .slice(0, 3);
    const detail = reasons.length > 0 ? ` Reasons: ${reasons.join('; ')}.` : '';
    return (
      `All ${images.length} candidate reference image(s) scored below the quality bar ` +
      `(best ${(best.quality_score ?? 0).toFixed(2)}, needed 0.50).${detail} ` +
      'This usually means the product is partly covered by on-screen text in the slideshow. ' +
      'Add one clean product photo in Advanced mode and we will use the slideshow for ' +
      'composition only.'
    );
  }

  return (
    `None of the ${images.length} candidate reference image(s) could be used for this product. ` +
    'Add a clear front image, and an angled or side image, in Advanced mode.'
  );
}

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
  // attempts every imported slide, not just the primary one. Story Slide
  // feature (see MIGRATION_PLAN.md): a slide with no resolvable product
  // is no longer a per-slide failure - the backend recreates it as an
  // original story/narrative shot instead. A per-slide failure can still
  // happen for other reasons (e.g. a genuine analysis-stage error), and
  // is still shown honestly in the results carousel rather than hidden.
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

  const hasSource =
    sourceMode === 'url' ? slideshowUrl.trim().length > 0 : uploadFiles.length > 0;
  const hasProduct =
    productMode === 'url' ? productUrl.trim().length > 0 : existingProductId.length > 0;

  const canGenerate = hasSource && hasProduct;

  // Say WHICH step is incomplete. A greyed-out button with a filled-in
  // slideshow field reads as "it rejected my link" - the link was fine, the
  // product step below it was empty, and nothing on screen said so.
  const missingSteps = [
    !hasSource && (sourceMode === 'url' ? 'a slideshow URL' : 'at least one image'),
    !hasProduct && (productMode === 'url' ? 'a product URL' : 'an existing product'),
  ].filter(Boolean) as string[];

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
      // Real-world-diagnosed fix (Generate All follow-up, see
      // MIGRATION_PLAN.md): there is no automatic per-slide product
      // detection anywhere in this codebase - Product Isolation/Lock
      // Profile only ever process a slide's EXISTING appearances, they
      // never discover new ones. Assigning the chosen product only to
      // the primary slide (the old behavior) meant every other slide
      // permanently had zero appearances, so Generate All's own
      // generate-creative call for those slides 422'd with "No product
      // assigned to this slide yet" every single time - confirmed live.
      // The common case for this simplified flow is one product
      // (or one bundle) advertised across the whole slideshow, so the
      // resolved product id(s) are assigned to every imported slide,
      // not just the primary one.
      const productIdsToAssign: string[] = [];
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
          productIdsToAssign.push(detail.resolved_product_id);
        } else if (detail.resolved_bundle_id) {
          const bundleView = await api.getBundleView(detail.resolved_bundle_id);
          productIdsToAssign.push(...bundleView.members.map((member) => member.product_id));
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
          productIdsToAssign.push(...bundleView.members.map((member) => member.product_id));
        } else {
          const resolved = await api.resolveListingToNewProduct(
            listing.id,
            detail.pending_product_title ?? 'New Product'
          );
          if (!resolved.resolved_product_id) throw new Error("Couldn't resolve the product.");
          productIdsToAssign.push(resolved.resolved_product_id);
        }
      } else {
        productIdsToAssign.push(existingProductId);
      }
      for (const slide of slideshow.slides) {
        for (const productId of productIdsToAssign) {
          await api.addSlideProduct(slideshow.id, slide.id, productId);
        }
      }

      setPhase('analyzing');
      await api.analyzeSlideshow(slideshow.id);
      let blueprint = await api.getSlideshowBlueprint(slideshow.id);
      let analysisPollAttempts = 0;
      while (
        (blueprint.status === 'queued' || blueprint.status === 'analyzing') &&
        analysisPollAttempts < ANALYSIS_POLL_ATTEMPTS
      ) {
        await sleep(ANALYSIS_POLL_INTERVAL_MS);
        blueprint = await api.getSlideshowBlueprint(slideshow.id);
        analysisPollAttempts += 1;
      }
      if (blueprint.status === 'queued' || blueprint.status === 'analyzing') {
        throw new Error(
          "Analysis is taking longer than expected. It may still finish in the background - check the slideshow again in a few minutes, or try re-running it."
        );
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
          throw new Error(describeReferenceFailure(images));
        }
      }

      setPhase('generating');
      setGeneratingProgress({ current: 0, total: blueprint.slides.length });
      const outcomes = await mapWithConcurrency(
        blueprint.slides,
        GENERATE_ALL_CONCURRENCY,
        async (slide, i): Promise<SlideGenerationOutcome> => {
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
            return { slideId: slide.id, response, error: null, regenerateRequest: request };
          } catch (err) {
            return {
              slideId: slide.id,
              response: null,
              error: (err as Error).message,
              regenerateRequest: request,
            };
          }
        },
        (completedCount) => setGeneratingProgress({ current: completedCount, total: blueprint.slides.length })
      );

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
          {importedSlideCount} source slides imported and will each be generated — slides showing your
          product are recreated with it; other slides are recreated as original story/narrative shots.
        </p>
      )}

      <button className="create-flow-generate-button" onClick={handleGenerate} disabled={busy || !canGenerate}>
        {phase === 'generating' && generatingProgress
          ? `Creating your images… (${generatingProgress.current} of ${generatingProgress.total})`
          : busy
            ? PROGRESS_LABELS[phase as Exclude<Phase, 'form' | 'done' | 'error'>]
            : 'Generate'}
      </button>

      {!busy && missingSteps.length > 0 && (
        <p className="create-flow-missing-steps">
          Still needed: {missingSteps.join(' and ')}.
        </p>
      )}
    </div>
  );
}
