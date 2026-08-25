import { Download, HardDrive, Upload, X } from 'lucide-react';
import { useState } from 'react';
import type { Catalog } from './types';
import type { OsProject } from './types';

export type OsProjectDraft = {
  name: string;
  description: string;
  type: string;
  icon: string;
  tags: string[];
  sourceKind: string;
  sourceValue?: string;
  file?: File;
};

export function OsTool({ catalog, onCreate, onStart, onSeal, onClose }: {
  catalog: Catalog;
  onCreate: (draft: OsProjectDraft) => Promise<OsProject>;
  onStart: (project: OsProject) => Promise<void>;
  onSeal: (project: OsProject) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState('general');
  const [tags, setTags] = useState('');
  const [sourceKind, setSourceKind] = useState('predefined');
  const [sourceValue, setSourceValue] = useState(catalog.templates[0]?.id ?? '');
  const [file, setFile] = useState<File | undefined>();
  const [working, setWorking] = useState(false);
  const [project, setProject] = useState<OsProject | null>(null);

  async function submit() {
    if (!name.trim()) return;
    setWorking(true);
    try {
      const created = await onCreate({
        name: name.trim(),
        description: description.trim(),
        type,
        icon: 'hard-drive',
        tags: tags.split(',').map(tag => tag.trim()).filter(Boolean),
        sourceKind,
        sourceValue,
        file
      });
      setProject(created);
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="os-tool-dialog" role="dialog" aria-modal="true" aria-label="Zbuduj obraz systemu">
      <header><span><small>Narzędzie systemowe</small><strong>Nowy obraz bazowy</strong></span><button className="icon-button" title="Zamknij" onClick={onClose}><X /></button></header>
      {project ? <div className="os-project-progress">
        <HardDrive />
        <span><small>Projekt obrazu</small><strong>{project.name}</strong><em>{project.status}</em></span>
        <div className="os-build-flow"><span>1. Źródło</span><i /><span>2. VM instalacyjna</span><i /><span>3. Konfiguracja</span><i /><span>4. Obraz bazowy</span></div>
        <button className="primary-action" onClick={() => onStart(project)}>Uruchom VM instalacyjną</button>
        <button className="command-button" onClick={() => onSeal(project)}>Zapisz wyłączoną VM jako bazę</button>
      </div> : <div className="os-tool-form">
        <label>Nazwa<input value={name} onChange={event => setName(event.target.value)} placeholder="np. Debian 13 - INF.03" /></label>
        <label>Opis<textarea value={description} onChange={event => setDescription(event.target.value)} placeholder="Przeznaczenie i zawartość obrazu" /></label>
        <div className="form-columns">
          <label>Typ<select value={type} onChange={event => setType(event.target.value)}><option value="desktop">Desktop</option><option value="server">Server</option><option value="general">Ogólny</option><option value="appliance">Appliance</option></select></label>
          <label>Tagi<input value={tags} onChange={event => setTags(event.target.value)} placeholder="linux, inf03, php" /></label>
        </div>
        <fieldset className="source-choice">
          <legend>Źródło instalacji</legend>
          <button className={sourceKind === 'predefined' ? 'is-active' : ''} onClick={() => setSourceKind('predefined')}><Download />Katalog</button>
          <button className={sourceKind === 'upload' ? 'is-active' : ''} onClick={() => setSourceKind('upload')}><Upload />Własny ISO</button>
          <button className={sourceKind === 'local-iso' ? 'is-active' : ''} onClick={() => setSourceKind('local-iso')}><HardDrive />Ścieżka lokalna</button>
        </fieldset>
        {sourceKind === 'predefined' ? (
          <label>Obraz źródłowy<select value={sourceValue} onChange={event => setSourceValue(event.target.value)}>{catalog.templates.filter(template => template.family !== 'custom').map(template => <option value={template.id} key={template.id}>{template.name}</option>)}</select></label>
        ) : sourceKind === 'upload' ? (
          <label>Plik ISO<input type="file" accept=".iso" onChange={event => { setFile(event.target.files?.[0]); setSourceValue(event.target.files?.[0]?.name ?? ''); }} /></label>
        ) : (
          <label>Ścieżka ISO<input value={sourceValue} onChange={event => setSourceValue(event.target.value)} placeholder="/home/user/images/system.iso" /></label>
        )}
        <div className="os-build-flow"><span>1. Źródło</span><i /><span>2. VM instalacyjna</span><i /><span>3. Konfiguracja</span><i /><span>4. Obraz bazowy</span></div>
        <button className="primary-action" disabled={working || !name.trim()} onClick={submit}><HardDrive />{working ? 'Zapisywanie...' : 'Utwórz projekt obrazu'}</button>
      </div>}
    </section>
  );
}
