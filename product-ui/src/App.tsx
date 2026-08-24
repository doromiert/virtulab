import { useEffect, useMemo, useState } from 'react';
import {
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type OnNodeDrag,
  type ReactFlowInstance
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Box,
  ChevronLeft,
  ChevronRight,
  Languages,
  Library,
  MonitorCog,
  Network,
  Plus,
  Printer,
  Router,
  Search,
  Server,
  Settings2,
  Trash2,
  X
} from 'lucide-react';
import { productApi } from './api';
import { CableEdge } from './CableEdge';
import { DeviceNode, type DeviceNodeData } from './DeviceNode';
import type { CableMode, Catalog, Device, DeviceProfile, WorkspaceSnapshot } from './types';
import './styles.css';

const nodeTypes = { device: DeviceNode };
const edgeTypes = { cable: CableEdge };
const cableColors: Record<string, string> = {
  yellow: '#f4c430', blue: '#3488db', red: '#dc4641', green: '#4ea85c', black: '#25282a'
};
const profileIcons = { router: Router, switch: Network, workstation: Box, server: Server, printer: Printer, uplink: Network };

function toFlow(snapshot: WorkspaceSnapshot, onOpen: (device: Device) => void) {
  const portOwners = new Map<string, string>();
  const connected = new Set<string>();
  snapshot.devices.forEach(device => device.ports.forEach(port => portOwners.set(port.id, device.id)));
  snapshot.cables.forEach(cable => { connected.add(cable.port_a); connected.add(cable.port_b); });
  const nodes: Array<Node<DeviceNodeData>> = snapshot.devices.map(device => ({
    id: device.id,
    type: 'device',
    position: { x: device.x, y: device.y },
    dragHandle: '.device-drag-handle',
    data: { device, connectedPorts: [...connected], onOpen }
  }));
  const edges: Edge[] = snapshot.cables.flatMap(cable => {
    const source = portOwners.get(cable.port_a);
    const target = portOwners.get(cable.port_b);
    if (!source || !target) return [];
    return [{
      id: cable.id,
      source,
      target,
      sourceHandle: cable.port_a,
      targetHandle: cable.port_b,
      type: 'cable',
      data: { mode: snapshot.workspace.cable_mode, color: cableColors[cable.color] ?? cable.color },
      selectable: snapshot.workspace.cable_mode !== 'hidden'
    }];
  });
  return { nodes, edges };
}

function ProductCanvas() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<DeviceNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [internalDevice, setInternalDevice] = useState<Device | null>(null);
  const [toolboxOpen, setToolboxOpen] = useState(() => window.innerWidth > 900);
  const [inspectorOpen, setInspectorOpen] = useState(() => window.innerWidth > 900);
  const [flow, setFlow] = useState<ReactFlowInstance<Node<DeviceNodeData>, Edge> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const openDevice = (device: Device) => setInternalDevice(device);

  useEffect(() => {
    Promise.all([productApi.catalog(), productApi.workspace('default')])
      .then(([nextCatalog, nextSnapshot]) => {
        setCatalog(nextCatalog);
        setSnapshot(nextSnapshot);
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  useEffect(() => {
    if (!snapshot) return;
    const flowState = toFlow(snapshot, openDevice);
    setNodes(flowState.nodes);
    setEdges(flowState.edges);
    if (selectedDevice) {
      setSelectedDevice(snapshot.devices.find(device => device.id === selectedDevice.id) ?? null);
    }
  }, [snapshot]);

  const selectedTemplate = useMemo(
    () => catalog?.templates.find(template => template.id === selectedDevice?.os_template),
    [catalog, selectedDevice]
  );

  const persistPosition: OnNodeDrag<Node<DeviceNodeData>> = async (_, node) => {
    if (!snapshot) return;
    setSaving(true);
    try {
      const next = await productApi.updateCanvas(snapshot.workspace.id, {
        positions: [{ id: node.id, x: node.position.x, y: node.position.y }]
      });
      setSnapshot(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  };

  async function setCableMode(mode: CableMode) {
    if (!snapshot) return;
    setSaving(true);
    try {
      setSnapshot(await productApi.updateCanvas(snapshot.workspace.id, { positions: [], cableMode: mode }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  async function addDevice(profile: DeviceProfile) {
    if (!snapshot) return;
    const center = flow?.screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 }) ?? { x: 0, y: 0 };
    setSaving(true);
    try {
      setSnapshot(await productApi.addDevice(snapshot.workspace.id, profile.id, center.x, center.y));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  async function removeSelected() {
    if (!snapshot || !selectedDevice) return;
    setSaving(true);
    try {
      setSnapshot(await productApi.removeDevice(snapshot.workspace.id, selectedDevice.id));
      setSelectedDevice(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  if (!snapshot || !catalog) {
    return <main className="loading-screen"><span className="loading-mark">VL</span><strong>VirtuLab</strong></main>;
  }

  return (
    <main className="product-shell">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={persistPosition}
        onNodeClick={(_, node) => setSelectedDevice(node.data.device)}
        onPaneClick={() => setSelectedDevice(null)}
        onInit={setFlow}
        fitView
        fitViewOptions={{ padding: 0.35, maxZoom: 0.75 }}
        minZoom={0.08}
        maxZoom={2.4}
        deleteKeyCode={null}
        nodesConnectable={false}
        connectionMode={ConnectionMode.Loose}
        selectionOnDrag
        panOnScroll
        zoomOnDoubleClick={false}
      >
        <Background color="#343634" gap={24} size={1} variant={BackgroundVariant.Dots} />
        <MiniMap className="canvas-minimap" pannable zoomable nodeColor={node => (node.data as DeviceNodeData).device.profile.accent} />
        <Controls className="canvas-controls" showInteractive={false} />
      </ReactFlow>

      <header className="floating-topbar">
        <button className="brand-button" title="Menu główne"><span>VL</span></button>
        <div className="workspace-name">
          <strong>{snapshot.workspace.name}</strong>
          <small>{saving ? 'Zapisywanie...' : `Wersja ${snapshot.workspace.revision}`}</small>
        </div>
        <button className="icon-button" title="Biblioteka laboratoriów"><Library /></button>
        <button className="icon-button" title="Ustawienia"><Settings2 /></button>
      </header>

      <nav className="floating-tools" aria-label="Narzędzia obszaru roboczego">
        <button className="icon-button is-active" title="Zaznacz"><MonitorCog /></button>
        <button className="icon-button" title="Dodaj urządzenie" onClick={() => setToolboxOpen(value => !value)}><Plus /></button>
        <button className="icon-button" title="Szukaj"><Search /></button>
        <span className="tool-separator" />
        <button className="icon-button" title="Język"><Languages /></button>
      </nav>

      <section className="cable-mode-control" aria-label="Sposób wyświetlania kabli">
        {(['realistic', 'straight', 'hidden'] as CableMode[]).map(mode => (
          <button
            key={mode}
            className={snapshot.workspace.cable_mode === mode ? 'is-active' : ''}
            onClick={() => setCableMode(mode)}
          >
            {{ realistic: 'Realistyczne', straight: 'Proste', hidden: 'Ukryte' }[mode]}
          </button>
        ))}
      </section>

      {toolboxOpen && (
        <aside className="floating-panel toolbox-panel">
          <header><strong>Urządzenia</strong><button className="icon-button" title="Zamknij" onClick={() => setToolboxOpen(false)}><X /></button></header>
          <label className="toolbox-search"><Search /><input type="search" placeholder="Szukaj" /></label>
          <div className="profile-list">
            {catalog.profiles.map(profile => {
              const Icon = profileIcons[profile.kind as keyof typeof profileIcons] ?? Box;
              return (
                <button className="profile-item" key={profile.id} onClick={() => addDevice(profile)}>
                  <span style={{ background: profile.accent }}><Icon /></span>
                  <span><strong>{profile.name.pl}</strong><small>{profile.model}</small></span>
                  <Plus />
                </button>
              );
            })}
          </div>
        </aside>
      )}

      <button
        className={`panel-toggle toolbox-toggle ${toolboxOpen ? 'is-open' : ''}`}
        title={toolboxOpen ? 'Ukryj bibliotekę' : 'Pokaż bibliotekę'}
        onClick={() => setToolboxOpen(value => !value)}
      >
        {toolboxOpen ? <ChevronLeft /> : <ChevronRight />}
      </button>

      {inspectorOpen && (
        <aside className="floating-panel inspector-panel">
          <header><strong>Właściwości</strong><button className="icon-button" title="Zamknij" onClick={() => setInspectorOpen(false)}><X /></button></header>
          {selectedDevice ? (
            <div className="inspector-content">
              <label>Nazwa<input value={selectedDevice.name} readOnly /></label>
              <label>Profil<input value={selectedDevice.profile.model} readOnly /></label>
              <label>System<input value={selectedTemplate?.name ?? selectedDevice.os_template ?? 'Bez systemu'} readOnly /></label>
              <dl>
                <div><dt>Porty</dt><dd>{selectedDevice.ports.length}</dd></div>
                <div><dt>Runtime</dt><dd>{selectedDevice.profile.runtime}</dd></div>
                <div><dt>Stan</dt><dd>{selectedDevice.status}</dd></div>
              </dl>
              <button className="command-button" onClick={() => setInternalDevice(selectedDevice)}><Settings2 />Sprzęt i system</button>
              <button className="command-button danger" onClick={removeSelected}><Trash2 />Usuń urządzenie</button>
            </div>
          ) : <div className="empty-inspector">Zaznacz urządzenie</div>}
        </aside>
      )}

      {!inspectorOpen && (
        <button className="panel-toggle inspector-toggle" title="Pokaż właściwości" onClick={() => setInspectorOpen(true)}><ChevronLeft /></button>
      )}

      {internalDevice && (
        <section className="hardware-focus" role="dialog" aria-modal="true" aria-label={`Sprzęt ${internalDevice.name}`}>
          <header>
            <span><small>Urządzenie</small><strong>{internalDevice.name}</strong></span>
            <button className="icon-button" title="Zamknij" onClick={() => setInternalDevice(null)}><X /></button>
          </header>
          <div className="motherboard">
            <div className="board-label">VIRTULAB Q35</div>
            <div className="cpu-socket"><small>CPU</small><strong>4 vCPU</strong></div>
            <div className="ram-bank"><small>DIMM</small><strong>6 GiB</strong></div>
            <div className="storage-bank"><small>SATA</small><strong>System disk</strong></div>
            <div className="pcie-area">
              {internalDevice.ports.filter(port => port.medium === 'ethernet').map(port => (
                <div className="pcie-card" key={port.id}><Network /><span><small>PCIe NIC</small><strong>{port.name}</strong></span></div>
              ))}
              <button className="add-component"><Plus />Dodaj kartę</button>
            </div>
          </div>
        </section>
      )}

      {error && <div className="error-toast"><span>{error}</span><button className="icon-button" onClick={() => setError(null)}><X /></button></div>}
    </main>
  );
}

export default function App() {
  return <ReactFlowProvider><ProductCanvas /></ReactFlowProvider>;
}
