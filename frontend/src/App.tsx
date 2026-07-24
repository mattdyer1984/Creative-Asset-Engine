import { useEffect, useState } from 'react';
import { api, type Product, type Project, type Slideshow } from './api';
import { ProjectWorkspace } from './components/ProjectWorkspace';
import { ImportPanel } from './components/ImportPanel';
import { SlideshowGrid } from './components/SlideshowGrid';
import { ProductManager } from './components/ProductManager';
import { CatalogueImporter } from './components/CatalogueImporter';
import { CreateCreativeFlow } from './components/CreateCreativeFlow';
import { CreativeGallery } from './components/CreativeGallery';
import './App.css';

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [slideshows, setSlideshows] = useState<Slideshow[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadingSlideshows, setLoadingSlideshows] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [creatingProject, setCreatingProject] = useState(false);
  // Phase 10.5/10.9 of AI Creative Engine vNext (see MIGRATION_PLAN.md's
  // ADR §3) - which Project's workspace is currently expanded, if any.
  // No router in this app (see App.tsx's own history) - an inline
  // expand/collapse follows the same single-page convention every other
  // section here already uses, rather than introducing new routing
  // infrastructure just for this one view.
  const [expandedProjectId, setExpandedProjectId] = useState<string | null>(null);
  // Phase 11.9 (Product Experience, see MIGRATION_PLAN.md) - everything
  // below this toggle (Projects, Products, Import a Listing, the old
  // Import Creatives form, the technical Creatives grid) is unchanged,
  // just no longer the default view - a normal user's whole workflow is
  // CreateCreativeFlow + CreativeGallery above the toggle.
  const [showAdvanced, setShowAdvanced] = useState(false);

  const loadProjects = () => {
    setLoadingProjects(true);
    api
      .listProjects()
      .then(setProjects)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingProjects(false));
  };

  const loadProducts = () => {
    setLoadingProducts(true);
    api
      .listProducts()
      .then(setProducts)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingProducts(false));
  };

  const loadSlideshows = () => {
    setLoadingSlideshows(true);
    api
      .listSlideshows()
      .then(setSlideshows)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingSlideshows(false));
  };

  // Silent refresh (no loading-spinner flash) - used by the polling
  // effect below, which ticks every 1.5s while anything is queued/
  // analyzing and would otherwise flicker the grid on every tick.
  const refreshSlideshowsSilently = () => {
    api.listSlideshows().then(setSlideshows).catch((err) => setError(err.message));
  };

  useEffect(() => {
    loadProjects();
    loadProducts();
    loadSlideshows();
  }, []);

  // Poll while a background analysis is in flight anywhere in the list
  // (Phase 3.2 of the async execution boundary work - see
  // MIGRATION_PLAN.md) so cards reach ready/failed without the user
  // needing to open a slideshow's blueprint modal (which has its own,
  // separate poller for the single slideshow it's showing). Depends on
  // the derived boolean, not `slideshows` itself, so the interval isn't
  // torn down and recreated on every single tick's update - only when
  // "is anything in flight" actually flips.
  const anySlideshowInFlight = slideshows.some(
    (s) => s.status === 'queued' || s.status === 'analyzing'
  );
  useEffect(() => {
    if (!anySlideshowInFlight) return;
    const interval = setInterval(refreshSlideshowsSilently, 1500);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anySlideshowInFlight]);

  // Product assignment changes a Slide's current_product_appearance, so
  // the Slideshow list needs reloading too - not just the Product list.
  const reloadProductsAndSlideshows = () => {
    loadProducts();
    loadSlideshows();
  };

  const handleCreateProject = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newName.trim()) return;
    setCreatingProject(true);
    setError(null);
    try {
      await api.createProject({ name: newName.trim() });
      setNewName('');
      loadProjects();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreatingProject(false);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>Creative Asset Engine</h1>
      </header>

      <CreateCreativeFlow onCreated={reloadProductsAndSlideshows} />

      {error && <p className="error">{error}</p>}

      <section className="creative-gallery-section">
        <h2>Your Creatives</h2>
        <CreativeGallery
          slideshows={slideshows}
          loading={loadingSlideshows}
          onChanged={reloadProductsAndSlideshows}
        />
      </section>

      <button
        type="button"
        className="advanced-toggle"
        onClick={() => setShowAdvanced((current) => !current)}
      >
        {showAdvanced ? '▾ Hide Advanced' : '▸ Advanced'}
      </button>

      {showAdvanced && (
        <div className="advanced-section">
          <section className="projects-section">
            <h2>Projects</h2>
            <form className="create-project-form" onSubmit={handleCreateProject}>
              <input
                type="text"
                placeholder="New project name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                disabled={creatingProject}
              />
              <button type="submit" disabled={creatingProject || !newName.trim()}>
                {creatingProject ? 'Creating…' : 'Create Project'}
              </button>
            </form>

            {loadingProjects ? (
              <p>Loading projects…</p>
            ) : projects.length === 0 ? (
              <p className="empty-state">
                No projects yet. Projects are optional — creatives can be
                imported without one.
              </p>
            ) : (
              <ul className="project-list">
                {projects.map((project) => (
                  <li key={project.id} className="project-list-item">
                    <button
                      type="button"
                      className="project-row-toggle"
                      onClick={() =>
                        setExpandedProjectId((current) =>
                          current === project.id ? null : project.id
                        )
                      }
                    >
                      <span className="project-name">{project.name}</span>
                      <span className="project-meta">
                        Created {new Date(project.created_at).toLocaleString()}
                      </span>
                      <span className="project-row-chevron">
                        {expandedProjectId === project.id ? '▾' : '▸'}
                      </span>
                    </button>
                    {expandedProjectId === project.id && <ProjectWorkspace project={project} />}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <ProductManager products={products} loading={loadingProducts} onCreated={loadProducts} />

          <CatalogueImporter products={products} onProductsChanged={loadProducts} />

          <ImportPanel projects={projects} onImported={loadSlideshows} />

          <section className="creatives-section">
            <h2>Creatives</h2>
            <SlideshowGrid
              slideshows={slideshows}
              loading={loadingSlideshows}
              onStatusChange={reloadProductsAndSlideshows}
              products={products}
            />
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
