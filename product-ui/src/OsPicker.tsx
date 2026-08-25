import { HardDrive, LayoutGrid, List, Mountain, Search, Server, Snowflake, Terminal, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { Template } from './types';

const iconMap = { server: Server, terminal: Terminal, snowflake: Snowflake, mountain: Mountain, windows: LayoutGrid, circle: HardDrive, 'hard-drive': HardDrive };

export function OsPicker({
  templates,
  value,
  onSelect,
  onClose,
  onBuild
}: {
  templates: Template[];
  value: string | null;
  onSelect: (id: string | null) => void;
  onClose: () => void;
  onBuild: () => void;
}) {
  const [view, setView] = useState<'list' | 'grid'>('grid');
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return templates;
    return templates.filter(template =>
      [template.name, template.description, template.type, ...template.tags].join(' ').toLowerCase().includes(needle)
    );
  }, [query, templates]);

  return (
    <section className="picker-dialog" role="dialog" aria-modal="true" aria-label="Wybierz system operacyjny">
      <header>
        <span><small>Biblioteka obrazów</small><strong>System operacyjny</strong></span>
        <div>
          <button className="command-button" onClick={onBuild}><HardDrive />Nowy obraz</button>
          <button className="icon-button" title="Zamknij" onClick={onClose}><X /></button>
        </div>
      </header>
      <div className="picker-tools">
        <label><Search /><input autoFocus type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Szukaj po nazwie, typie lub tagu" /></label>
        <div className="view-toggle">
          <button className={view === 'list' ? 'is-active' : ''} title="Lista" onClick={() => setView('list')}><List /></button>
          <button className={view === 'grid' ? 'is-active' : ''} title="Siatka" onClick={() => setView('grid')}><LayoutGrid /></button>
        </div>
      </div>
      <div className={`os-results view-${view}`}>
        <button className={`os-option no-os ${value === null ? 'is-selected' : ''}`} onClick={() => onSelect(null)}>
          <span className="os-icon"><X /></span><span><strong>Bez systemu</strong><small>Pusty dysk</small></span>
        </button>
        {filtered.map(template => {
          const Icon = iconMap[template.icon as keyof typeof iconMap] ?? HardDrive;
          return (
            <button className={`os-option ${value === template.id ? 'is-selected' : ''}`} key={template.id} onClick={() => onSelect(template.id)}>
              <span className="os-icon"><Icon /></span>
              <span><strong>{template.name}</strong><small>{template.description}</small></span>
              <div className="os-tags">{template.tags.slice(0, 3).map(tag => <em key={tag}>{tag}</em>)}</div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
