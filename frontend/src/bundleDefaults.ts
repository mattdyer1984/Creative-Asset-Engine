import type { AssembledSlideProductBlueprint } from './api';

export interface BundleDefaultSelection {
  selectedProductIds: string[];
  roles: Record<string, string>;
}

/**
 * Phase 11.4 (see MIGRATION_PLAN.md) - mirrors the backend's own
 * resolve_primary_appearance exactly (prefer prominence == "primary",
 * tie-break by earliest (created_at, id)), so a slide with only one
 * product resolves to exactly what generate-creative would already do
 * with no bundle_members given. Extracted in Phase 11.8 so both the new
 * simplified Create flow and the existing blueprint modal compute the
 * same default from the same rule, rather than two copies that could
 * drift.
 */
export function resolveDefaultBundleSelection(
  products: AssembledSlideProductBlueprint[] | undefined
): BundleDefaultSelection {
  if (!products || products.length === 0) {
    return { selectedProductIds: [], roles: {} };
  }
  const primaryMarked = products.filter((p) => p.appearance.prominence === 'primary');
  const candidates = primaryMarked.length > 0 ? primaryMarked : products;
  const earliest = candidates.reduce((a, b) => {
    if (a.appearance.created_at !== b.appearance.created_at) {
      return a.appearance.created_at < b.appearance.created_at ? a : b;
    }
    return a.appearance.id < b.appearance.id ? a : b;
  });
  return {
    selectedProductIds: [earliest.appearance.product_id],
    roles: Object.fromEntries(
      products.map((p) => [p.appearance.product_id, p.appearance.product?.display_name ?? p.appearance.product_id])
    ),
  };
}
