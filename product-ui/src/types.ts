export type LocalizedName = { pl: string; en: string };

export type Port = {
  id: string;
  device_id: string;
  port_key: string;
  name: string;
  connector: string;
  medium: string;
  side: 'left' | 'right' | 'top' | 'bottom';
  ordinal: number;
  max_links: number;
};

export type ProfilePort = {
  key: string;
  name: string;
  connector: string;
  medium: string;
  side: Port['side'];
};

export type DeviceProfile = {
  id: string;
  kind: string;
  name: LocalizedName;
  model: string;
  runtime: string;
  accent: string;
  ports: ProfilePort[];
  defaultHardware?: Record<string, number | string>;
};

export type Device = {
  id: string;
  workspace_id: string;
  profile_id: string;
  name: string;
  x: number;
  y: number;
  z: number;
  status: string;
  os_template: string | null;
  hardware: Record<string, unknown>;
  profile: DeviceProfile;
  ports: Port[];
};

export type Cable = {
  id: string;
  workspace_id: string;
  port_a: string;
  port_b: string;
  medium: string;
  color: string;
};

export type Workspace = {
  id: string;
  name: string;
  locale: string;
  theme: string;
  cable_mode: CableMode;
  revision: number;
};

export type WorkspaceSnapshot = {
  schemaVersion: number;
  workspace: Workspace;
  devices: Device[];
  cables: Cable[];
  documents: PrintDocument[];
};

export type Template = {
  id: string;
  family: string;
  type: string;
  name: string;
  icon: string;
  description: string;
  tags: string[];
  source: string;
  status?: string;
  sourceValue?: string | null;
};

export type OsProject = {
  id: string;
  name: string;
  description: string;
  os_type: string;
  icon: string;
  tags: string[];
  source_kind: string;
  source_value: string | null;
  status: string;
};

export type PrintDocument = {
  id: string;
  workspace_id: string;
  printer_id: string;
  name: string;
  pages: number;
  location: 'canvas' | 'hud';
  x: number;
  y: number;
  created_at: number;
};

export type Catalog = {
  schemaVersion: number;
  profiles: DeviceProfile[];
  templates: Template[];
  cableModes: CableMode[];
};

export type CableMode = 'realistic' | 'straight' | 'hidden';
