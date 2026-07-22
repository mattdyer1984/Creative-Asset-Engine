import { useEffect, useState } from 'react';
import {
  api,
  type Product,
  type ProductAttributeValue,
  type ProductLockProfile,
  type ProductProfile,
  type ProductReferenceImage,
  type ProductSourceImport,
} from '../api';

interface ProductManagerProps {
  products: Product[];
  loading: boolean;
  onCreated: () => void;
}

/**
 * Mirrors the Projects section's shape (list + inline create form) since
 * Product is, like Project, an optional-parent entity a Creative can be
 * linked to - see plan §1, §7.
 *
 * Each product also gets a "View Analysis" toggle showing its current
 * reference images, a Product Source URL import form, and the assembled
 * Product Profile (Phase 5 of Product Intelligence, see
 * MIGRATION_PLAN.md) - the canonical, provenance-tagged merge of every
 * evidence source. The raw ProductLockProfile view from M4 stays as a
 * secondary "raw evidence" detail, collapsed by default - the Product
 * Profile is the primary view now, per the standing design principle
 * that the profile (not this UI) is the canonical contract.
 */
export function ProductManager({ products, loading, onCreated }: ProductManagerProps) {
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedProductId, setExpandedProductId] = useState<string | null>(null);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createProduct({ display_name: newName.trim() });
      setNewName('');
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <section className="products-section">
      <h2>Products</h2>
      <form className="create-product-form" onSubmit={handleCreate}>
        <input
          type="text"
          placeholder="New product name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          disabled={creating}
        />
        <button type="submit" disabled={creating || !newName.trim()}>
          {creating ? 'Creating…' : 'Create Product'}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {loading ? (
        <p>Loading products…</p>
      ) : products.length === 0 ? (
        <p className="empty-state">
          No products yet. Products let the Product Lock Profile stay
          consistent across every creative that features them.
        </p>
      ) : (
        <ul className="product-list">
          {products.map((product) => (
            <li key={product.id} className="product-list-item">
              <div className="product-list-row">
                <span>{product.display_name}</span>
                <button
                  className="view-analysis-button"
                  onClick={() =>
                    setExpandedProductId(expandedProductId === product.id ? null : product.id)
                  }
                >
                  {expandedProductId === product.id ? 'Hide' : 'View'} Analysis
                </button>
              </div>
              {expandedProductId === product.id && <ProductAnalysisPanel productId={product.id} />}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ProductAnalysisPanel({ productId }: { productId: string }) {
  const [referenceImages, setReferenceImages] = useState<ProductReferenceImage[] | null>(null);
  const [lockProfile, setLockProfile] = useState<ProductLockProfile | 'none' | null>(null);
  const [profile, setProfile] = useState<ProductProfile | null>(null);
  const [sourceUrl, setSourceUrl] = useState('');
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [lastImport, setLastImport] = useState<ProductSourceImport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProfile = () => {
    api.getProductProfile(productId).then(setProfile).catch((err) => setError(err.message));
  };

  useEffect(() => {
    api
      .listReferenceImages(productId)
      .then(setReferenceImages)
      .catch((err) => setError(err.message));
    api
      .getLockProfile(productId)
      .then(setLockProfile)
      .catch(() => setLockProfile('none'));
    loadProfile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId]);

  const handleImportSource = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!sourceUrl.trim()) return;
    setImporting(true);
    setImportError(null);
    try {
      const result = await api.createSourceImport(productId, sourceUrl.trim());
      setLastImport(result);
      setSourceUrl('');
      loadProfile();
    } catch (err) {
      setImportError((err as Error).message);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="product-analysis-panel">
      {error && <p className="error">{error}</p>}

      <form className="source-import-form" onSubmit={handleImportSource}>
        <input
          type="url"
          placeholder="Product URL (e.g. official listing)"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
          disabled={importing}
        />
        <button type="submit" disabled={importing || !sourceUrl.trim()}>
          {importing ? 'Importing…' : 'Import from URL'}
        </button>
      </form>
      {importError && <p className="error card-error">{importError}</p>}
      {lastImport?.fetch_status === 'failed' && (
        <p className="section-error">Import failed: {lastImport.error}</p>
      )}

      <div className="reference-images-row">
        {referenceImages === null ? (
          <p>Loading reference images…</p>
        ) : referenceImages.length === 0 ? (
          <p className="empty-state">No reference images yet.</p>
        ) : (
          referenceImages.map((img) => (
            <img
              key={img.id}
              src={api.referenceImageFileUrl(productId, img.id)}
              alt="Product reference"
              className="reference-image-thumbnail"
            />
          ))
        )}
      </div>

      <div className="product-profile">
        <h4>Product Profile</h4>
        {profile === null ? (
          <p>Loading profile…</p>
        ) : Object.keys(profile.fields).length === 0 ? (
          <p className="empty-state">
            No evidence yet - import a source URL above, or run analysis on a slideshow featuring
            this product.
          </p>
        ) : (
          <div className="field-grid">
            {Object.entries(profile.fields).map(([fieldName, field]) => (
              <div key={fieldName} className="field-row profile-field-row">
                <span className="field-label">{fieldName.replace(/_/g, ' ')}</span>
                <span className="field-value">
                  <AttributeValueDisplay value={field.value} />
                  <span className={`classification-badge classification-${field.classification}`}>
                    {field.classification}
                  </span>
                  <span className="confidence-badge">
                    {field.source_type} · {Math.round(field.confidence * 100)}%
                  </span>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {lockProfile !== null && lockProfile !== 'none' && (
        <details className="raw-evidence-details">
          <summary>Raw slideshow-derived evidence</summary>
          <pre className="lock-profile-json">{JSON.stringify(lockProfile.structured, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

// Renders each ProductAttributeValue shape appropriately (Phase 5.7,
// applying the standing design principle: the typed structure exists
// specifically so it can be shown as more than a flattened string - a
// color swatch for ColorValue, not just its label).
function AttributeValueDisplay({ value }: { value: ProductAttributeValue }) {
  switch (value.kind) {
    case 'text':
      return <span>{value.text}</span>;
    case 'color':
      return (
        <span className="attribute-color-value">
          {value.hex && <span className="color-swatch" style={{ backgroundColor: value.hex }} />}
          {value.label}
        </span>
      );
    case 'dimension': {
      const parts = [value.length, value.width, value.height].filter((n) => n != null);
      return (
        <span>
          {parts.join(' × ')} {value.unit}
        </span>
      );
    }
    case 'number':
      return (
        <span>
          {value.value}
          {value.unit ? ` ${value.unit}` : ''}
        </span>
      );
    case 'list':
      return (
        <span className="tag-list">
          {value.items.map((item, i) => (
            <span key={i} className="tag">
              {item}
            </span>
          ))}
        </span>
      );
  }
}
