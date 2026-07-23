import { useState } from 'react';
import { api, type BundleView, type ListingDetail, type Product } from '../api';
import { ProductProfileFields } from './ProductManager';

interface CatalogueImporterProps {
  products: Product[];
  onProductsChanged: () => void;
}

interface MemberChoice {
  mode: 'existing' | 'new';
  existingProductId: string;
  newDisplayName: string;
}

/**
 * Phase 5.12 of the catalogue layer (see MIGRATION_PLAN.md's frozen
 * catalogue ADR). The new, unknown-URL entry point: unlike
 * ProductManager's per-product source-import form (Phase 5.7), the
 * caller here doesn't already know which Product/Bundle a URL
 * represents - resolution is always a separate, explicit human action,
 * never automatic (per the ADR's identity section), surfaced here as an
 * inline review step right after import.
 */
export function CatalogueImporter({ products, onProductsChanged }: CatalogueImporterProps) {
  const [url, setUrl] = useState('');
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listing, setListing] = useState<ListingDetail | null>(null);
  const [bundleDisplayName, setBundleDisplayName] = useState('');
  const [memberChoices, setMemberChoices] = useState<MemberChoice[]>([]);
  const [singleProductId, setSingleProductId] = useState('');
  const [singleNewName, setSingleNewName] = useState('');
  const [resolving, setResolving] = useState(false);
  const [resolvedBundleView, setResolvedBundleView] = useState<BundleView | null>(null);

  const resetReviewState = () => {
    setBundleDisplayName('');
    setMemberChoices([]);
    setSingleProductId('');
    setSingleNewName('');
    setResolvedBundleView(null);
  };

  const handleImport = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    setImporting(true);
    setError(null);
    resetReviewState();
    try {
      const imported = await api.createListingSourceImport(url.trim());
      const detail = await api.getListing(imported.id);
      setListing(detail);
      setBundleDisplayName(detail.pending_bundle_title ?? '');
      setMemberChoices(
        detail.pending_bundle_hints.map((hint) => ({
          mode: 'new' as const,
          existingProductId: '',
          newDisplayName: hint.label,
        }))
      );
      setUrl('');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setImporting(false);
    }
  };

  const handleResolveBundle = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!listing || !bundleDisplayName.trim()) return;
    setResolving(true);
    setError(null);
    try {
      const members = memberChoices.map((choice) =>
        choice.mode === 'existing'
          ? { existing_product_id: choice.existingProductId }
          : { new_product_display_name: choice.newDisplayName.trim() }
      );
      const resolved = await api.resolveListingToNewBundle(listing.id, bundleDisplayName.trim(), members);
      setListing(resolved as ListingDetail);
      onProductsChanged();
      if (resolved.resolved_bundle_id) {
        setResolvedBundleView(await api.getBundleView(resolved.resolved_bundle_id));
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setResolving(false);
    }
  };

  const handleResolveSingleProduct = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!listing) return;
    setResolving(true);
    setError(null);
    try {
      const resolved = singleProductId
        ? await api.resolveListingToExistingProduct(listing.id, singleProductId)
        : await api.resolveListingToNewProduct(listing.id, singleNewName.trim());
      setListing(resolved as ListingDetail);
      onProductsChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setResolving(false);
    }
  };

  const updateMemberChoice = (index: number, patch: Partial<MemberChoice>) => {
    setMemberChoices((prev) => prev.map((choice, i) => (i === index ? { ...choice, ...patch } : choice)));
  };

  const isResolved = listing && (listing.resolved_product_id || listing.resolved_bundle_id);
  const hasPendingBundle = listing && !isResolved && listing.pending_bundle_hints.length > 0;
  const needsSingleProductResolution = listing && !isResolved && listing.pending_bundle_hints.length === 0;

  const memberChoicesValid =
    memberChoices.length > 0 &&
    memberChoices.every((c) => (c.mode === 'existing' ? c.existingProductId : c.newDisplayName.trim()));

  return (
    <section className="catalogue-importer-section">
      <h2>Import a Listing</h2>
      <p className="catalogue-importer-intro">
        Paste any product URL - the system doesn't need to know in advance whether it's a single
        product or a bundle. You'll review and confirm what it represents below.
      </p>

      <form className="source-import-form" onSubmit={handleImport}>
        <input
          type="url"
          placeholder="Listing URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={importing}
        />
        <button type="submit" disabled={importing || !url.trim()}>
          {importing ? 'Importing…' : 'Import Listing'}
        </button>
      </form>

      {error && <p className="error card-error">{error}</p>}

      {listing && (
        <div className="listing-review-panel">
          <p className="listing-review-source">{listing.source_url}</p>

          {isResolved ? (
            <p className="listing-resolved-note">
              {listing.resolved_product_id
                ? `Resolved to product "${products.find((p) => p.id === listing.resolved_product_id)?.display_name ?? listing.resolved_product_id}".`
                : `Resolved to bundle ${listing.resolved_bundle_id}.`}
            </p>
          ) : hasPendingBundle ? (
            <form className="bundle-review-form" onSubmit={handleResolveBundle}>
              <p className="bundle-review-heading">
                This listing looks like a bundle of {listing.pending_bundle_hints.length} items -
                resolve each one below.
              </p>
              <label className="field-row">
                <span className="field-label">Bundle name</span>
                <input
                  type="text"
                  value={bundleDisplayName}
                  onChange={(e) => setBundleDisplayName(e.target.value)}
                  disabled={resolving}
                />
              </label>

              <ul className="bundle-member-list">
                {listing.pending_bundle_hints.map((hint, i) => (
                  <li key={i} className="bundle-member-row">
                    <span className="bundle-member-hint-label">{hint.label}</span>
                    <select
                      value={memberChoices[i]?.mode === 'existing' ? memberChoices[i].existingProductId : ''}
                      onChange={(e) =>
                        updateMemberChoice(i, {
                          mode: e.target.value ? 'existing' : 'new',
                          existingProductId: e.target.value,
                        })
                      }
                      disabled={resolving}
                    >
                      <option value="">Create new product…</option>
                      {products.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.display_name}
                        </option>
                      ))}
                    </select>
                    {memberChoices[i]?.mode === 'new' && (
                      <input
                        type="text"
                        placeholder="New product name"
                        value={memberChoices[i]?.newDisplayName ?? ''}
                        onChange={(e) => updateMemberChoice(i, { newDisplayName: e.target.value })}
                        disabled={resolving}
                      />
                    )}
                  </li>
                ))}
              </ul>

              <button type="submit" disabled={resolving || !bundleDisplayName.trim() || !memberChoicesValid}>
                {resolving ? 'Creating…' : 'Create Bundle'}
              </button>
            </form>
          ) : needsSingleProductResolution ? (
            <form className="single-product-review-form" onSubmit={handleResolveSingleProduct}>
              <p className="bundle-review-heading">What product does this listing represent?</p>
              <select
                value={singleProductId}
                onChange={(e) => {
                  setSingleProductId(e.target.value);
                  if (e.target.value) setSingleNewName('');
                }}
                disabled={resolving}
              >
                <option value="">Create new product…</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name}
                  </option>
                ))}
              </select>
              {!singleProductId && (
                <input
                  type="text"
                  placeholder="New product name"
                  value={singleNewName}
                  onChange={(e) => setSingleNewName(e.target.value)}
                  disabled={resolving}
                />
              )}
              <button type="submit" disabled={resolving || (!singleProductId && !singleNewName.trim())}>
                {resolving ? 'Linking…' : 'Resolve'}
              </button>
            </form>
          ) : null}

          {resolvedBundleView && <BundleViewPanel bundleView={resolvedBundleView} products={products} />}
        </div>
      )}
    </section>
  );
}

function BundleViewPanel({ bundleView, products }: { bundleView: BundleView; products: Product[] }) {
  return (
    <div className="bundle-view-panel">
      <h3>{bundleView.display_name}</h3>
      {bundleView.members.map((member) => (
        <div key={member.product_id} className="bundle-view-member">
          <h4 className="product-subsection-title">
            {products.find((p) => p.id === member.product_id)?.display_name ?? member.product_id}
            {member.quantity > 1 && <span className="prominence-badge">×{member.quantity}</span>}
          </h4>
          <ProductProfileFields
            profile={member.profile}
            emptyMessage="No evidence yet for this member - import a source URL or run analysis on a slideshow featuring it."
          />
        </div>
      ))}
    </div>
  );
}
