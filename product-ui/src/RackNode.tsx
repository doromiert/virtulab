import { Box, GripVertical } from 'lucide-react';
import type { NodeProps } from '@xyflow/react';
import type { Device } from './types';

export type RackNodeData = { device: Device; mounted: Device[]; rackHeight: number };

export function RackNode({ data, selected }: NodeProps) {
  const { device, mounted, rackHeight } = data as RackNodeData;
  const width = Number(device.hardware.rackWidth ?? 520);
  return (
    <article className={`rack-node ${selected ? 'is-selected' : ''}`} style={{ width, height: rackHeight }}>
      <header><GripVertical /><span><strong>{device.name}</strong><small>19 cali / automatyczna wysokość</small></span><em>{mounted.length} urządzeń</em></header>
      <div className="rack-rails" />
      {mounted.length === 0 && <div className="rack-empty"><Box />Upuść urządzenie na szafę</div>}
    </article>
  );
}
