import { useState } from 'react';
import { api, type Product, type SlideProductAppearance } from '../api';

interface SlideProductPickerProps {
  slideshowId: string;
  slideId: string;
  currentAppearance: SlideProductAppearance | null;
  products: Product[];
  onChanged: () => void;
}

/**
 * New-pipeline equivalent of ProductPicker.tsx, operating on a
 * (slideshowId, slideId) pair and a ProductAppearance instead of a
 * creativeId and a direct Creative.product FK - see
 * app/routers/slideshows.py's assign-product endpoint.
 */
export function SlideProductPicker({
  slideshowId,
  slideId,
  currentAppearance,
  products,
  onChanged,
}: SlideProductPickerProps) {
  const [creatingNew, setCreatingNew] = useState(false);
  const [newProductName, setNewProductName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSelectExisting = async (productId: string) => {
    if (!productId) return;
    setBusy(true);
    setError(null);
    try {
      await api.assignSlideProduct(slideshowId, slideId, productId);
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
      await api.assignSlideProduct(slideshowId, slideId, null);
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
      await api.assignSlideProduct(slideshowId, slideId, product.id);
      setNewProductName('');
      setCreatingNew(false);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (currentAppearance) {
    return (
      <div className="product-picker">
        <span className="assigned-product">
          Product: {currentAppearance.product?.display_name ?? currentAppearance.product_id}
        </span>
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
