import type { NodeProps } from '@xyflow/react';
import type { Device } from './types';

export type SocketOverlayNodeData = {
  device: Device;
  connectedPortColors: Record<string, string>;
  mountedWidth?: number;
};

export function SocketOverlayNode({ data }: NodeProps) {
  const { device, connectedPortColors, mountedWidth } = data as SocketOverlayNodeData;
  const bottomPorts = device.ports.filter(port => port.side === 'bottom');
  const sidePorts = device.ports.filter(port => port.side !== 'bottom');
  const isSwitch = device.profile.kind === 'switch';
  const isPrinter = device.profile.kind === 'printer';
  return (
    <article
      className={`device-node socket-overlay-node ${isSwitch ? 'is-switch' : ''} ${isPrinter ? 'is-printer' : ''}`}
      style={{ '--device-accent': device.profile.accent, width: mountedWidth } as React.CSSProperties}
    >
      <div className="device-face">
        <header className="device-heading"><span className="device-kind-icon" /><span><strong>{device.name}</strong><small>{device.profile.model}</small></span><span /></header>
        {isPrinter && <div className="printer-output"><div className="printer-output-slot" /><small>Odbiornik wydruków</small></div>}
        <div className={`port-bank ${isSwitch ? 'port-bank-switch' : ''}`}>
          {bottomPorts.map(port => (
            <div className="device-port" key={port.id}>
              <small>{port.name}</small>
              <span className={`socket-stack connector-${port.connector}`} style={{ '--port-cable-color': connectedPortColors[port.id] ?? '#777d76' } as React.CSSProperties}>
                <span className="socket-visual" />
              </span>
            </div>
          ))}
        </div>
        {sidePorts.length > 0 && <div className="side-port-bank">
          {sidePorts.map(port => <div className={`side-port side-${port.side}`} key={port.id}>
            <small>{port.name}</small>
            <span className={`socket-stack side-socket connector-${port.connector}`} style={{ '--port-cable-color': connectedPortColors[port.id] ?? '#777d76' } as React.CSSProperties}>
              <span className="socket-visual" />
            </span>
          </div>)}
        </div>}
      </div>
      <footer className="device-statusbar" />
    </article>
  );
}
