import { useEffect, useState } from 'react';
import { api, type Creative, type Product, type Project } from './api';
import { ImportPanel } from './components/ImportPanel';
import { CreativeGrid } from './components/CreativeGrid';
import { ProductManager } from './components/ProductManager';
import './App.css';

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [creatives, setCreatives] = useState<Creative[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadingCreatives, setLoadingCreatives] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [creatingProject, setCreatingProject] = useState(false);

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

  const loadCreatives = () => {
    setLoadingCreatives(true);
    api
      .listCreatives()
      .then(setCreatives)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingCreatives(false));
  };

  useEffect(() => {
    loadProjects();
    loadProducts();
    loadCreatives();
  }, []);

  // Product assignment changes a Creative's `product` field, so the
  // Creative list needs reloading too - not just the Product list.
  const reloadProductsAndCreatives = () => {
    loadProducts();
    loadCreatives();
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
                <span className="project-name">{project.name}</span>
                <span className="project-meta">
                  Created {new Date(project.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ProductManager products={products} loading={loadingProducts} onCreated={loadProducts} />

      {error && <p className="error">{error}</p>}

      <ImportPanel projects={projects} onImported={loadCreatives} />

      <section className="creatives-section">
        <h2>Creatives</h2>
        <CreativeGrid
          creatives={creatives}
          loading={loadingCreatives}
          onStatusChange={reloadProductsAndCreatives}
          products={products}
        />
      </section>
    </div>
  );
}

export default App;
