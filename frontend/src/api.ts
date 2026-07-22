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
}

export interface MarketingAnalysisData {
  id: string;
  is_current: boolean;
  narrative_text: string;
  created_at: string;
}

export interface RecreationPromptData {
  id: string;
  schema_version: string;
  is_current: boolean;
  product_lock_profile_id: string;
  creative_fingerprint_id: string;
  structured: Record<string, unknown>;
  created_at: string;
}

// AssembledCreativeBlueprint (old /api/creatives/*'s single-response
// view) was removed in Phase 2.7 of the Slideshow/Slide migration -
// superseded by AssembledSlideshowBlueprint below.

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

export interface AssembledSlideBlueprint {
  id: string;
  slide_index: number;
  original_filename: string;
  source_type: string;
  source_locator: string;
  ocr_result: OCRResult | null;
  creative_fingerprint: CreativeFingerprintData | null;
  product_appearances: SlideProductAppearance[];
  product_reference_images: SlideProductReferenceImage[];
  product_lock_profile: ProductLockProfile | null;
}

export interface AssembledSlideshowBlueprint {
  id: string;
  status: string;
  imported_at: string;
  project_id: string | null;
  source_references: Record<string, unknown>;
  slides: AssembledSlideBlueprint[];
  marketing_analysis: MarketingAnalysisData | null;
  recreation_prompt: RecreationPromptData | null;
  failed_stage: string | null;
  failed_stage_error: string | null;
}
