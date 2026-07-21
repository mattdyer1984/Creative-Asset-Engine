import { useRef, useState } from 'react';
import { api, type Project } from '../api';

interface ImportPanelProps {
  projects: Project[];
  onImported: () => void;
}

/**
 * Import UI for M1's only Import Provider: LocalFileImporter. The project
 * selector is optional - a Creative does not require a Project (plan §1,
 * §6) - so "No project" is a first-class, default choice here, not an
 * afterthought.
 */
export function ImportPanel({ projects, onImported }: ImportPanelProps) {
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFilesSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setImporting(true);
    setError(null);
    try {
      await api.importLocalFiles(Array.from(files), selectedProjectId || undefined);
      onImported();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
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
    </section>
  );
}
