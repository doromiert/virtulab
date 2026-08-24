import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Box, CircleStop, Network, Play, Power, Printer, Router, Server, Settings2 } from 'lucide-react';
import type { Device } from './types';

export type DeviceNodeData = {
  device: Device;
  connectedPorts: string[];
  onOpen: (device: Device) => void;
};

const kindIcons = {
  router: Router,
  switch: Network,
  workstation: Box,
  server: Server,
  printer: Printer,
  uplink: Network
};

export function DeviceNode({ data, selected }: NodeProps) {
  const nodeData = data as DeviceNodeData;
  const { device, connectedPorts, onOpen } = nodeData;
  const Icon = kindIcons[device.profile.kind as keyof typeof kindIcons] ?? Box;
  const bottomPorts = device.ports.filter(port => port.side === 'bottom');
  const sidePorts = device.ports.filter(port => port.side !== 'bottom');
  const isSwitch = device.profile.kind === 'switch';

  return (
    <article
      className={`device-node ${selected ? 'is-selected' : ''} ${isSwitch ? 'is-switch' : ''}`}
      style={{ '--device-accent': device.profile.accent } as React.CSSProperties}
      onDoubleClick={() => onOpen(device)}
    >
      <div className="device-face">
        <header className="device-heading">
          <span className="device-kind-icon"><Icon aria-hidden="true" /></span>
          <span>
            <strong>{device.name}</strong>
            <small>{device.profile.model}</small>
          </span>
          <button className="nodrag icon-button" title="Konfiguruj urządzenie" onClick={() => onOpen(device)}>
            <Settings2 aria-hidden="true" />
          </button>
        </header>

        <div className={`port-bank ${isSwitch ? 'port-bank-switch' : ''}`}>
          {bottomPorts.map((port, index) => (
            <div className={`device-port ${connectedPorts.includes(port.id) ? 'is-connected' : ''}`} key={port.id}>
              <span className={`port-socket connector-${port.connector}`} />
              <small>{port.name}</small>
              <Handle
                type="source"
                position={Position.Bottom}
                id={port.id}
                className="port-handle"
                style={{ left: `${((index + 1) / (bottomPorts.length + 1)) * 100}%` }}
              />
            </div>
          ))}
        </div>

        {sidePorts.map((port, index) => {
          const position = port.side === 'left' ? Position.Left : Position.Right;
          return (
            <Handle
              key={port.id}
              type="source"
              position={position}
              id={port.id}
              className={`port-handle side-handle ${connectedPorts.includes(port.id) ? 'is-connected' : ''}`}
              style={{ top: `${32 + index * 22}%` }}
              title={port.name}
            />
          );
        })}
      </div>

      <footer className="device-statusbar device-drag-handle">
        <span className={`status-dot status-${device.status}`} />
        <span>{device.status === 'running' ? 'Uruchomione' : 'Wyłączone'}</span>
        <span className="device-os">{device.os_template ?? 'Bez systemu'}</span>
        <button className="nodrag icon-button" title="Uruchom"><Play aria-hidden="true" /></button>
        <button className="nodrag icon-button" title="Zatrzymaj">
          {device.status === 'running' ? <CircleStop aria-hidden="true" /> : <Power aria-hidden="true" />}
        </button>
      </footer>
    </article>
  );
}
