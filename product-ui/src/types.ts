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
};

export type Template = {
  id: string;
  family: string;
  name: string;
  source: string;
};

export type Catalog = {
  schemaVersion: number;
  profiles: DeviceProfile[];
  templates: Template[];
  cableModes: CableMode[];
};

export type CableMode = 'realistic' | 'straight' | 'hidden';
