import { Handle, Position, type NodeProps } from '@xyflow/react';
import { ArchiveRestore, Box, CircleStop, Monitor, Network, Play, Printer, RotateCcw, Router, Server, Settings2 } from 'lucide-react';
import type { Device } from './types';

export type DeviceNodeData = {
  device: Device;
  connectedPortColors: Record<string, string>;
  onOpen: (device: Device) => void;
  onAction: (device: Device, action: string) => void;
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
  const { device, connectedPortColors, onOpen, onAction } = nodeData;
  const Icon = kindIcons[device.profile.kind as keyof typeof kindIcons] ?? Box;
  const bottomPorts = device.ports.filter(port => port.side === 'bottom');
  const sidePorts = device.ports.filter(port => port.side !== 'bottom');
  const isSwitch = device.profile.kind === 'switch';
  const isPrinter = device.profile.kind === 'printer';
  const canConfigure = ['workstation', 'server'].includes(device.profile.kind);
  const hasRuntime = ['router', 'client1', 'client2'].includes(device.id);

  return (
    <article
      className={`device-node ${selected ? 'is-selected' : ''} ${isSwitch ? 'is-switch' : ''} ${isPrinter ? 'is-printer' : ''}`}
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
          {canConfigure ? (
            <button className="nodrag icon-button" title="Konfiguruj urządzenie" onClick={() => onOpen(device)}>
              <Settings2 aria-hidden="true" />
            </button>
          ) : <span />}
        </header>

        {isPrinter && (
          <div className="printer-output">
            <div className="printer-output-slot" />
            <small>Odbiornik wydruków</small>
          </div>
        )}

        <div className={`port-bank ${isSwitch ? 'port-bank-switch' : ''}`}>
          {bottomPorts.map(port => (
            <div className={`device-port ${connectedPortColors[port.id] ? 'is-connected' : ''}`} key={port.id}>
              <small>{port.name}</small>
              <Handle
                type="source"
                position={Position.Bottom}
                id={port.id}
                className={`nodrag port-socket port-handle connector-${port.connector}`}
                style={{ '--port-cable-color': connectedPortColors[port.id] ?? '#777d76' } as React.CSSProperties}
                title={`${port.name} (${port.connector})`}
              />
            </div>
          ))}
        </div>

        {sidePorts.length > 0 && (
          <div className="side-port-bank">
            {sidePorts.map(port => {
              const position = port.side === 'left' ? Position.Left : Position.Right;
              return (
                <div className={`side-port side-${port.side}`} key={port.id}>
                  <small>{port.name}</small>
                  <Handle
                    type="source"
                    position={position}
                    id={port.id}
                    className={`nodrag port-socket port-handle connector-${port.connector}`}
                    style={{ '--port-cable-color': connectedPortColors[port.id] ?? '#777d76' } as React.CSSProperties}
                    title={`${port.name} (${port.connector})`}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      <footer className="device-statusbar">
        <span className={`status-dot status-${device.status}`} />
        <span>{device.status === 'running' ? 'Uruchomione' : 'Wyłączone'}</span>
        <span className="device-os">{device.os_template ?? 'Bez systemu'}</span>
        {hasRuntime && <button className="nodrag icon-button" title="Konsola" onClick={() => onAction(device, 'console')}><Monitor aria-hidden="true" /></button>}
        {hasRuntime && <button className="nodrag icon-button" title="Przywróć" onClick={() => onAction(device, 'reset')}><RotateCcw aria-hidden="true" /></button>}
        {hasRuntime && canConfigure && <button className="nodrag icon-button" title="Aktualizuj obraz odzyskiwania" onClick={() => onAction(device, 'promote')}><ArchiveRestore aria-hidden="true" /></button>}
        {hasRuntime && device.status !== 'running' && <button className="nodrag icon-button" title="Uruchom" onClick={() => onAction(device, 'start')}><Play aria-hidden="true" /></button>}
        {hasRuntime && device.status === 'running' && <button className="nodrag icon-button" title="Zatrzymaj" onClick={() => onAction(device, 'shutdown')}><CircleStop aria-hidden="true" /></button>}
      </footer>
    </article>
  );
}
