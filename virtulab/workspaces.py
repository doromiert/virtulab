from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


SCHEMA_VERSION = 1
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
            {"key": "power", "name": "Power", "connector": "iec-c14", "medium": "power", "side": "left"},
        ],
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
    {"id": "windows-11", "family": "windows", "name": "Windows 11", "source": "microsoft-connector"},
    {"id": "windows-server", "family": "windows", "name": "Windows Server Evaluation", "source": "official-download"},
    {"id": "debian", "family": "linux", "name": "Debian", "source": "official-download"},
    {"id": "ubuntu-lts", "family": "linux", "name": "Ubuntu LTS", "source": "official-download"},
    {"id": "fedora", "family": "linux", "name": "Fedora", "source": "official-download"},
    {"id": "opensuse", "family": "linux", "name": "openSUSE", "source": "official-download"},
    {"id": "alpine", "family": "linux", "name": "Alpine Linux", "source": "official-download"},
    {"id": "nixos", "family": "linux", "name": "NixOS", "source": "official-download"},
    {"id": "rhel", "family": "linux", "name": "Red Hat Enterprise Linux", "source": "authenticated-or-user-iso"},
    {"id": "freebsd", "family": "bsd", "name": "FreeBSD", "source": "official-download"},
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
                """
            )
            row = connection.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
            elif row["version"] != SCHEMA_VERSION:
                raise WorkspaceError(f"Unsupported workspace schema version: {row['version']}")
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
        connection.execute(
            "INSERT INTO devices(id, workspace_id, profile_id, name, x, y, os_template) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (device_id, workspace_id, profile_id, name, x, y, os_template),
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
        return {
            "schemaVersion": SCHEMA_VERSION,
            "profiles": list(DEVICE_PROFILES.values()),
            "templates": TEMPLATE_CATALOG,
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
            return {
                "schemaVersion": SCHEMA_VERSION,
                "workspace": dict(workspace),
                "devices": devices,
                "cables": cables,
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
        if os_template is not None and os_template not in {template["id"] for template in TEMPLATE_CATALOG}:
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
