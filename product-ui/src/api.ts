import type { Catalog, OsProject, WorkspaceSnapshot } from './types';

type StableState = { vms: Record<string, string> };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) }
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? `Request failed (${response.status})`);
  return data as T;
}

export const productApi = {
  catalog: () => request<Catalog>('/api/product/catalog'),
  stableState: () => request<StableState>('/api/state'),
  vmAction: (vm: string, action: string) => request<{ ok: boolean; message: string }>(`/api/vm/${vm}/${action}`, {
    method: 'POST',
    body: '{}'
  }),
  workspace: (id: string) => request<WorkspaceSnapshot>(`/api/product/workspaces/${id}`),
  updateCanvas: (
    id: string,
    body: { positions: Array<{ id: string; x: number; y: number }>; cableMode?: string }
  ) => request<WorkspaceSnapshot>(`/api/product/workspaces/${id}/canvas`, {
    method: 'PUT',
    body: JSON.stringify(body)
  }),
  addDevice: (id: string, profileId: string, x: number, y: number) =>
    request<WorkspaceSnapshot>(`/api/product/workspaces/${id}/devices`, {
      method: 'POST',
      body: JSON.stringify({ profileId, x, y })
    }),
  removeDevice: (workspaceId: string, deviceId: string) =>
    request<WorkspaceSnapshot>(`/api/product/workspaces/${workspaceId}/devices/${deviceId}`, {
      method: 'DELETE'
    }),
  updateDeviceOs: (workspaceId: string, deviceId: string, osTemplate: string | null) =>
    request<WorkspaceSnapshot>(`/api/product/workspaces/${workspaceId}/devices/${deviceId}`, {
      method: 'PUT',
      body: JSON.stringify({ osTemplate })
    }),
  updateDeviceHardware: (workspaceId: string, deviceId: string, hardware: Record<string, number | string>) =>
    request<WorkspaceSnapshot>(`/api/product/workspaces/${workspaceId}/devices/${deviceId}`, {
      method: 'PUT',
      body: JSON.stringify({ hardware })
    }),
  mountDevice: (workspaceId: string, deviceId: string, rackId: string | null, rackUnit?: number) =>
    request<WorkspaceSnapshot>(`/api/product/workspaces/${workspaceId}/devices/${deviceId}`, {
      method: 'PUT',
      body: JSON.stringify({ mount: { rackId, rackUnit } })
    }),
  addCable: (workspaceId: string, portA: string, portB: string, color: string) =>
    request<WorkspaceSnapshot>(`/api/product/workspaces/${workspaceId}/cables`, {
      method: 'POST',
      body: JSON.stringify({ portA, portB, color })
    }),
  updateCableColor: (workspaceId: string, cableId: string, color: string) =>
    request<WorkspaceSnapshot>(`/api/product/workspaces/${workspaceId}/cables/${cableId}`, {
      method: 'PUT',
      body: JSON.stringify({ color })
    }),
  removeCable: (workspaceId: string, cableId: string) =>
    request<WorkspaceSnapshot>(`/api/product/workspaces/${workspaceId}/cables/${cableId}`, {
      method: 'DELETE'
    }),
  createOsProject: (body: {
    name: string;
    description: string;
    type: string;
    icon: string;
    tags: string[];
    sourceKind: string;
    sourceValue?: string;
  }) => request<{ catalog: Catalog; project: OsProject }>('/api/product/templates', { method: 'POST', body: JSON.stringify(body) }),
  uploadOsMedia: async (projectId: string, file: File) => {
    const response = await fetch(`/api/product/templates/${projectId}/media`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream', 'X-Filename': encodeURIComponent(file.name) },
      body: file
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? `Upload failed (${response.status})`);
    return data as { ok: boolean; project: OsProject };
  },
  startOsBuilder: (projectId: string) => request<{ ok: boolean; message: string }>(`/api/product/templates/${projectId}/start`, { method: 'POST', body: '{}' }),
  sealOsBuilder: (projectId: string) => request<{ ok: boolean; message: string }>(`/api/product/templates/${projectId}/seal`, { method: 'POST', body: '{}' }),
  moveDocument: (
    workspaceId: string,
    documentId: string,
    location: 'canvas' | 'hud',
    x = 0,
    y = 0
  ) => request<WorkspaceSnapshot>(`/api/product/workspaces/${workspaceId}/documents/${documentId}`, {
    method: 'PUT',
    body: JSON.stringify({ location, x, y })
  })
};
