from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


SCHEMA_VERSION = 2
CABLE_MODES = {"realistic", "straight", "hidden"}
BUILTIN_CABLE_COLORS = {"yellow", "blue", "red", "green", "black", "orange", "cyan", "white", "purple"}


def _ports(prefix: str, count: int, connector: str = "rj45", medium: str = "ethernet") -> list[dict]:
    return [
        {
            "key": f"{prefix}{number}",
            "name": f"{prefix.upper()} {number}",
            "connector": connector,
            "medium": medium,
            "side": "bottom",
        }
        for number in range(1, count + 1)
    ]


DEVICE_PROFILES = {
    "mikrotik-rb960pgs": {
        "id": "mikrotik-rb960pgs",
        "kind": "router",
        "name": {"pl": "Router MikroTik", "en": "MikroTik router"},
        "model": "RB960PGS / CHR",
        "runtime": "libvirt",
        "accent": "#9dcc4a",
        "ports": [
            *[
                {
                    "key": f"ether{number}",
                    "name": f"ether{number}",
                    "connector": "rj45",
                    "medium": "ethernet",
                    "side": "bottom",
                }
                for number in range(1, 6)
            ],
            {
                "key": "sfp1",
                "name": "SFP 1",
                "connector": "sfp",
                "medium": "fiber",
                "side": "bottom",
            },
        ],
    },
    "x86-workstation": {
        "id": "x86-workstation",
        "kind": "workstation",
        "name": {"pl": "Stacja robocza", "en": "Workstation"},
        "model": "Generic x86-64",
        "runtime": "libvirt",
        "accent": "#45a7c7",
        "defaultHardware": {"cpuType": "host-model", "cpuCores": 4, "memoryMib": 6144, "diskGib": 80, "networkCards": 2},
        "ports": [
            *_ports("nic", 2),
            {"key": "usb1", "name": "USB 1", "connector": "usb-a", "medium": "usb", "side": "right"},
            {"key": "usb2", "name": "USB 2", "connector": "usb-a", "medium": "usb", "side": "right"},
        ],
    },
    "x86-server": {
        "id": "x86-server",
        "kind": "server",
        "name": {"pl": "Serwer", "en": "Server"},
        "model": "Generic x86-64 server",
        "runtime": "libvirt",
        "accent": "#d69b3f",
        "defaultHardware": {"cpuType": "host-model", "cpuCores": 4, "memoryMib": 8192, "diskGib": 120, "networkCards": 4},
        "ports": [*_ports("nic", 4), {"key": "console", "name": "Console", "connector": "serial", "medium": "serial", "side": "right"}],
    },
    "tplink-sg3428": {
        "id": "tplink-sg3428",
        "kind": "switch",
        "name": {"pl": "Przełącznik zarządzalny", "en": "Managed switch"},
        "model": "JetStream SG3428 behavioral profile",
        "runtime": "switch-appliance",
        "accent": "#46b889",
        "ports": [
            *_ports("ge", 24),
            *_ports("sfp", 4, "sfp", "fiber"),
            {"key": "console-rj45", "name": "Console", "connector": "rj45-console", "medium": "console", "side": "right"},
            {"key": "console-usb", "name": "Micro-USB", "connector": "micro-usb", "medium": "usb", "side": "right"},
        ],
    },
    "virtual-printer": {
        "id": "virtual-printer",
        "kind": "printer",
        "name": {"pl": "Drukarka sieciowa", "en": "Network printer"},
        "model": "IPP Everywhere / PDF output",
        "runtime": "printer-appliance",
        "accent": "#ce6b5c",
        "ports": [
            {"key": "ethernet", "name": "Ethernet", "connector": "rj45", "medium": "ethernet", "side": "bottom"},
            {"key": "usb", "name": "USB-B", "connector": "usb-b", "medium": "usb", "side": "right"},
        ],
    },
    "server-rack": {
        "id": "server-rack",
        "kind": "rack",
        "name": {"pl": "Szafa serwerowa", "en": "Server rack"},
        "model": "Adjustable 19-inch rack",
        "runtime": "passive",
        "accent": "#8f9690",
        "defaultHardware": {"rackUnits": 24, "rackWidth": 520},
        "ports": [],
    },
    "internet": {
        "id": "internet",
        "kind": "uplink",
        "name": {"pl": "Internet", "en": "Internet"},
        "model": "libvirt NAT",
        "runtime": "internet",
        "accent": "#d0b34c",
        "ports": [{"key": "uplink", "name": "WAN", "connector": "rj45", "medium": "ethernet", "side": "bottom"}],
    },
}


TEMPLATE_CATALOG = [
    {"id": "windows-11", "family": "windows", "type": "desktop", "name": "Windows 11", "icon": "windows", "description": "Microsoft desktop operating system", "tags": ["desktop", "microsoft", "inf02"], "source": "microsoft-connector"},
    {"id": "windows-server", "family": "windows", "type": "server", "name": "Windows Server Evaluation", "icon": "server", "description": "Microsoft server evaluation image", "tags": ["server", "microsoft", "active-directory"], "source": "official-download"},
    {"id": "debian", "family": "linux", "type": "general", "name": "Debian", "icon": "terminal", "description": "Stable community Linux distribution", "tags": ["linux", "server", "desktop"], "source": "official-download"},
    {"id": "ubuntu-lts", "family": "linux", "type": "general", "name": "Ubuntu LTS", "icon": "circle", "description": "Long-term support Ubuntu release", "tags": ["linux", "server", "desktop", "lts"], "source": "official-download"},
    {"id": "fedora", "family": "linux", "type": "general", "name": "Fedora", "icon": "circle", "description": "Current Fedora workstation and server", "tags": ["linux", "redhat", "desktop"], "source": "official-download"},
    {"id": "opensuse", "family": "linux", "type": "general", "name": "openSUSE", "icon": "terminal", "description": "openSUSE Leap or Tumbleweed", "tags": ["linux", "server", "desktop"], "source": "official-download"},
    {"id": "alpine", "family": "linux", "type": "minimal", "name": "Alpine Linux", "icon": "mountain", "description": "Small security-oriented Linux image", "tags": ["linux", "minimal", "server"], "source": "official-download"},
    {"id": "nixos", "family": "linux", "type": "general", "name": "NixOS", "icon": "snowflake", "description": "Declarative Linux distribution", "tags": ["linux", "nix", "server", "desktop"], "source": "official-download"},
    {"id": "rhel", "family": "linux", "type": "enterprise", "name": "Red Hat Enterprise Linux", "icon": "server", "description": "Enterprise Linux from Red Hat", "tags": ["linux", "redhat", "enterprise", "server"], "source": "authenticated-or-user-iso"},
    {"id": "freebsd", "family": "bsd", "type": "general", "name": "FreeBSD", "icon": "terminal", "description": "FreeBSD operating system", "tags": ["bsd", "server", "unix"], "source": "official-download"},
]


class WorkspaceError(RuntimeError):
    pass


class WorkspaceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    locale TEXT NOT NULL DEFAULT 'pl',
                    theme TEXT NOT NULL DEFAULT 'dark',
                    cable_mode TEXT NOT NULL DEFAULT 'realistic',
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    profile_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    z INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'off',
                    os_template TEXT,
                    hardware_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS ports (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                    port_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    connector TEXT NOT NULL,
                    medium TEXT NOT NULL,
                    side TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    max_links INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(device_id, port_key)
                );
                CREATE TABLE IF NOT EXISTS cables (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    port_a TEXT NOT NULL REFERENCES ports(id) ON DELETE CASCADE,
                    port_b TEXT NOT NULL REFERENCES ports(id) ON DELETE CASCADE,
                    medium TEXT NOT NULL,
                    color TEXT NOT NULL,
                    UNIQUE(port_a),
                    UNIQUE(port_b)
                );
                CREATE TABLE IF NOT EXISTS os_projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    os_type TEXT NOT NULL,
                    icon TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_value TEXT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS print_documents (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    printer_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    pages INTEGER NOT NULL,
                    location TEXT NOT NULL DEFAULT 'hud',
                    x REAL NOT NULL DEFAULT 0,
                    y REAL NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                );
                """
            )
            row = connection.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
            elif row["version"] > SCHEMA_VERSION:
                raise WorkspaceError(f"Unsupported workspace schema version: {row['version']}")
            elif row["version"] < SCHEMA_VERSION:
                connection.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION,))
            connection.execute(
                """
                DELETE FROM ports
                WHERE port_key = 'power'
                  AND device_id IN (SELECT id FROM devices WHERE profile_id = 'virtual-printer')
                """
            )
            if connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 0:
                self._seed_default(connection)

    def _seed_default(self, connection: sqlite3.Connection) -> None:
        now = int(time.time())
        connection.execute(
            "INSERT INTO workspaces(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("default", "Laboratorium INF.02", now, now),
        )
        self._insert_device(connection, "default", "router", "mikrotik-rb960pgs", "R1", 80, 20)
        self._insert_device(connection, "default", "client1", "x86-workstation", "CLIENT01", -250, 360, "windows-11")
        self._insert_device(connection, "default", "client2", "x86-workstation", "CLIENT02", 410, 360, "windows-11")
        self._insert_device(connection, "default", "internet", "internet", "Internet", 80, -260)
        self._insert_cable(connection, "default", "wan", "default:internet:uplink", "default:router:ether1", "green")
        self._insert_cable(connection, "default", "client1", "default:router:ether2", "default:client1:nic1", "yellow")
        self._insert_cable(connection, "default", "client2", "default:router:ether3", "default:client2:nic1", "blue")

    def _insert_device(
        self,
        connection: sqlite3.Connection,
        workspace_id: str,
        device_id: str,
        profile_id: str,
        name: str,
        x: float,
        y: float,
        os_template: str | None = None,
    ) -> None:
        profile = DEVICE_PROFILES.get(profile_id)
        if not profile:
            raise WorkspaceError(f"Unknown device profile: {profile_id}")
        hardware = profile.get("defaultHardware", {})
        connection.execute(
            "INSERT INTO devices(id, workspace_id, profile_id, name, x, y, os_template, hardware_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (device_id, workspace_id, profile_id, name, x, y, os_template, json.dumps(hardware)),
        )
        for ordinal, port in enumerate(profile["ports"]):
            connection.execute(
                "INSERT INTO ports(id, device_id, port_key, name, connector, medium, side, ordinal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"{workspace_id}:{device_id}:{port['key']}",
                    device_id,
                    port["key"],
                    port["name"],
                    port["connector"],
                    port["medium"],
                    port["side"],
                    ordinal,
                ),
            )

    def _insert_cable(
        self,
        connection: sqlite3.Connection,
        workspace_id: str,
        cable_id: str,
        port_a: str,
        port_b: str,
        color: str,
    ) -> None:
        color = self._validate_color(color)
        if port_a == port_b:
            raise WorkspaceError("A cable must connect two different ports")
        ports = connection.execute(
            """
            SELECT ports.id, ports.medium, devices.workspace_id
            FROM ports JOIN devices ON devices.id = ports.device_id
            WHERE ports.id IN (?, ?)
            """,
            (port_a, port_b),
        ).fetchall()
        if len(ports) != 2 or any(port["workspace_id"] != workspace_id for port in ports):
            raise WorkspaceError("Cable ports must belong to the selected workspace")
        if ports[0]["medium"] != ports[1]["medium"]:
            raise WorkspaceError("Cable ports must exist and use the same medium")
        connection.execute(
            "INSERT INTO cables(id, workspace_id, port_a, port_b, medium, color) VALUES (?, ?, ?, ?, ?, ?)",
            (cable_id, workspace_id, port_a, port_b, ports[0]["medium"], color),
        )

    @staticmethod
    def _validate_color(color: str) -> str:
        normalized = color.strip().lower()
        if normalized in BUILTIN_CABLE_COLORS or re.fullmatch(r"#[0-9a-f]{6}", normalized):
            return normalized
        raise WorkspaceError(f"Unsupported cable color: {color}")

    @staticmethod
    def _touch(connection: sqlite3.Connection, workspace_id: str) -> None:
        connection.execute(
            "UPDATE workspaces SET revision = revision + 1, updated_at = ? WHERE id = ?",
            (int(time.time()), workspace_id),
        )

    def catalog(self) -> dict:
        with self._connection() as connection:
            custom_templates = []
            for row in connection.execute("SELECT * FROM os_projects ORDER BY created_at, id"):
                project = dict(row)
                custom_templates.append(
                    {
                        "id": project["id"],
                        "family": "custom",
                        "type": project.pop("os_type"),
                        "name": project["name"],
                        "icon": project["icon"],
                        "description": project["description"],
                        "tags": json.loads(project.pop("tags_json")),
                        "source": project.pop("source_kind"),
                        "sourceValue": project.pop("source_value"),
                        "status": project["status"],
                    }
                )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "profiles": list(DEVICE_PROFILES.values()),
            "templates": [*TEMPLATE_CATALOG, *custom_templates],
            "cableModes": sorted(CABLE_MODES),
        }

    def list_workspaces(self) -> list[dict]:
        with self._connection() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM workspaces ORDER BY created_at, id")]

    def snapshot(self, workspace_id: str) -> dict:
        with self._connection() as connection:
            workspace = connection.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
            if workspace is None:
                raise WorkspaceError(f"Unknown workspace: {workspace_id}")
            devices = []
            for row in connection.execute(
                "SELECT * FROM devices WHERE workspace_id = ? ORDER BY z, id", (workspace_id,)
            ):
                device = dict(row)
                device["hardware"] = json.loads(device.pop("hardware_json"))
                device["profile"] = DEVICE_PROFILES[device["profile_id"]]
                device["ports"] = [
                    dict(port)
                    for port in connection.execute(
                        "SELECT * FROM ports WHERE device_id = ? ORDER BY ordinal", (device["id"],)
                    )
                ]
                devices.append(device)
            cables = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM cables WHERE workspace_id = ? ORDER BY id", (workspace_id,)
                )
            ]
            documents = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM print_documents WHERE workspace_id = ? ORDER BY created_at, id",
                    (workspace_id,),
                )
            ]
            return {
                "schemaVersion": SCHEMA_VERSION,
                "workspace": dict(workspace),
                "devices": devices,
                "cables": cables,
                "documents": documents,
            }

    def update_canvas(self, workspace_id: str, positions: list[dict], cable_mode: str | None = None) -> dict:
        if cable_mode is not None and cable_mode not in CABLE_MODES:
            raise WorkspaceError(f"Unsupported cable mode: {cable_mode}")
        with self._connection() as connection:
            if connection.execute("SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)).fetchone() is None:
                raise WorkspaceError(f"Unknown workspace: {workspace_id}")
            for position in positions:
                device_id = str(position.get("id", ""))
                cursor = connection.execute(
                    "UPDATE devices SET x = ?, y = ? WHERE id = ? AND workspace_id = ?",
                    (float(position["x"]), float(position["y"]), device_id, workspace_id),
                )
                if cursor.rowcount != 1:
                    raise WorkspaceError(f"Unknown device: {device_id}")
            now = int(time.time())
            if cable_mode is None:
                connection.execute(
                    "UPDATE workspaces SET revision = revision + 1, updated_at = ? WHERE id = ?",
                    (now, workspace_id),
                )
            else:
                connection.execute(
                    "UPDATE workspaces SET cable_mode = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                    (cable_mode, now, workspace_id),
                )
        return self.snapshot(workspace_id)

    def add_device(self, workspace_id: str, profile_id: str, x: float, y: float, name: str | None = None) -> dict:
        profile = DEVICE_PROFILES.get(profile_id)
        if not profile:
            raise WorkspaceError(f"Unknown device profile: {profile_id}")
        device_id = f"device-{uuid.uuid4().hex[:12]}"
        display_name = name or profile["name"]["pl"]
        with self._connection() as connection:
            if connection.execute("SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)).fetchone() is None:
                raise WorkspaceError(f"Unknown workspace: {workspace_id}")
            self._insert_device(connection, workspace_id, device_id, profile_id, display_name, x, y)
            self._touch(connection, workspace_id)
        return self.snapshot(workspace_id)

    def update_device_os(self, workspace_id: str, device_id: str, os_template: str | None) -> dict:
        template_ids = {template["id"] for template in self.catalog()["templates"]}
        if os_template is not None and os_template not in template_ids:
            raise WorkspaceError(f"Unknown OS template: {os_template}")
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE devices SET os_template = ? WHERE id = ? AND workspace_id = ?",
                (os_template, device_id, workspace_id),
            )
            if cursor.rowcount != 1:
                raise WorkspaceError(f"Unknown device: {device_id}")
            self._touch(connection, workspace_id)
        return self.snapshot(workspace_id)

    def update_device_hardware(self, workspace_id: str, device_id: str, changes: dict) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT profile_id, hardware_json FROM devices WHERE id = ? AND workspace_id = ?",
                (device_id, workspace_id),
            ).fetchone()
            if row is None:
                raise WorkspaceError(f"Unknown device: {device_id}")
            profile = DEVICE_PROFILES[row["profile_id"]]
            hardware = json.loads(row["hardware_json"])
            if profile["kind"] in {"workstation", "server"}:
                allowed = {"host-model", "host-passthrough", "qemu64"}
                cpu_type = str(changes.get("cpuType", hardware.get("cpuType", "host-model")))
                if cpu_type not in allowed:
                    raise WorkspaceError(f"Unsupported CPU type: {cpu_type}")
                hardware.update(
                    {
                        "cpuType": cpu_type,
                        "cpuCores": self._bounded_int(changes.get("cpuCores", hardware.get("cpuCores", 4)), 1, 64, "CPU cores"),
                        "memoryMib": self._bounded_int(changes.get("memoryMib", hardware.get("memoryMib", 4096)), 512, 262144, "memory"),
                        "diskGib": self._bounded_int(changes.get("diskGib", hardware.get("diskGib", 80)), 4, 4096, "disk size"),
                        "networkCards": self._bounded_int(changes.get("networkCards", hardware.get("networkCards", 2)), 1, 16, "network cards"),
                    }
                )
                self._reconcile_network_ports(connection, workspace_id, device_id, hardware["networkCards"])
            elif profile["kind"] == "rack":
                hardware.update(
                    {
                        "rackUnits": self._bounded_int(changes.get("rackUnits", hardware.get("rackUnits", 24)), 1, 48, "rack units"),
                        "rackWidth": self._bounded_int(changes.get("rackWidth", hardware.get("rackWidth", 520)), 320, 1200, "rack width"),
                    }
                )
            else:
                raise WorkspaceError("This device does not expose configurable hardware")
            connection.execute(
                "UPDATE devices SET hardware_json = ? WHERE id = ?", (json.dumps(hardware), device_id)
            )
            self._touch(connection, workspace_id)
        return self.snapshot(workspace_id)

    def mount_device(
        self, workspace_id: str, device_id: str, rack_id: str | None, rack_unit: int | None = None
    ) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT hardware_json FROM devices WHERE id = ? AND workspace_id = ?",
                (device_id, workspace_id),
            ).fetchone()
            if row is None:
                raise WorkspaceError(f"Unknown device: {device_id}")
            if rack_id is not None:
                rack = connection.execute(
                    "SELECT profile_id FROM devices WHERE id = ? AND workspace_id = ?",
                    (rack_id, workspace_id),
                ).fetchone()
                if rack is None or DEVICE_PROFILES[rack["profile_id"]]["kind"] != "rack":
                    raise WorkspaceError(f"Unknown rack: {rack_id}")
            hardware = json.loads(row["hardware_json"])
            if rack_id is None:
                hardware.pop("rackId", None)
                hardware.pop("rackUnit", None)
            else:
                hardware["rackId"] = rack_id
                hardware["rackUnit"] = self._bounded_int(rack_unit or 1, 1, 48, "rack unit")
            connection.execute(
                "UPDATE devices SET hardware_json = ? WHERE id = ?", (json.dumps(hardware), device_id)
            )
            self._touch(connection, workspace_id)
        return self.snapshot(workspace_id)

    @staticmethod
    def _bounded_int(value: object, minimum: int, maximum: int, label: str) -> int:
        result = int(value)
        if result < minimum or result > maximum:
            raise WorkspaceError(f"{label} must be between {minimum} and {maximum}")
        return result

    def _reconcile_network_ports(
        self, connection: sqlite3.Connection, workspace_id: str, device_id: str, wanted: int
    ) -> None:
        rows = connection.execute(
            "SELECT id, port_key, ordinal FROM ports WHERE device_id = ? AND port_key LIKE 'nic%' ORDER BY ordinal",
            (device_id,),
        ).fetchall()
        existing = len(rows)
        if wanted > existing:
            next_ordinal = connection.execute(
                "SELECT COALESCE(MAX(ordinal), -1) + 1 FROM ports WHERE device_id = ?", (device_id,)
            ).fetchone()[0]
            for number in range(existing + 1, wanted + 1):
                connection.execute(
                    "INSERT INTO ports(id, device_id, port_key, name, connector, medium, side, ordinal) VALUES (?, ?, ?, ?, 'rj45', 'ethernet', 'bottom', ?)",
                    (f"{workspace_id}:{device_id}:nic{number}", device_id, f"nic{number}", f"NIC {number}", next_ordinal),
                )
                next_ordinal += 1
        elif wanted < existing:
            for row in rows[wanted:]:
                linked = connection.execute(
                    "SELECT 1 FROM cables WHERE port_a = ? OR port_b = ?", (row["id"], row["id"])
                ).fetchone()
                if linked:
                    raise WorkspaceError(f"Disconnect {row['port_key']} before removing it")
                connection.execute("DELETE FROM ports WHERE id = ?", (row["id"],))

    def create_os_project(
        self,
        name: str,
        description: str,
        os_type: str,
        icon: str,
        tags: list[str],
        source_kind: str,
        source_value: str | None,
    ) -> dict:
        if source_kind not in {"predefined", "upload", "local-iso"}:
            raise WorkspaceError(f"Unsupported OS source: {source_kind}")
        if not name.strip():
            raise WorkspaceError("OS image name is required")
        project_id = f"os-{uuid.uuid4().hex[:12]}"
        now = int(time.time())
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO os_projects(id, name, description, os_type, icon, tags_json, source_kind, source_value, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
                """,
                (project_id, name.strip(), description.strip(), os_type.strip(), icon, json.dumps(tags), source_kind, source_value, now, now),
            )
        return {"catalog": self.catalog(), "project": self.get_os_project(project_id)}

    def get_os_project(self, project_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM os_projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                raise WorkspaceError(f"Unknown OS project: {project_id}")
            project = dict(row)
            project["tags"] = json.loads(project.pop("tags_json"))
            return project

    def update_os_project(self, project_id: str, *, status: str, source_value: str | None = None) -> dict:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE os_projects
                SET status = ?, source_value = COALESCE(?, source_value), updated_at = ?
                WHERE id = ?
                """,
                (status, source_value, int(time.time()), project_id),
            )
            if cursor.rowcount != 1:
                raise WorkspaceError(f"Unknown OS project: {project_id}")
        return self.get_os_project(project_id)

    def move_print_document(
        self, workspace_id: str, document_id: str, location: str, x: float = 0, y: float = 0
    ) -> dict:
        if location not in {"canvas", "hud"}:
            raise WorkspaceError(f"Unsupported document location: {location}")
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE print_documents SET location = ?, x = ?, y = ? WHERE id = ? AND workspace_id = ?",
                (location, x, y, document_id, workspace_id),
            )
            if cursor.rowcount != 1:
                raise WorkspaceError(f"Unknown printed document: {document_id}")
            self._touch(connection, workspace_id)
        return self.snapshot(workspace_id)

    def add_cable(self, workspace_id: str, port_a: str, port_b: str, color: str) -> dict:
        cable_id = f"cable-{uuid.uuid4().hex[:12]}"
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM cables WHERE workspace_id = ? AND (port_a IN (?, ?) OR port_b IN (?, ?))",
                (workspace_id, port_a, port_b, port_a, port_b),
            )
            self._insert_cable(connection, workspace_id, cable_id, port_a, port_b, color)
            self._touch(connection, workspace_id)
        return self.snapshot(workspace_id)

    def update_cable_color(self, workspace_id: str, cable_id: str, color: str) -> dict:
        normalized = self._validate_color(color)
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE cables SET color = ? WHERE id = ? AND workspace_id = ?",
                (normalized, cable_id, workspace_id),
            )
            if cursor.rowcount != 1:
                raise WorkspaceError(f"Unknown cable: {cable_id}")
            self._touch(connection, workspace_id)
        return self.snapshot(workspace_id)

    def remove_cable(self, workspace_id: str, cable_id: str) -> dict:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM cables WHERE id = ? AND workspace_id = ?", (cable_id, workspace_id)
            )
            if cursor.rowcount != 1:
                raise WorkspaceError(f"Unknown cable: {cable_id}")
            self._touch(connection, workspace_id)
        return self.snapshot(workspace_id)

    def remove_device(self, workspace_id: str, device_id: str) -> dict:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM devices WHERE id = ? AND workspace_id = ?", (device_id, workspace_id)
            )
            if cursor.rowcount != 1:
                raise WorkspaceError(f"Unknown device: {device_id}")
            self._touch(connection, workspace_id)
        return self.snapshot(workspace_id)
