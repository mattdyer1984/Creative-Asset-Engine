import { useEffect, useState } from 'react';
import { api, type Product, type Project } from '../api';

/**
 * Project Workspace — Phase 10.5/10.9 of AI Creative Engine vNext (see
 * MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §3). The read
 * side of the Project role reversal: which Products this Project's
 * work has come to involve, populated automatically (via
 * app.services.project_product.ensure_project_product_membership)
 * whenever a Product gets linked to one of the Project's Slides.
 *
 * Deliberately scoped to member products only - Generation History/
 * Validation Results as assembled Project-level views (§3's own
 * larger vision) were explicitly deferred in Phase 10.5's own report
 * (no real consumer/producer existed yet), so there is nothing for
 * this workspace to show for those beyond what already exists: a
 * real, honest reflection of what the backend actually computes
 * today, not a placeholder for what it doesn't.
 */
export function ProjectWorkspace({ project }: { project: Project }) {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setProducts(null);
    setError(null);
    api
      .listProjectProducts(project.id)
      .then((result) => {
        if (!cancelled) setProducts(result);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  return (
    <div className="project-workspace">
      {project.notes && <p className="project-workspace-notes">{project.notes}</p>}

      <h4 className="project-workspace-heading">Products in this Project</h4>
      {error && <p className="error">{error}</p>}
      {products === null && !error ? (
        <p>Loading products…</p>
      ) : products && products.length === 0 ? (
        <p className="empty-state">
          No products linked yet — assign a product to a slide in one of this
          Project's Slideshows to see it here.
        </p>
      ) : (
        <ul className="project-workspace-products">
          {products?.map((product) => (
            <li key={product.id} className="project-workspace-product">
              {product.display_name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
