import type { Catalog, WorkspaceSnapshot } from './types';

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
    })
};
