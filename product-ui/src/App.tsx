import { useEffect, useState, type DragEvent } from 'react';
import {
  Background,
  BackgroundVariant,
  ConnectionMode,
  ConnectionLineType,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type Connection,
  type Node,
  type OnNodeDrag,
  type ReactFlowInstance
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Box,
  Cable,
  ChevronLeft,
  ChevronRight,
  FileOutput,
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
  Usb,
  X
} from 'lucide-react';
import { productApi } from './api';
import { CableEdge } from './CableEdge';
import { DeviceNode, type DeviceNodeData } from './DeviceNode';
import type { Cable as WorkspaceCable, CableMode, Catalog, Device, DeviceProfile, WorkspaceSnapshot } from './types';
import './styles.css';

const nodeTypes = { device: DeviceNode };
const edgeTypes = { cable: CableEdge };
const cableColors: Record<string, string> = {
  yellow: '#f4c430', blue: '#3488db', red: '#dc4641', green: '#4ea85c', black: '#25282a',
  orange: '#ed8738', cyan: '#35bfd1', white: '#e8eae7', purple: '#9b6de3'
};
const builtinPalette = [
  ['#f4c430', 'Żółty'], ['#3488db', 'Niebieski'], ['#dc4641', 'Czerwony'],
  ['#4ea85c', 'Zielony'], ['#ed8738', 'Pomarańczowy'], ['#35bfd1', 'Cyjan'],
  ['#9b6de3', 'Fioletowy'], ['#e8eae7', 'Biały'], ['#25282a', 'Czarny']
] as const;
const profileIcons = { router: Router, switch: Network, workstation: Box, server: Server, printer: Printer, uplink: Network };

function loadCustomColors(): string[] {
  try {
    const stored = JSON.parse(localStorage.getItem('virtulab.customCableColors') ?? 'null');
    if (Array.isArray(stored) && stored.length === 3 && stored.every(color => /^#[0-9a-f]{6}$/i.test(color))) return stored;
  } catch { /* Use defaults when storage was edited externally. */ }
  return ['#b15cff', '#ff5ca8', '#35d0ba'];
}

function toFlow(snapshot: WorkspaceSnapshot, onOpen: (device: Device) => void) {
  const portOwners = new Map<string, string>();
  const connectedPortColors: Record<string, string> = {};
  snapshot.devices.forEach(device => device.ports.forEach(port => portOwners.set(port.id, device.id)));
  snapshot.cables.forEach(cable => {
    const color = cableColors[cable.color] ?? cable.color;
    connectedPortColors[cable.port_a] = color;
    connectedPortColors[cable.port_b] = color;
  });
  const nodes: Array<Node<DeviceNodeData>> = snapshot.devices.map(device => ({
    id: device.id,
    type: 'device',
    position: { x: device.x, y: device.y },
    zIndex: 1,
    data: { device, connectedPortColors, onOpen }
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
      selectable: snapshot.workspace.cable_mode !== 'hidden',
      zIndex: 2
    }];
  });
  return { nodes, edges };
}

function CableInspector({ cable, onRemove }: { cable: WorkspaceCable; onRemove: () => void }) {
  return (
    <div className="inspector-content">
      <div className="cable-inspector-color" style={{ '--cable': cableColors[cable.color] ?? cable.color } as React.CSSProperties}>
        <Cable /><span><small>Połączenie</small><strong>{cable.medium}</strong></span>
      </div>
      <dl>
        <div><dt>Port A</dt><dd>{cable.port_a.split(':').at(-1)}</dd></div>
        <div><dt>Port B</dt><dd>{cable.port_b.split(':').at(-1)}</dd></div>
        <div><dt>Kolor</dt><dd>{cable.color}</dd></div>
      </dl>
      <button className="command-button danger" onClick={onRemove}><Trash2 />Odłącz kabel</button>
    </div>
  );
}

function ProductCanvas() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<DeviceNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [selectedCableId, setSelectedCableId] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState('#f4c430');
  const [customColors, setCustomColors] = useState(loadCustomColors);
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

  const selectedCable = snapshot?.cables.find(cable => cable.id === selectedCableId) ?? null;

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

  async function addDevice(profile: DeviceProfile, position?: { x: number; y: number }) {
    if (!snapshot) return;
    const center = position ?? flow?.screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 }) ?? { x: 0, y: 0 };
    setSaving(true);
    try {
      setSnapshot(await productApi.addDevice(snapshot.workspace.id, profile.id, center.x, center.y));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  function startToolboxDrag(event: DragEvent<HTMLButtonElement>, profile: DeviceProfile) {
    event.dataTransfer.setData('application/x-virtulab-profile', profile.id);
    event.dataTransfer.effectAllowed = 'copy';
  }

  function allowToolboxDrop(event: DragEvent) {
    if (!event.dataTransfer.types.includes('application/x-virtulab-profile')) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  }

  async function dropToolboxDevice(event: DragEvent) {
    const profileId = event.dataTransfer.getData('application/x-virtulab-profile');
    const profile = catalog?.profiles.find(item => item.id === profileId);
    if (!profile || !flow) return;
    event.preventDefault();
    await addDevice(profile, flow.screenToFlowPosition({ x: event.clientX, y: event.clientY }));
  }

  async function connectPorts(connection: Connection) {
    if (!snapshot || !connection.sourceHandle || !connection.targetHandle) return;
    setSaving(true);
    try {
      setSnapshot(await productApi.addCable(
        snapshot.workspace.id, connection.sourceHandle, connection.targetHandle, selectedColor
      ));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  async function updateDeviceOs(device: Device, osTemplate: string | null) {
    if (!snapshot) return;
    setSaving(true);
    try {
      setSnapshot(await productApi.updateDeviceOs(snapshot.workspace.id, device.id, osTemplate));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  async function chooseCableColor(color: string) {
    setSelectedColor(color);
    if (!snapshot || !selectedCableId) return;
    setSaving(true);
    try {
      setSnapshot(await productApi.updateCableColor(snapshot.workspace.id, selectedCableId, color));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  function overwriteCustomColor(index: number, color: string) {
    const next = customColors.map((current, slot) => slot === index ? color : current);
    setCustomColors(next);
    localStorage.setItem('virtulab.customCableColors', JSON.stringify(next));
    chooseCableColor(color);
  }

  async function removeSelectedCable() {
    if (!snapshot || !selectedCableId) return;
    setSaving(true);
    try {
      setSnapshot(await productApi.removeCable(snapshot.workspace.id, selectedCableId));
      setSelectedCableId(null);
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
        onConnect={connectPorts}
        onDragOver={allowToolboxDrop}
        onDrop={dropToolboxDevice}
        onNodeDragStop={persistPosition}
        onNodeClick={(_, node) => { setSelectedDevice(node.data.device); setSelectedCableId(null); }}
        onEdgeClick={(_, edge) => {
          setSelectedCableId(edge.id);
          setSelectedDevice(null);
          const cable = snapshot.cables.find(item => item.id === edge.id);
          if (cable) setSelectedColor(cableColors[cable.color] ?? cable.color);
        }}
        onPaneClick={() => { setSelectedDevice(null); setSelectedCableId(null); }}
        onInit={setFlow}
        fitView
        fitViewOptions={{ padding: 0.35, maxZoom: 0.75 }}
        minZoom={0.08}
        maxZoom={2.4}
        deleteKeyCode={null}
        nodesConnectable
        connectionMode={ConnectionMode.Loose}
        connectionLineType={ConnectionLineType.Bezier}
        connectionLineStyle={{ stroke: selectedColor, strokeWidth: 5 }}
        connectOnClick={false}
        elevateNodesOnSelect={false}
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

      <section className="cable-color-picker" aria-label="Kolor kabla">
        <span className="palette-label"><Cable />Kolor</span>
        {builtinPalette.map(([color, name]) => (
          <button
            key={color}
            className={`color-swatch ${selectedColor === color ? 'is-active' : ''}`}
            style={{ '--swatch': color } as React.CSSProperties}
            title={name}
            onClick={() => chooseCableColor(color)}
          />
        ))}
        <span className="palette-divider" />
        {customColors.map((color, index) => (
          <label
            className={`color-swatch custom-swatch ${selectedColor === color ? 'is-active' : ''}`}
            style={{ '--swatch': color } as React.CSSProperties}
            title={`Kolor własny ${index + 1}`}
            key={index}
          >
            <input type="color" value={color} onChange={event => overwriteCustomColor(index, event.target.value)} />
            <span>{index + 1}</span>
          </label>
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
                <button
                  className="profile-item"
                  key={profile.id}
                  draggable
                  onDragStart={event => startToolboxDrag(event, profile)}
                  onClick={() => addDevice(profile)}
                >
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
              {['workstation', 'server'].includes(selectedDevice.profile.kind) && (
                <label>System
                  <select
                    className="nodrag"
                    value={selectedDevice.os_template ?? ''}
                    onChange={event => updateDeviceOs(selectedDevice, event.target.value || null)}
                  >
                    <option value="">Bez systemu</option>
                    {catalog.templates.map(template => (
                      <option value={template.id} key={template.id}>{template.name}</option>
                    ))}
                  </select>
                </label>
              )}
              <dl>
                <div><dt>Porty</dt><dd>{selectedDevice.ports.length}</dd></div>
                <div><dt>Runtime</dt><dd>{selectedDevice.profile.runtime}</dd></div>
                <div><dt>Stan</dt><dd>{selectedDevice.status}</dd></div>
              </dl>
              <button className="command-button" onClick={() => setInternalDevice(selectedDevice)}><Settings2 />Sprzęt i system</button>
              <button className="command-button danger" onClick={removeSelected}><Trash2 />Usuń urządzenie</button>
            </div>
          ) : selectedCable ? (
            <CableInspector cable={selectedCable} onRemove={removeSelectedCable} />
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
          {internalDevice.profile.kind === 'printer' ? (
            <div className="printer-internal">
              <div className="printer-chassis">
                <Printer />
                <span><small>Wirtualna drukarka</small><strong>IPP Everywhere</strong></span>
              </div>
              <div className="printed-output">
                <FileOutput />
                <span><small>Odbiornik wydruków</small><strong>0 dokumentów</strong></span>
                <button className="command-button">Otwórz odbiornik</button>
              </div>
              <div className="printer-connectors">
                <div><Network /><span><small>Sieć</small><strong>Ethernet</strong></span></div>
                <div><Usb /><span><small>Połączenie lokalne</small><strong>USB-B</strong></span></div>
              </div>
            </div>
          ) : <div className="motherboard">
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
          </div>}
        </section>
      )}

      {error && <div className="error-toast"><span>{error}</span><button className="icon-button" onClick={() => setError(null)}><X /></button></div>}
    </main>
  );
}

export default function App() {
  return <ReactFlowProvider><ProductCanvas /></ReactFlowProvider>;
}
