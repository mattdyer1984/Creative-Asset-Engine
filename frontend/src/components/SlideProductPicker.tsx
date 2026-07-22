import { useState } from 'react';
import { api, type Product, type SlideProductAppearance } from '../api';

interface SlideProductPickerProps {
  slideshowId: string;
  slideId: string;
  currentAppearances: SlideProductAppearance[];
  products: Product[];
  onChanged: () => void;
}

/**
 * New-pipeline equivalent of ProductPicker.tsx, operating on a
 * (slideshowId, slideId) pair and a list of ProductAppearances instead
 * of a creativeId and a direct Creative.product FK - see
 * app/routers/slideshows.py's assign-product endpoint.
 *
 * Phase 6.5 (multi per-slide product detection, see MIGRATION_PLAN.md)
 * rebuilt this around the additive add/remove endpoints (Phase 6.1)
 * instead of the single-slot assign-product endpoint - a slide can now
 * carry several current appearances at once, each removable
 * independently, rather than one replaceable slot.
 */
export function SlideProductPicker({
  slideshowId,
  slideId,
  currentAppearances,
  products,
  onChanged,
}: SlideProductPickerProps) {
  const [creatingNew, setCreatingNew] = useState(false);
  const [newProductName, setNewProductName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assignedProductIds = new Set(currentAppearances.map((a) => a.product_id));
  const availableProducts = products.filter((p) => !assignedProductIds.has(p.id));

  const handleAddExisting = async (productId: string) => {
    if (!productId) return;
    setBusy(true);
    setError(null);
    try {
      await api.addSlideProduct(slideshowId, slideId, productId);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (appearanceId: string) => {
    setBusy(true);
    setError(null);
    try {
      await api.removeSlideProduct(slideshowId, slideId, appearanceId);
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
      await api.addSlideProduct(slideshowId, slideId, product.id);
      setNewProductName('');
      setCreatingNew(false);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="product-picker">
      {currentAppearances.length > 0 && (
        <ul className="assigned-product-list">
          {currentAppearances.map((appearance) => (
            <li key={appearance.id} className="assigned-product">
              <span>{appearance.product?.display_name ?? appearance.product_id}</span>
              <button
                className="unassign-button"
                onClick={() => handleRemove(appearance.id)}
                disabled={busy}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

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
            Create &amp; Add
          </button>
          <button type="button" onClick={() => setCreatingNew(false)} disabled={busy}>
            Cancel
          </button>
        </form>
      ) : (
        <>
          <select
            value=""
            onChange={(e) => handleAddExisting(e.target.value)}
            disabled={busy || availableProducts.length === 0}
          >
            <option value="">
              {currentAppearances.length > 0 ? 'Add another product…' : 'Assign product…'}
            </option>
            {availableProducts.map((product) => (
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
