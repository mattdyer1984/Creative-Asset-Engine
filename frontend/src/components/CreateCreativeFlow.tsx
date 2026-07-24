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
  generating: 'Creating your image…',
};

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
  const [result, setResult] = useState<GenerateCreativeResponseData | null>(null);
  const [resultSlideshowId, setResultSlideshowId] = useState<string | null>(null);
  const [resultSlideId, setResultSlideId] = useState<string | null>(null);
  // The exact request generateCreative was called with - Regenerate (Phase
  // 12.6) re-invokes the same call rather than guessing settings back out
  // of the response.
  const [resultRequest, setResultRequest] = useState<GenerateCreativeRequest | null>(null);
  // Critical TikTok Slideshow Import Fix (see MIGRATION_PLAN.md) - the
  // required pre-generation confirmation. Set once import succeeds (so
  // it reflects the real, gate-verified slide count, not a guess) and
  // shown for the rest of the flow. Generation is still scoped to the
  // primary slide only (an unchanged, deliberate boundary - see Phase
  // 8), so this deliberately says so rather than implying every
  // imported slide gets generated.
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
    setResult(null);
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
        const listing = await api.createListingSourceImport(productUrl.trim());
        const detail = await api.getListing(listing.id);
        if (detail.pending_bundle_hints.length > 0) {
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
      // this step was added. Runs for every product the generation will
      // actually use, not just the primary one, so Bundle Composition
      // scenes aren't left with an empty Library for a secondary member.
      setPhase('building_references');
      const { selectedProductIds, roles } = resolveDefaultBundleSelection(blueprint.slides[0]?.products);
      for (const productId of selectedProductIds) {
        await api.scoreReferences(productId);
      }
      for (const productId of selectedProductIds) {
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
      const generated = await api.generateCreative(slideshow.id, primarySlideId, request);

      setResult(generated);
      setResultSlideshowId(slideshow.id);
      setResultSlideId(primarySlideId);
      setResultRequest(request);
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
    setResult(null);
    setResultSlideshowId(null);
    setResultSlideId(null);
    setResultRequest(null);
    setShowAdvancedModal(false);
    setImportedSlideCount(null);
  };

  if (phase === 'done' && result && resultSlideshowId && resultSlideId && resultRequest) {
    return (
      <>
        <GenerationResultsModal
          slideshowId={resultSlideshowId}
          slideId={resultSlideId}
          initialResult={result}
          regenerateRequest={resultRequest}
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
          {importedSlideCount} source slides imported — the primary slide will be generated.
        </p>
      )}

      <button className="create-flow-generate-button" onClick={handleGenerate} disabled={busy || !canGenerate}>
        {busy ? PROGRESS_LABELS[phase as Exclude<Phase, 'form' | 'done' | 'error'>] : 'Generate'}
      </button>
    </div>
  );
}
