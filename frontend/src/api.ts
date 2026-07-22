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

  // ---------------------------------------------------------------------
  // Slideshow/Slide (new pipeline), added in Phase 2.6 of the Slideshow/
  // Slide migration as new methods alongside the old Creative-pipeline
  // ones above (rather than modifications of them). The old ones were
  // removed in Phase 2.7 once nothing used them - see the comments above.
  // ---------------------------------------------------------------------

  importSlideshows: (files: File[], projectId?: string): Promise<Slideshow[]> => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    if (projectId) formData.append('project_id', projectId);
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

  analyzeSlideshow: (slideshowId: string): Promise<AssembledSlideshowBlueprint> =>
    fetch(`/api/slideshows/${slideshowId}/analyze`, { method: 'POST' }).then((res) =>
      handle<AssembledSlideshowBlueprint>(res)
    ),

  getSlideshowBlueprint: (slideshowId: string): Promise<AssembledSlideshowBlueprint> =>
    fetch(`/api/slideshows/${slideshowId}/blueprint`).then((res) =>
      handle<AssembledSlideshowBlueprint>(res)
    ),

  rerunSlideshowStage: (
    slideshowId: string,
    stageName: string
  ): Promise<AssembledSlideshowBlueprint> =>
    fetch(`/api/slideshows/${slideshowId}/stages/${stageName}/rerun`, { method: 'POST' }).then(
      (res) => handle<AssembledSlideshowBlueprint>(res)
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
