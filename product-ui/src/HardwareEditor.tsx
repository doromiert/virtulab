import { HardDrive, MemoryStick, Network, Plus, Save, Server, X } from 'lucide-react';
import { useState } from 'react';
import type { Device } from './types';

type Hardware = Record<string, string | number> & {
  cpuType: string;
  cpuCores: number;
  memoryMib: number;
  diskGib: number;
  networkCards: number;
};

export function HardwareEditor({ device, onSave, onClose }: { device: Device; onSave: (hardware: Hardware) => Promise<void>; onClose: () => void }) {
  const [draft, setDraft] = useState<Hardware>({
    cpuType: String(device.hardware.cpuType ?? 'host-model'),
    cpuCores: Number(device.hardware.cpuCores ?? 4),
    memoryMib: Number(device.hardware.memoryMib ?? 4096),
    diskGib: Number(device.hardware.diskGib ?? 80),
    networkCards: Number(device.hardware.networkCards ?? device.ports.filter(port => port.medium === 'ethernet').length)
  });
  const [saving, setSaving] = useState(false);
  const cards = Array.from({ length: draft.networkCards }, (_, index) => index + 1);

  function number(field: keyof Hardware, minimum: number, maximum: number, value: string) {
    setDraft(current => ({ ...current, [field]: Math.min(maximum, Math.max(minimum, Number(value))) }));
  }

  async function save() {
    setSaving(true);
    try { await onSave(draft); } finally { setSaving(false); }
  }

  return (
    <section className="hardware-focus" role="dialog" aria-modal="true" aria-label={`Sprzęt ${device.name}`}>
      <header><span><small>Konfigurator komputera</small><strong>{device.name}</strong></span><button className="icon-button" title="Zamknij" onClick={onClose}><X /></button></header>
      <div className="hardware-scroll">
        <aside className="hardware-settings">
          <label>Typ CPU<select value={draft.cpuType} onChange={event => setDraft(current => ({ ...current, cpuType: event.target.value }))}><option value="host-model">Host model</option><option value="host-passthrough">Host passthrough</option><option value="qemu64">QEMU64</option></select></label>
          <label>Rdzenie CPU<input type="number" min="1" max="64" value={draft.cpuCores} onChange={event => number('cpuCores', 1, 64, event.target.value)} /></label>
          <label>Pamięć RAM (MiB)<input type="number" min="512" max="262144" step="512" value={draft.memoryMib} onChange={event => number('memoryMib', 512, 262144, event.target.value)} /></label>
          <label>Dysk (GiB)<input type="number" min="4" max="4096" value={draft.diskGib} onChange={event => number('diskGib', 4, 4096, event.target.value)} /></label>
          <label>Karty sieciowe<input type="number" min="1" max="16" value={draft.networkCards} onChange={event => number('networkCards', 1, 16, event.target.value)} /></label>
          <button className="primary-action" disabled={saving} onClick={save}><Save />{saving ? 'Zapisywanie...' : 'Zapisz sprzęt'}</button>
        </aside>
        <div className="motherboard" style={{ minHeight: `${520 + Math.max(0, cards.length - 4) * 55}px` }}>
          <div className="board-label">VIRTULAB Q35</div>
          <div className="cpu-socket"><Server /><small>{draft.cpuType}</small><strong>{draft.cpuCores} vCPU</strong></div>
          <div className="ram-bank"><MemoryStick /><small>DIMM</small><strong>{draft.memoryMib} MiB</strong></div>
          <div className="storage-bank"><HardDrive /><small>SATA</small><strong>{draft.diskGib} GiB</strong></div>
          <div className="pcie-area">
            {cards.map(number => <div className="pcie-card" key={number}><Network /><span><small>PCIe NIC</small><strong>NIC {number}</strong></span></div>)}
            <button className="add-component" disabled={draft.networkCards >= 16} onClick={() => setDraft(current => ({ ...current, networkCards: current.networkCards + 1 }))}><Plus />Dodaj kartę</button>
          </div>
        </div>
      </div>
    </section>
  );
}
