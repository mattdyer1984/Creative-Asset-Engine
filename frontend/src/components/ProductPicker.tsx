import { useState } from 'react';
import { api, type Product } from '../api';

interface ProductPickerProps {
  creativeId: string;
  currentProduct: Product | null;
  products: Product[];
  onChanged: () => void;
}

/**
 * The "new product or existing?" prompt from the plan's workflow (§11,
 * step 1) - implemented as an always-visible per-card control rather
 * than a blocking modal at import time, since a Creative's product
 * assignment doesn't need to happen before anything else can proceed
 * (product_id is nullable throughout - plan §7). Simpler UX, same end
 * state.
 */
export function ProductPicker({ creativeId, currentProduct, products, onChanged }: ProductPickerProps) {
  const [creatingNew, setCreatingNew] = useState(false);
  const [newProductName, setNewProductName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSelectExisting = async (productId: string) => {
    if (!productId) return;
    setBusy(true);
    setError(null);
    try {
      await api.assignProduct(creativeId, productId);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleUnassign = async () => {
    setBusy(true);
    try {
      await api.assignProduct(creativeId, null);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleCreateAndAssign = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newProductName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const product = await api.createProduct({ display_name: newProductName.trim() });
      await api.assignProduct(creativeId, product.id);
      setNewProductName('');
      setCreatingNew(false);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (currentProduct) {
    return (
      <div className="product-picker">
        <span className="assigned-product">Product: {currentProduct.display_name}</span>
        <button className="unassign-button" onClick={handleUnassign} disabled={busy}>
          Unassign
        </button>
      </div>
    );
  }

  return (
    <div className="product-picker">
      {creatingNew ? (
        <form className="new-product-form" onSubmit={handleCreateAndAssign}>
          <input
            type="text"
            placeholder="New product name"
            value={newProductName}
            onChange={(e) => setNewProductName(e.target.value)}
            disabled={busy}
            autoFocus
          />
          <button type="submit" disabled={busy || !newProductName.trim()}>
            Create &amp; Assign
          </button>
          <button type="button" onClick={() => setCreatingNew(false)} disabled={busy}>
            Cancel
          </button>
        </form>
      ) : (
        <>
          <select
            value=""
            onChange={(e) => handleSelectExisting(e.target.value)}
            disabled={busy}
          >
            <option value="">Assign product…</option>
            {products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.display_name}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => setCreatingNew(true)} disabled={busy}>
            + New
          </button>
        </>
      )}
      {error && <p className="error card-error">{error}</p>}
    </div>
  );
}
