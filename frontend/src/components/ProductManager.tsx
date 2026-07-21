import { useEffect, useState } from 'react';
import { api, type Product, type ProductLockProfile, type ProductReferenceImage } from '../api';

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
 * reference images + Product Lock Profile, once M4's Stages have
 * produced them - deliberately minimal (raw JSON, not a designed view),
 * since the real assembled Blueprint UX is M7's job. This exists only to
 * prove the Stages' output is reachable and correct.
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listReferenceImages(productId)
      .then(setReferenceImages)
      .catch((err) => setError(err.message));
    api
      .getLockProfile(productId)
      .then(setLockProfile)
      .catch(() => setLockProfile('none'));
  }, [productId]);

  return (
    <div className="product-analysis-panel">
      {error && <p className="error">{error}</p>}

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

      {lockProfile === null ? (
        <p>Loading lock profile…</p>
      ) : lockProfile === 'none' ? (
        <p className="empty-state">No Product Lock Profile generated yet.</p>
      ) : (
        <pre className="lock-profile-json">{JSON.stringify(lockProfile.structured, null, 2)}</pre>
      )}
    </div>
  );
}
