import { useEffect, useRef, useState, type DragEvent } from 'react';
import {
  Background,
  BackgroundVariant,
  ConnectionMode,
  ConnectionLineType,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type NodeChange,
  useEdgesState,
  useNodesState,
  type Edge,
  type Connection,
  type OnConnectStartParams,
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
  Files,
  HardDrive,
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
import { DeviceUnderlay } from './DeviceUnderlay';
import { HardwareEditor } from './HardwareEditor';
import { OsPicker } from './OsPicker';
import { OsTool, type OsProjectDraft } from './OsTool';
import { PrintDocumentNode, type PrintDocumentNodeData } from './PrintDocumentNode';
import { RackNode, type RackNodeData } from './RackNode';
import { RealisticConnectionLine } from './RealisticConnectionLine';
import type { Cable as WorkspaceCable, CableMode, Catalog, Device, DeviceProfile, OsProject, PrintDocument, WorkspaceSnapshot } from './types';
import './styles.css';

const nodeTypes = { device: DeviceNode, underlay: DeviceUnderlay, rack: RackNode, document: PrintDocumentNode };
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

function profileDimensions(profile: DeviceProfile) {
  if (profile.kind === 'switch') return { width: 650, height: 220 };
  if (profile.kind === 'printer') return { width: 330, height: 245 };
  if (profile.kind === 'rack') return {
    width: Number(profile.defaultHardware?.rackWidth ?? 520),
    height: 58 + Number(profile.defaultHardware?.rackUnits ?? 24) * 24
  };
  return { width: 290, height: profile.ports.some(port => port.side !== 'bottom') ? 220 : 185 };
}

const RACK_TOP_INSET = 12;
const RACK_DEVICE_GAP = 8;
const RACK_BOTTOM_SPACE = 72;
const RACK_HEADER_HEIGHT = 58;

function loadCustomColors(): string[] {
  try {
    const stored = JSON.parse(localStorage.getItem('virtulab.customCableColors') ?? 'null');
    if (Array.isArray(stored) && stored.length === 3 && stored.every(color => /^#[0-9a-f]{6}$/i.test(color))) return stored;
  } catch { /* Use defaults when storage was edited externally. */ }
  return ['#b15cff', '#ff5ca8', '#35d0ba'];
}

function toFlow(
  snapshot: WorkspaceSnapshot,
  onOpen: (device: Device) => void,
  onStoreDocument: (document: PrintDocument) => void,
  onAction: (device: Device, action: string) => void,
  runtimeStates: Record<string, string>,
  measuredHeights: Record<string, number>
) {
  const portOwners = new Map<string, string>();
  const connectedPortColors: Record<string, string> = {};
  snapshot.devices.forEach(device => device.ports.forEach(port => portOwners.set(port.id, device.id)));
  snapshot.cables.forEach(cable => {
    const color = cableColors[cable.color] ?? cable.color;
    connectedPortColors[cable.port_a] = color;
    connectedPortColors[cable.port_b] = color;
  });
  const racks = new Map(snapshot.devices.filter(device => device.profile.kind === 'rack').map(device => [device.id, device]));
  const rackLayouts = new Map<string, { height: number; positions: Map<string, { x: number; y: number }>; mounted: Device[] }>();
  racks.forEach(rack => {
    const mounted = snapshot.devices
      .filter(device => device.hardware.rackId === rack.id)
      .sort((a, b) => Number(a.hardware.rackUnit ?? 0) - Number(b.hardware.rackUnit ?? 0));
    const positions = new Map<string, { x: number; y: number }>();
    let offset = RACK_HEADER_HEIGHT + RACK_TOP_INSET;
    mounted.forEach(device => {
      positions.set(device.id, { x: rack.x + 20, y: rack.y + offset });
      offset += (measuredHeights[device.id] ?? profileDimensions(device.profile).height) + RACK_DEVICE_GAP;
    });
    rackLayouts.set(rack.id, {
      mounted,
      positions,
      height: offset + RACK_BOTTOM_SPACE - (mounted.length ? RACK_DEVICE_GAP : 0)
    });
  });
  const nodes: Node[] = [];
  snapshot.devices.forEach(device => {
    if (device.profile.kind === 'rack') {
      const layout = rackLayouts.get(device.id)!;
      nodes.push({
        id: device.id,
        type: 'rack',
        position: { x: device.x, y: device.y },
        zIndex: 0,
        data: { device, mounted: layout.mounted, rackHeight: layout.height } satisfies RackNodeData,
        style: { width: Number(device.hardware.rackWidth ?? 520), height: layout.height }
      });
      return;
    }
    const runtimeDevice = { ...device, status: runtimeStates[device.id] ?? device.status };
    const rack = typeof device.hardware.rackId === 'string' ? racks.get(device.hardware.rackId) : undefined;
    const mountedWidth = rack ? Number(rack.hardware.rackWidth ?? 520) - 40 : undefined;
    const position = rack
      ? rackLayouts.get(rack.id)?.positions.get(device.id) ?? { x: rack.x + 20, y: rack.y + RACK_HEADER_HEIGHT + RACK_TOP_INSET }
      : { x: device.x, y: device.y };
    nodes.push({
      id: `underlay:${device.id}`,
      type: 'underlay',
      position,
      zIndex: 1,
      draggable: false,
      selectable: false,
      focusable: false,
      data: { device: runtimeDevice, mountedWidth },
      style: mountedWidth ? { width: mountedWidth } : undefined
    });
    nodes.push({
      id: device.id,
      type: 'device',
      position,
      zIndex: 5,
      data: { device: runtimeDevice, connectedPortColors, onOpen, onAction, mountedWidth } satisfies DeviceNodeData,
      style: mountedWidth ? { width: mountedWidth } : undefined
    });
  });
  snapshot.documents.filter(document => document.location === 'canvas').forEach(document => {
    nodes.push({
      id: `document:${document.id}`,
      type: 'document',
      position: { x: document.x, y: document.y },
      zIndex: 4,
      data: { document, onStore: onStoreDocument } satisfies PrintDocumentNodeData
    });
  });
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
      zIndex: 4
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
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [selectedCableId, setSelectedCableId] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState('#f4c430');
  const [customColors, setCustomColors] = useState(loadCustomColors);
  const [internalDevice, setInternalDevice] = useState<Device | null>(null);
  const [toolboxOpen, setToolboxOpen] = useState(() => window.innerWidth > 900);
  const [inspectorOpen, setInspectorOpen] = useState(() => window.innerWidth > 900);
  const [flow, setFlow] = useState<ReactFlowInstance<Node, Edge> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [osPickerDevice, setOsPickerDevice] = useState<Device | null>(null);
  const [osToolOpen, setOsToolOpen] = useState(false);
  const [printTrayOpen, setPrintTrayOpen] = useState(false);
  const [runtimeStates, setRuntimeStates] = useState<Record<string, string>>({});
  const [measuredHeights, setMeasuredHeights] = useState<Record<string, number>>({});
  const cableDrag = useRef<{ cable: WorkspaceCable | null; completed: boolean }>({ cable: null, completed: false });
  const deviceDragActive = useRef(false);
  const rackDragTarget = useRef<{ rackId: string; index: number } | null>(null);

  const openDevice = (device: Device) => {
    if (['workstation', 'server'].includes(device.profile.kind)) setInternalDevice(device);
  };

  async function storeDocument(document: PrintDocument) {
    if (!snapshot) return;
    setSnapshot(await productApi.moveDocument(snapshot.workspace.id, document.id, 'hud'));
  }

  async function refreshRuntimeStates() {
    try { setRuntimeStates((await productApi.stableState()).vms); } catch { /* Stable lab may not be prepared yet. */ }
  }

  async function deviceAction(device: Device, action: string) {
    try {
      await productApi.vmAction(device.id, action);
      window.setTimeout(refreshRuntimeStates, action === 'shutdown' ? 1200 : 250);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  useEffect(() => {
    Promise.all([productApi.catalog(), productApi.workspace('default')])
      .then(([nextCatalog, nextSnapshot]) => {
        setCatalog(nextCatalog);
        setSnapshot(nextSnapshot);
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  useEffect(() => {
    refreshRuntimeStates();
    const timer = window.setInterval(refreshRuntimeStates, 3000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!snapshot) return;
    if (deviceDragActive.current) return;
    const flowState = toFlow(snapshot, openDevice, storeDocument, deviceAction, runtimeStates, measuredHeights);
    setNodes(flowState.nodes);
    setEdges(cableDrag.current.cable && !cableDrag.current.completed
      ? flowState.edges.filter(edge => edge.id !== cableDrag.current.cable?.id)
      : flowState.edges);
    if (selectedDevice) {
      setSelectedDevice(snapshot.devices.find(device => device.id === selectedDevice.id) ?? null);
    }
    if (internalDevice) setInternalDevice(snapshot.devices.find(device => device.id === internalDevice.id) ?? null);
    if (osPickerDevice) setOsPickerDevice(snapshot.devices.find(device => device.id === osPickerDevice.id) ?? null);
  }, [snapshot, runtimeStates, measuredHeights]);

  const selectedCable = snapshot?.cables.find(cable => cable.id === selectedCableId) ?? null;

  function handleNodesChange(changes: NodeChange<Node>[]) {
    const measured = changes.filter(change =>
      change.type === 'dimensions' && !change.id.startsWith('underlay:') && change.dimensions?.height
    );
    if (measured.length) {
      setMeasuredHeights(current => {
        let changed = false;
        const next = { ...current };
        for (const change of measured) {
          if (change.type !== 'dimensions' || !change.dimensions) continue;
          if (Math.abs((next[change.id] ?? 0) - change.dimensions.height) > 0.5) {
            next[change.id] = change.dimensions.height;
            changed = true;
          }
        }
        return changed ? next : current;
      });
    }
    const mirrored = changes.flatMap(change => {
      if (!['position', 'dimensions'].includes(change.type) || change.id.startsWith('underlay:')) return [change];
      if (change.type === 'position') {
        const current = nodes.find(node => node.id === change.id);
        if (current?.type === 'rack' && change.position) {
          const dx = change.position.x - current.position.x;
          const dy = change.position.y - current.position.y;
          const mountedChanges = nodes.flatMap(node => {
            if (node.type !== 'device') return [];
            const device = (node.data as DeviceNodeData).device;
            if (device.hardware.rackId !== change.id) return [];
            const position = { x: node.position.x + dx, y: node.position.y + dy };
            return [
              { type: 'position', id: node.id, position, dragging: change.dragging } as NodeChange<Node>,
              { type: 'position', id: `underlay:${node.id}`, position, dragging: change.dragging } as NodeChange<Node>
            ];
          });
          return [change, ...mountedChanges];
        }
        if (current?.type === 'device' && change.position) {
          const dragged = (current.data as DeviceNodeData).device;
          const draggedHeight = measuredHeights[dragged.id] ?? profileDimensions(dragged.profile).height;
          const candidate = nodes.find(node => {
            if (node.type !== 'rack') return false;
            const rack = (node.data as RackNodeData).device;
            const rackWidth = Number(rack.hardware.rackWidth ?? 520);
            const rackHeight = Number(node.measured?.height ?? node.height ?? 0);
            const lockedX = node.position.x + 20;
            const centerY = change.position!.y + draggedHeight / 2;
            return Math.abs(change.position!.x - lockedX) <= 120
              && centerY >= node.position.y + RACK_HEADER_HEIGHT
              && centerY <= node.position.y + rackHeight;
          });
          const oldRack = typeof dragged.hardware.rackId === 'string'
            ? nodes.find(node => node.id === dragged.hardware.rackId && node.type === 'rack')
            : undefined;
          if (candidate) {
            const rackDevice = (candidate.data as RackNodeData).device;
            const others = snapshot?.devices
              .filter(device => device.hardware.rackId === rackDevice.id && device.id !== dragged.id)
              .sort((a, b) => Number(a.hardware.rackUnit ?? 0) - Number(b.hardware.rackUnit ?? 0)) ?? [];
            const lockedPosition = { x: candidate.position.x + 20, y: change.position.y };
            const draggedCenter = change.position.y + draggedHeight / 2;
            let offset = candidate.position.y + RACK_HEADER_HEIGHT + RACK_TOP_INSET;
            let insertionIndex = 0;
            for (const other of others) {
              const height = measuredHeights[other.id] ?? profileDimensions(other.profile).height;
              if (draggedCenter > offset + height / 2) insertionIndex += 1;
              offset += height + RACK_DEVICE_GAP;
            }
            const order = [...others];
            order.splice(insertionIndex, 0, dragged);
            rackDragTarget.current = { rackId: rackDevice.id, index: insertionIndex };
            let slotY = candidate.position.y + RACK_HEADER_HEIGHT + RACK_TOP_INSET;
            const siblingChanges: NodeChange<Node>[] = [];
            for (const item of order) {
              const position = { x: candidate.position.x + 20, y: slotY };
              if (item.id !== dragged.id) {
                siblingChanges.push(
                  { type: 'position', id: item.id, position, dragging: true },
                  { type: 'position', id: `underlay:${item.id}`, position, dragging: true }
                );
              }
              slotY += (measuredHeights[item.id] ?? profileDimensions(item.profile).height) + RACK_DEVICE_GAP;
            }
            return [
              { ...change, position: lockedPosition },
              { ...change, id: `underlay:${change.id}`, position: lockedPosition },
              ...siblingChanges
            ];
          }
          rackDragTarget.current = null;
          if (oldRack) {
            const remaining = snapshot?.devices
              .filter(device => device.hardware.rackId === dragged.hardware.rackId && device.id !== dragged.id)
              .sort((a, b) => Number(a.hardware.rackUnit ?? 0) - Number(b.hardware.rackUnit ?? 0)) ?? [];
            let slotY = oldRack.position.y + RACK_HEADER_HEIGHT + RACK_TOP_INSET;
            const collapseChanges: NodeChange<Node>[] = [];
            for (const item of remaining) {
              const position = { x: oldRack.position.x + 20, y: slotY };
              collapseChanges.push(
                { type: 'position', id: item.id, position, dragging: true },
                { type: 'position', id: `underlay:${item.id}`, position, dragging: true }
              );
              slotY += (measuredHeights[item.id] ?? profileDimensions(item.profile).height) + RACK_DEVICE_GAP;
            }
            return [change, { ...change, id: `underlay:${change.id}` }, ...collapseChanges];
          }
        }
      }
      if (change.type === 'dimensions') {
        return [change, { ...change, id: `underlay:${change.id}`, setAttributes: true }];
      }
      return [change, { ...change, id: `underlay:${change.id}` }];
    });
    onNodesChange(mirrored);
  }

  const persistPosition: OnNodeDrag<Node> = async (_, node) => {
    if (!snapshot) return;
    setSaving(true);
    try {
      if (node.type === 'document') {
        const document = (node.data as PrintDocumentNodeData).document;
        setSnapshot(await productApi.moveDocument(
          snapshot.workspace.id, document.id, 'canvas', node.position.x, node.position.y
        ));
        return;
      }
      const device = (node.data as DeviceNodeData | RackNodeData).device;
      const positions = [{ id: node.id, x: node.position.x, y: node.position.y }];
      let next = await productApi.updateCanvas(snapshot.workspace.id, { positions });
      if (device.profile.kind !== 'rack') {
        const target = rackDragTarget.current;
        let sortKey: number | undefined;
        if (target) {
          const others = snapshot.devices
            .filter(item => item.hardware.rackId === target.rackId && item.id !== device.id)
            .sort((a, b) => Number(a.hardware.rackUnit ?? 0) - Number(b.hardware.rackUnit ?? 0));
          sortKey = target.index === 0 ? 0 : Number(others[target.index - 1]?.hardware.rackUnit ?? 0) + 1;
        }
        next = await productApi.mountDevice(snapshot.workspace.id, device.id, target?.rackId ?? null, sortKey);
      }
      setSnapshot(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      deviceDragActive.current = false;
      rackDragTarget.current = null;
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
    const dimensions = profileDimensions(profile);
    setSaving(true);
    try {
      setSnapshot(await productApi.addDevice(
        snapshot.workspace.id,
        profile.id,
        center.x - dimensions.width / 2,
        center.y - dimensions.height / 2
      ));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  function startToolboxDrag(event: DragEvent<HTMLButtonElement>, profile: DeviceProfile) {
    event.dataTransfer.setData('application/x-virtulab-profile', profile.id);
    event.dataTransfer.effectAllowed = 'copy';
    const ghost = document.createElement('div');
    ghost.className = `toolbox-device-ghost is-${profile.kind}`;
    ghost.style.setProperty('--accent', profile.accent);
    const heading = document.createElement('strong');
    heading.textContent = profile.name.pl;
    const model = document.createElement('small');
    model.textContent = profile.model;
    const ports = document.createElement('div');
    ports.className = 'ghost-ports';
    profile.ports.slice(0, 28).forEach(port => {
      const socket = document.createElement('span');
      socket.title = port.name;
      ports.append(socket);
    });
    const status = document.createElement('footer');
    status.textContent = '●  Wyłączone';
    ghost.append(heading, model, ports, status);
    document.body.append(ghost);
    event.dataTransfer.setDragImage(ghost, ghost.offsetWidth / 2, ghost.offsetHeight / 2);
    requestAnimationFrame(() => ghost.remove());
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
    cableDrag.current.completed = true;
    setSaving(true);
    try {
      setSnapshot(await productApi.addCable(
        snapshot.workspace.id,
        connection.sourceHandle,
        connection.targetHandle,
        cableDrag.current.cable ? cableColors[cableDrag.current.cable.color] ?? cableDrag.current.cable.color : selectedColor
      ));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  function startCableDrag(_: MouseEvent | TouchEvent, params: OnConnectStartParams) {
    const cable = snapshot?.cables.find(item => item.port_a === params.handleId || item.port_b === params.handleId) ?? null;
    cableDrag.current = { cable, completed: false };
    if (cable) {
      setSelectedColor(cableColors[cable.color] ?? cable.color);
      setEdges(current => current.filter(edge => edge.id !== cable.id));
    }
  }

  async function finishCableDrag() {
    const detached = cableDrag.current;
    cableDrag.current = { cable: null, completed: false };
    if (!snapshot || !detached.cable || detached.completed) return;
    setSaving(true);
    try {
      setSnapshot(await productApi.removeCable(snapshot.workspace.id, detached.cable.id));
      if (selectedCableId === detached.cable.id) setSelectedCableId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setSnapshot(await productApi.workspace(snapshot.workspace.id));
    } finally {
      setSaving(false);
    }
  }

  async function updateDeviceOs(device: Device, osTemplate: string | null) {
    if (!snapshot) return;
    setSaving(true);
    try {
      setSnapshot(await productApi.updateDeviceOs(snapshot.workspace.id, device.id, osTemplate));
      setOsPickerDevice(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  async function updateHardware(device: Device, hardware: Record<string, number | string>) {
    if (!snapshot) return;
    setSnapshot(await productApi.updateDeviceHardware(snapshot.workspace.id, device.id, hardware));
  }

  async function updateRack(device: Device, field: 'rackUnits' | 'rackWidth', value: number) {
    if (!snapshot) return;
    setSaving(true);
    try {
      setSnapshot(await productApi.updateDeviceHardware(snapshot.workspace.id, device.id, {
        rackUnits: Number(device.hardware.rackUnits ?? 24),
        rackWidth: Number(device.hardware.rackWidth ?? 520),
        [field]: value
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setSaving(false); }
  }

  async function createOsProject(draft: OsProjectDraft): Promise<OsProject> {
    const result = await productApi.createOsProject(draft);
    let project = result.project;
    if (draft.file) project = (await productApi.uploadOsMedia(project.id, draft.file)).project;
    setCatalog(await productApi.catalog());
    return project;
  }

  async function startOsBuilder(project: OsProject) {
    try { await productApi.startOsBuilder(project.id); setCatalog(await productApi.catalog()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  async function sealOsBuilder(project: OsProject) {
    try { await productApi.sealOsBuilder(project.id); setCatalog(await productApi.catalog()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  async function moveDocumentToCanvas(document: PrintDocument) {
    if (!snapshot) return;
    const center = flow?.screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 }) ?? { x: 0, y: 0 };
    setSnapshot(await productApi.moveDocument(snapshot.workspace.id, document.id, 'canvas', center.x, center.y));
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

  useEffect(() => {
    const deleteSelection = (event: KeyboardEvent) => {
      if (!['Delete', 'Backspace'].includes(event.key)) return;
      if (internalDevice || osPickerDevice || osToolOpen) return;
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement) return;
      event.preventDefault();
      if (selectedCableId) removeSelectedCable();
      else if (selectedDevice) removeSelected();
    };
    window.addEventListener('keydown', deleteSelection);
    return () => window.removeEventListener('keydown', deleteSelection);
  }, [selectedCableId, selectedDevice, snapshot, internalDevice, osPickerDevice, osToolOpen]);

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
        onNodesChange={handleNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={connectPorts}
        onConnectStart={startCableDrag}
        onConnectEnd={finishCableDrag}
        onDragOver={allowToolboxDrop}
        onDrop={dropToolboxDevice}
        onNodeDragStart={() => { deviceDragActive.current = true; }}
        onNodeDragStop={persistPosition}
        onNodeClick={(_, node) => {
          if (node.type === 'document') return;
          if (node.type === 'underlay') return;
          setSelectedDevice((node.data as DeviceNodeData | RackNodeData).device);
          setSelectedCableId(null);
        }}
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
        connectionLineComponent={RealisticConnectionLine}
        connectionLineStyle={{ stroke: selectedColor, strokeWidth: 5 }}
        connectOnClick={false}
        elevateNodesOnSelect={false}
        selectionOnDrag
        panOnScroll
        zoomOnDoubleClick={false}
      >
        <Background color="#343634" gap={24} size={1} variant={BackgroundVariant.Dots} />
        <MiniMap className="canvas-minimap" pannable zoomable nodeColor={node => {
          if (node.type === 'document') return '#e7e5dd';
          if (node.type === 'underlay') return 'transparent';
          return (node.data as DeviceNodeData | RackNodeData).device.profile.accent;
        }} />
        <Controls className="canvas-controls" showInteractive={false} />
      </ReactFlow>

      <header className="floating-topbar">
        <button className="brand-button" title="Menu główne"><span>VL</span></button>
        <div className="workspace-name">
          <strong>{snapshot.workspace.name}</strong>
          <small>{saving ? 'Zapisywanie...' : `Wersja ${snapshot.workspace.revision}`}</small>
        </div>
        <button className="icon-button" title="Biblioteka laboratoriów"><Library /></button>
        <button className="icon-button" title="Obrazy systemów" onClick={() => setOsToolOpen(true)}><HardDrive /></button>
        <button className="icon-button" title="Odbiornik wydruków" onClick={() => setPrintTrayOpen(value => !value)}><Files /></button>
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
                  <button className="os-picker-trigger" onClick={() => setOsPickerDevice(selectedDevice)}>
                    <HardDrive />
                    <span><strong>{catalog.templates.find(template => template.id === selectedDevice.os_template)?.name ?? 'Bez systemu'}</strong><small>Wybierz z biblioteki</small></span>
                  </button>
                </label>
              )}
              {selectedDevice.profile.kind === 'rack' && (
                <div className="rack-settings">
                  <label>Szerokość<input type="number" min="320" max="1200" step="20" value={Number(selectedDevice.hardware.rackWidth ?? 520)} onChange={event => updateRack(selectedDevice, 'rackWidth', Number(event.target.value))} /></label>
                </div>
              )}
              <dl>
                <div><dt>Porty</dt><dd>{selectedDevice.ports.length}</dd></div>
                <div><dt>Runtime</dt><dd>{selectedDevice.profile.runtime}</dd></div>
                <div><dt>Stan</dt><dd>{selectedDevice.status}</dd></div>
              </dl>
              {['workstation', 'server'].includes(selectedDevice.profile.kind) && (
                <button className="command-button" onClick={() => setInternalDevice(selectedDevice)}><Settings2 />Sprzęt i system</button>
              )}
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
        <HardwareEditor
          device={internalDevice}
          onSave={hardware => updateHardware(internalDevice, hardware)}
          onClose={() => setInternalDevice(null)}
        />
      )}

      {osPickerDevice && (
        <OsPicker
          templates={catalog.templates.filter(template => template.family !== 'custom' || template.status === 'sealed')}
          value={osPickerDevice.os_template}
          onSelect={template => updateDeviceOs(osPickerDevice, template)}
          onClose={() => setOsPickerDevice(null)}
          onBuild={() => { setOsPickerDevice(null); setOsToolOpen(true); }}
        />
      )}

      {osToolOpen && (
        <OsTool
          catalog={catalog}
          onCreate={createOsProject}
          onStart={startOsBuilder}
          onSeal={sealOsBuilder}
          onClose={() => setOsToolOpen(false)}
        />
      )}

      {printTrayOpen && (
        <aside className="print-tray-panel">
          <header><span><small>HUD</small><strong>Odbiornik wydruków</strong></span><button className="icon-button" title="Zamknij" onClick={() => setPrintTrayOpen(false)}><X /></button></header>
          <div>
            {snapshot.documents.filter(document => document.location === 'hud').map(document => (
              <article key={document.id}><Files /><span><strong>{document.name}</strong><small>{document.pages} str.</small></span><button className="command-button" onClick={() => moveDocumentToCanvas(document)}>Na płótno</button></article>
            ))}
            {snapshot.documents.every(document => document.location !== 'hud') && <p>Brak dokumentów w odbiorniku</p>}
          </div>
        </aside>
      )}

      {error && <div className="error-toast"><span>{error}</span><button className="icon-button" onClick={() => setError(null)}><X /></button></div>}
    </main>
  );
}

export default function App() {
  return <ReactFlowProvider><ProductCanvas /></ReactFlowProvider>;
}
