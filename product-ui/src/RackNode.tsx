import { Box, GripVertical } from 'lucide-react';
import type { NodeProps } from '@xyflow/react';
import type { Device } from './types';

export type RackNodeData = { device: Device; mounted: Device[] };

export function RackNode({ data, selected }: NodeProps) {
  const { device, mounted } = data as RackNodeData;
  const units = Number(device.hardware.rackUnits ?? 24);
  const width = Number(device.hardware.rackWidth ?? 520);
  return (
    <article className={`rack-node ${selected ? 'is-selected' : ''}`} style={{ width, height: 58 + units * 24 }}>
      <header><GripVertical /><span><strong>{device.name}</strong><small>{units}U / 19 cali</small></span><em>{mounted.length} urządzeń</em></header>
      <div className="rack-rails">
        {Array.from({ length: units }, (_, index) => (
          <div className="rack-unit" key={index}><small>{units - index}U</small><span /><span /></div>
        ))}
      </div>
      {mounted.length === 0 && <div className="rack-empty"><Box />Upuść urządzenie na szafę</div>}
    </article>
  );
}
