import type { NodeProps } from '@xyflow/react';
import type { Device } from './types';

export function DeviceUnderlay({ data }: NodeProps) {
  const { device, mountedWidth } = data as { device: Device; mountedWidth?: number };
  const kind = device.profile.kind;
  return (
    <div
      className={`device-underlay kind-${kind}`}
      style={{ '--device-accent': device.profile.accent, width: mountedWidth } as React.CSSProperties}
    >
      <div className="underlay-face" />
    </div>
  );
}
