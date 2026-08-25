import type { NodeProps } from '@xyflow/react';
import type { Device } from './types';

export function DeviceUnderlay({ data }: NodeProps) {
  const device = (data as { device: Device }).device;
  const kind = device.profile.kind;
  return (
    <div
      className={`device-underlay kind-${kind}`}
      style={{ '--device-accent': device.profile.accent } as React.CSSProperties}
    >
      <div className="underlay-face" />
    </div>
  );
}
