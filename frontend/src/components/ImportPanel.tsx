import { useRef, useState } from 'react';
import { api, type Project } from '../api';

interface ImportPanelProps {
  projects: Project[];
  onImported: () => void;
}

/**
 * Import UI covering both real Import Providers: local file upload
 * (LocalFileImporter) and URL import (PlaywrightTikTokImporter/
 * DownieImporter, Phase 11.1 - see MIGRATION_PLAN.md). The project
 * selector is optional - a Creative does not require a Project (plan §1,
 * §6) - so "No project" is a first-class, default choice here, not an
 * afterthought, and is shared by both import paths below.
 *
 * Calls api.importSlideshows (new pipeline, Phase 2.6 of the
 * Slideshow/Slide migration) rather than api.importLocalFiles - this
 * component has no Creative-specific typing otherwise (it never
 * references the Creative type, only Project), so the cutover is this
 * one call, not a parallel component.
 *
 * groupAsOne (Phase 4 - true multi-slide import, see MIGRATION_PLAN.md):
 * an explicit, unchecked-by-default checkbox, not something inferred
 * from "more than one file was chosen" - selecting several files today
 * already means "N unrelated items," a real, already-relied-on behavior
 * this must not silently change. Not user-configurable for URL import -
 * the backend always groups a URL import's media as one Slideshow
 * (api.importSlideshowFromUrl), since a TikTok post's images are one
 * coherent slideshow the platform itself already ordered.
 */
export function ImportPanel({ projects, onImported }: ImportPanelProps) {
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [groupAsOne, setGroupAsOne] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Phase 11.1 (see MIGRATION_PLAN.md) - the URL import path, kept as
  // separate state from the file-upload flow above so the two mechanisms
  // never interfere with each other's loading/error state.
  const [sourceUrl, setSourceUrl] = useState('');
  const [urlProvider, setUrlProvider] = useState<'tiktok' | 'downie'>('tiktok');
  const [urlImporting, setUrlImporting] = useState(false);
  const [urlError, setUrlError] = useState<string | null>(null);

  const handleFilesSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setImporting(true);
    setError(null);
    try {
      await api.importSlideshows(Array.from(files), selectedProjectId || undefined, groupAsOne);
      onImported();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleImportFromUrl = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!sourceUrl.trim()) return;

    setUrlImporting(true);
    setUrlError(null);
    try {
      await api.importSlideshowFromUrl(sourceUrl.trim(), selectedProjectId || undefined, urlProvider);
      setSourceUrl('');
      onImported();
    } catch (err) {
      setUrlError((err as Error).message);
    } finally {
      setUrlImporting(false);
    }
  };

  return (
    <section className="import-panel">
      <h2>Import Creatives</h2>
      <div className="import-controls">
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          disabled={importing}
        >
          <option value="">No project</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>

        <label className="group-as-one-checkbox">
          <input
            type="checkbox"
            checked={groupAsOne}
            onChange={(e) => setGroupAsOne(e.target.checked)}
            disabled={importing}
          />
          These are one slideshow
        </label>

        <label className="file-picker-button">
          {importing ? 'Importing…' : 'Choose Image(s)'}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={handleFilesSelected}
            disabled={importing}
            hidden
          />
        </label>
      </div>
      {error && <p className="error">{error}</p>}

      <form className="import-url-controls" onSubmit={handleImportFromUrl}>
        <input
          type="url"
          placeholder="TikTok slideshow URL"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.target.value)}
          disabled={urlImporting}
        />
        <select
          value={urlProvider}
          onChange={(e) => setUrlProvider(e.target.value as 'tiktok' | 'downie')}
          disabled={urlImporting}
        >
          <option value="tiktok">TikTok (native)</option>
          <option value="downie">Downie (fallback - requires local app)</option>
        </select>
        <button type="submit" disabled={urlImporting || !sourceUrl.trim()}>
          {urlImporting ? 'Importing…' : 'Import from URL'}
        </button>
      </form>
      {urlError && <p className="error">{urlError}</p>}
    </section>
  );
}
