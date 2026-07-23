/**
 * Minimal API client. Kept as plain fetch wrappers (no heavier client
 * library) since M0's surface area is tiny — this will likely grow into a
 * small typed client module per resource as more endpoints arrive in M1+.
 */

export interface Project {
  id: string;
  name: string;
  notes: string | null;
  created_at: string;
}

export interface ProjectCreateInput {
  name: string;
  notes?: string;
}

export interface ProductReferenceImage {
  id: string;
  // Nullable since Phase 2.3 of the Slideshow/Slide migration - rows
  // created by the new pipeline populate source_slide_id instead (not
  // exposed by this endpoint's response shape). See
  // ProductReferenceImageRead's docstring in app/schemas.py.
  source_creative_id: string | null;
  isolation_method: string;
  is_current: boolean;
  created_at: string;
}

export interface ProductLockProfile {
  id: string;
  schema_version: string;
  is_current: boolean;
  structured: Record<string, unknown>;
  reference_image_ids: string[];
  created_at: string;
  // Phase 7.4 (dependency-aware staleness, see MIGRATION_PLAN.md) -
  // computed on every fetch, never persisted; defaults match the
  // backend's ProductLockProfileRead defaults for callers (e.g.
  // GET /api/products/{id}/lock-profile) that predate this field.
  is_stale?: boolean;
  stale_because?: string[];
}

export interface Product {
  id: string;
  project_id: string | null;
  display_name: string;
  created_at: string;
}

// --- Product Intelligence (Phase 5, see MIGRATION_PLAN.md) -----------------
//
// Mirrors app/product_sources/base.py's ProductAttributeValue discriminated
// union exactly - the standing design principle (revision #4) is that the
// Product Profile is a canonical contract, not a UI convenience, so this
// stays a real typed union here too rather than collapsing to a string.

export interface TextValue {
  kind: 'text';
  text: string;
}

export interface DimensionValue {
  kind: 'dimension';
  length: number | null;
  width: number | null;
  height: number | null;
  unit: string;
}

export interface ColorValue {
  kind: 'color';
  label: string;
  hex: string | null;
}

export interface NumberValue {
  kind: 'number';
  value: number;
  unit: string | null;
}

export interface ListValue {
  kind: 'list';
  items: string[];
}

export type ProductAttributeValue = TextValue | DimensionValue | ColorValue | NumberValue | ListValue;

export interface ProductProfileField {
  value: ProductAttributeValue;
  source_type: string;
  source_id: string;
  confidence: number;
  classification: 'immutable' | 'contextual';
}

export interface ProductProfile {
  product_id: string;
  fields: Record<string, ProductProfileField>;
}

export interface ProductSourceImport {
  id: string;
  source_type: string;
  source_url: string;
  fetch_status: 'succeeded' | 'partial' | 'failed';
  error: string | null;
  is_current: boolean;
  created_at: string;
}

export interface ProductCreateInput {
  display_name: string;
  project_id?: string;
}

// --- Catalogue layer (Phase 5.8+, see MIGRATION_PLAN.md's frozen
// catalogue ADR) ------------------------------------------------------------
//
// Listing sits above Product Intelligence: it owns marketplace/commercial
// facts and resolves to either a Product or a ProductBundle. Resolution
// is never automatic - these types/methods exist to support a human
// reviewing and choosing, never inferring on their own.

export interface Listing {
  id: string;
  source_type: string;
  source_url: string;
  resolved_product_id: string | null;
  resolved_bundle_id: string | null;
  price_amount: number | null;
  price_currency: string | null;
  seller_name: string | null;
  rating: number | null;
  units_sold: number | null;
  shipping_info: string | null;
  created_at: string;
}

export interface PendingBundleMemberHint {
  label: string;
  attributes: Record<string, { value: ProductAttributeValue; confidence: number }>;
}

export interface ListingDetail extends Listing {
  pending_bundle_hints: PendingBundleMemberHint[];
  pending_bundle_title: string | null;
}

export interface BundleMemberResolutionInput {
  existing_product_id?: string;
  new_product_display_name?: string;
  quantity?: number;
}

export interface ProductBundle {
  id: string;
  project_id: string | null;
  display_name: string;
  created_at: string;
}

export interface BundleMemberProfile {
  product_id: string;
  quantity: number;
  profile: ProductProfile;
}

export interface BundleView {
  id: string;
  display_name: string;
  members: BundleMemberProfile[];
}

// CreativeBlueprint and Creative (old /api/creatives/* types) were
// removed in Phase 2.7 of the Slideshow/Slide migration - superseded by
// Slideshow/Slide below.

export interface OCRResult {
  id: string;
  schema_version: string;
  is_current: boolean;
  raw_text: string;
  structured_blocks: { text: string; role: string }[];
  created_at: string;
}

export interface CreativeFingerprintData {
  id: string;
  schema_version: string;
  is_current: boolean;
  structured: Record<string, unknown>;
  created_at: string;
  is_stale?: boolean;
  stale_because?: string[];
}

export interface MarketingAnalysisData {
  id: string;
  is_current: boolean;
  narrative_text: string;
  created_at: string;
  is_stale?: boolean;
  stale_because?: string[];
}

// Renamed from RecreationPromptData in Phase 8.1, see MIGRATION_PLAN.md.
export interface CreativeSpecificationData {
  id: string;
  schema_version: string;
  is_current: boolean;
  product_lock_profile_id: string;
  creative_fingerprint_id: string;
  structured: Record<string, unknown>;
  created_at: string;
  is_stale?: boolean;
  stale_because?: string[];
}

// Phase 8.3 of the Generation -> Validation proof of loop, see
// MIGRATION_PLAN.md. No is_stale/stale_because - a generated image is a
// point-in-time output, not something that goes stale relative to its
// own inputs the way an analysis artifact does.
export interface GeneratedImageData {
  id: string;
  schema_version: string;
  is_current: boolean;
  slide_id: string;
  creative_specification_id: string;
  provider: string;
  model_name: string;
  prompt_used: string;
  seed: string | null;
  generation_time_seconds: number;
  created_at: string;
}

// Phase 8.4 - field_checks is surfaced directly, not summarized, so the
// UI can show exactly why a generated image passed or failed.
export interface ImageValidationFieldCheck {
  field_name: string;
  preserved: boolean;
  reason: string;
}

export interface ImageValidationResultData {
  id: string;
  schema_version: string;
  is_current: boolean;
  generated_image_id: string;
  product_id: string;
  passed: boolean;
  field_checks: ImageValidationFieldCheck[];
  overall_explanation: string;
  created_at: string;
}

// Phase 7.2 (Narrative pass, see MIGRATION_PLAN.md) - structured is
// {slides: [{slide_id, slide_index, beat}], arc_summary}.
export interface NarrativeStructureData {
  id: string;
  schema_version: string;
  is_current: boolean;
  structured: {
    slides: { slide_id: string; slide_index: number; beat: string }[];
    arc_summary: string;
  };
  created_at: string;
  is_stale?: boolean;
  stale_because?: string[];
}

// AssembledCreativeBlueprint (old /api/creatives/*'s single-response
// view) was removed in Phase 2.7 of the Slideshow/Slide migration -
// superseded by AssembledSlideshowBlueprint below.

// Phase 8.5 (see MIGRATION_PLAN.md) - a 404 here means "nothing generated/
// validated yet", an expected, common state for a fresh slide, not an
// error to surface - resolves to null instead of throwing.
async function handleOptional<T>(res: Response): Promise<T | null> {
  if (res.status === 404) return null;
  return handle<T>(res);
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Request failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listProjects: (): Promise<Project[]> =>
    fetch('/api/projects').then((res) => handle<Project[]>(res)),

  createProject: (input: ProjectCreateInput): Promise<Project> =>
    fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }).then((res) => handle<Project>(res)),

  // importLocalFiles/listCreatives/creativeFileUrl/analyzeCreative/
  // getCreativeBlueprint/rerunStage/getOcrResult/getCreativeFingerprint/
  // getMarketingAnalysis/getRecreationPrompt/listAnalysisRuns (old
  // /api/creatives/* methods) were removed in Phase 2.7 of the
  // Slideshow/Slide migration - superseded by importSlideshows/
  // listSlideshows/slideFileUrl/analyzeSlideshow/getSlideshowBlueprint/
  // rerunSlideshowStage further down this file.

  createProduct: (input: ProductCreateInput): Promise<Product> =>
    fetch('/api/products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }).then((res) => handle<Product>(res)),

  listProducts: (): Promise<Product[]> =>
    fetch('/api/products').then((res) => handle<Product[]>(res)),

  // assignProduct (old, Creative-level) was removed in Phase 2.7 -
  // superseded by assignSlideProduct further down this file.

  listReferenceImages: (productId: string): Promise<ProductReferenceImage[]> =>
    fetch(`/api/products/${productId}/reference-images`).then((res) =>
      handle<ProductReferenceImage[]>(res)
    ),

  referenceImageFileUrl: (productId: string, referenceImageId: string): string =>
    `/api/products/${productId}/reference-images/${referenceImageId}/file`,

  getLockProfile: (productId: string): Promise<ProductLockProfile> =>
    fetch(`/api/products/${productId}/lock-profile`).then((res) =>
      handle<ProductLockProfile>(res)
    ),

  // Product Intelligence (Phase 5.6, see MIGRATION_PLAN.md). Synchronous
  // (200, not 202) - a single fetch+parse is done by the time the response
  // is sent, unlike Slideshow analysis's backgrounded pipeline.
  createSourceImport: (productId: string, url: string): Promise<ProductSourceImport> =>
    fetch(`/api/products/${productId}/source-import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    }).then((res) => handle<ProductSourceImport>(res)),

  getProductProfile: (productId: string): Promise<ProductProfile> =>
    fetch(`/api/products/${productId}/profile`).then((res) => handle<ProductProfile>(res)),

  // Catalogue layer (Phase 5.11, see MIGRATION_PLAN.md's frozen catalogue
  // ADR) - the unknown-URL entry point. Unlike createSourceImport above,
  // the caller doesn't already know which Product/Bundle a URL is about;
  // resolution is a separate, always-explicit step via the resolve*
  // methods below.
  createListingSourceImport: (url: string): Promise<Listing> =>
    fetch('/api/listings/source-import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    }).then((res) => handle<Listing>(res)),

  getListing: (listingId: string): Promise<ListingDetail> =>
    fetch(`/api/listings/${listingId}`).then((res) => handle<ListingDetail>(res)),

  resolveListingToExistingProduct: (listingId: string, productId: string): Promise<Listing> =>
    fetch(`/api/listings/${listingId}/resolve-existing-product`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId }),
    }).then((res) => handle<Listing>(res)),

  resolveListingToNewProduct: (listingId: string, displayName: string): Promise<Listing> =>
    fetch(`/api/listings/${listingId}/resolve-new-product`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName }),
    }).then((res) => handle<Listing>(res)),

  resolveListingToExistingBundle: (listingId: string, bundleId: string): Promise<Listing> =>
    fetch(`/api/listings/${listingId}/resolve-existing-bundle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bundle_id: bundleId }),
    }).then((res) => handle<Listing>(res)),

  resolveListingToNewBundle: (
    listingId: string,
    displayName: string,
    members: BundleMemberResolutionInput[]
  ): Promise<Listing> =>
    fetch(`/api/listings/${listingId}/resolve-new-bundle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName, members }),
    }).then((res) => handle<Listing>(res)),

  getBundleView: (bundleId: string): Promise<BundleView> =>
    fetch(`/api/bundles/${bundleId}`).then((res) => handle<BundleView>(res)),

  // ---------------------------------------------------------------------
  // Slideshow/Slide (new pipeline), added in Phase 2.6 of the Slideshow/
  // Slide migration as new methods alongside the old Creative-pipeline
  // ones above (rather than modifications of them). The old ones were
  // removed in Phase 2.7 once nothing used them - see the comments above.
  // ---------------------------------------------------------------------

  // groupAsOne (Phase 4 - true multi-slide import, see MIGRATION_PLAN.md):
  // default false preserves existing behavior (every file becomes its
  // own independent Slideshow). true imports every file in this one call
  // as a single Slideshow's ordered Slides instead.
  importSlideshows: (
    files: File[],
    projectId?: string,
    groupAsOne?: boolean
  ): Promise<Slideshow[]> => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    if (projectId) formData.append('project_id', projectId);
    if (groupAsOne) formData.append('group_as_one', 'true');
    return fetch('/api/slideshows/import', {
      method: 'POST',
      body: formData,
    }).then((res) => handle<Slideshow[]>(res));
  },

  listSlideshows: (projectId?: string): Promise<Slideshow[]> => {
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
    return fetch(`/api/slideshows${query}`).then((res) => handle<Slideshow[]>(res));
  },

  slideFileUrl: (slideshowId: string, slideId: string): string =>
    `/api/slideshows/${slideshowId}/slides/${slideId}/file`,

  // Schedules analysis in the background and returns as soon as status
  // flips to "queued" (202 Accepted) - Phase 3.2 of the async execution
  // boundary work (see MIGRATION_PLAN.md). No longer returns the full
  // blueprint, since none of its analysis content exists yet at this
  // point - callers should poll getSlideshowBlueprint/listSlideshows
  // while status is "queued"/"analyzing".
  analyzeSlideshow: (slideshowId: string): Promise<Slideshow> =>
    fetch(`/api/slideshows/${slideshowId}/analyze`, { method: 'POST' }).then((res) =>
      handle<Slideshow>(res)
    ),

  getSlideshowBlueprint: (slideshowId: string): Promise<AssembledSlideshowBlueprint> =>
    fetch(`/api/slideshows/${slideshowId}/blueprint`).then((res) =>
      handle<AssembledSlideshowBlueprint>(res)
    ),

  // Same shape as analyzeSlideshow (Phase 3.3 - see MIGRATION_PLAN.md):
  // schedules the stage in the background and returns immediately with
  // status=queued, not the finished blueprint.
  rerunSlideshowStage: (slideshowId: string, stageName: string): Promise<Slideshow> =>
    fetch(`/api/slideshows/${slideshowId}/stages/${stageName}/rerun`, { method: 'POST' }).then(
      (res) => handle<Slideshow>(res)
    ),

  // Phase 8.3 (Generation -> Validation proof of loop, see
  // MIGRATION_PLAN.md) - deliberately synchronous (unlike
  // analyzeSlideshow/rerunSlideshowStage above), so this resolves with
  // the finished GeneratedImageData directly, not a queued status to poll.
  generateImage: (slideshowId: string, slideId: string): Promise<GeneratedImageData> =>
    fetch(`/api/slideshows/${slideshowId}/slides/${slideId}/generate-image`, {
      method: 'POST',
    }).then((res) => handle<GeneratedImageData>(res)),

  generatedImageFileUrl: (slideshowId: string, generatedImageId: string): string =>
    `/api/slideshows/${slideshowId}/generated-images/${generatedImageId}/file`,

  // Phase 8.5 - lets the modal show a slide's already-generated image on
  // open without spending a real, paid regeneration call just to check.
  getCurrentGeneratedImage: (
    slideshowId: string,
    slideId: string
  ): Promise<GeneratedImageData | null> =>
    fetch(`/api/slideshows/${slideshowId}/slides/${slideId}/generated-image`).then((res) =>
      handleOptional<GeneratedImageData>(res)
    ),

  // Phase 8.4 - also synchronous, resolves with the finished
  // ImageValidationResultData directly.
  validateGeneratedImage: (
    slideshowId: string,
    generatedImageId: string
  ): Promise<ImageValidationResultData> =>
    fetch(`/api/slideshows/${slideshowId}/generated-images/${generatedImageId}/validate`, {
      method: 'POST',
    }).then((res) => handle<ImageValidationResultData>(res)),

  getCurrentValidationResult: (
    slideshowId: string,
    generatedImageId: string
  ): Promise<ImageValidationResultData | null> =>
    fetch(`/api/slideshows/${slideshowId}/generated-images/${generatedImageId}/validation`).then(
      (res) => handleOptional<ImageValidationResultData>(res)
    ),

  // productId: null unassigns.
  assignSlideProduct: (
    slideshowId: string,
    slideId: string,
    productId: string | null
  ): Promise<Slideshow> =>
    fetch(`/api/slideshows/${slideshowId}/slides/${slideId}/assign-product`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId }),
    }).then((res) => handle<Slideshow>(res)),

  // Additive, multi-product endpoints (Phase 6.1, see MIGRATION_PLAN.md) -
  // unlike assignSlideProduct above, adding a second product doesn't
  // replace the first. addSlideProduct is idempotent: re-adding an
  // already-current product no-ops rather than duplicating.
  addSlideProduct: (slideshowId: string, slideId: string, productId: string): Promise<Slideshow> =>
    fetch(`/api/slideshows/${slideshowId}/slides/${slideId}/products`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId }),
    }).then((res) => handle<Slideshow>(res)),

  removeSlideProduct: (
    slideshowId: string,
    slideId: string,
    appearanceId: string
  ): Promise<Slideshow> =>
    fetch(`/api/slideshows/${slideshowId}/slides/${slideId}/products/${appearanceId}`, {
      method: 'DELETE',
    }).then((res) => handle<Slideshow>(res)),
};

export interface SlideProductAppearance {
  id: string;
  product_id: string;
  product: Product | null;
  prominence: string;
  confidence: number;
  is_current: boolean;
  created_at: string;
}

export interface Slide {
  id: string;
  slideshow_id: string;
  slide_index: number;
  original_filename: string;
  source_type: string;
  source_locator: string;
  current_product_appearance: SlideProductAppearance | null;
  // Phase 6.5 (multi per-slide product detection, see MIGRATION_PLAN.md) -
  // additive alongside the unchanged singular field above.
  current_product_appearances: SlideProductAppearance[];
}

export interface Slideshow {
  id: string;
  project_id: string | null;
  imported_at: string;
  status: string;
  slides: Slide[];
}

export interface SlideProductReferenceImage {
  id: string;
  source_slide_id: string;
  isolation_method: string;
  is_current: boolean;
  created_at: string;
}

// Phase 6.4 (multi per-slide product detection, see MIGRATION_PLAN.md):
// one product's full artifact set on a slide. Replaces the old flat
// product_reference_images/product_lock_profile fields on
// AssembledSlideBlueprint, which only ever showed data for
// product_appearances[0] - a slide with 2+ current products now gets
// one of these per product.
export interface AssembledSlideProductBlueprint {
  appearance: SlideProductAppearance;
  product_reference_images: SlideProductReferenceImage[];
  product_lock_profile: ProductLockProfile | null;
}

export interface AssembledSlideBlueprint {
  id: string;
  slide_index: number;
  original_filename: string;
  source_type: string;
  source_locator: string;
  ocr_result: OCRResult | null;
  creative_fingerprint: CreativeFingerprintData | null;
  products: AssembledSlideProductBlueprint[];
}

export interface AssembledSlideshowBlueprint {
  id: string;
  status: string;
  imported_at: string;
  project_id: string | null;
  source_references: Record<string, unknown>;
  slides: AssembledSlideBlueprint[];
  marketing_analysis: MarketingAnalysisData | null;
  narrative_structure: NarrativeStructureData | null;
  creative_specification: CreativeSpecificationData | null;
  failed_stage: string | null;
  failed_stage_error: string | null;
}
