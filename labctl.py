#!/usr/bin/env python3
"""Local controller for the MikroTik cable training lab."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, unquote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from virtulab import WorkspaceError, WorkspaceStore


LAB_PREFIX = "mikrolab-"
TOPOLOGY_SCHEMA = 3
TOOLS_VERSION = 8
HOST_FIREWALL_UNITS = ("firewall", "firewalld")
VM_NAMES = ("router", "client1", "client2")
PORTS = {
    "router": ("ether1", "ether2", "ether3", "ether4", "ether5", "sfp"),
    "client1": ("ethernet", "ethernet2"),
    "client2": ("ethernet", "ethernet2"),
    "wan": ("uplink",),
}
MACS = {
    "router:ether1": "52:54:00:96:00:01",
    "router:ether2": "52:54:00:96:00:02",
    "router:ether3": "52:54:00:96:00:03",
    "router:ether4": "52:54:00:96:00:04",
    "router:ether5": "52:54:00:96:00:05",
    "router:sfp": "52:54:00:96:00:06",
    "client1:ethernet": "52:54:00:96:01:01",
    "client1:ethernet2": "52:54:00:96:01:02",
    "client2:ethernet": "52:54:00:96:02:01",
    "client2:ethernet2": "52:54:00:96:02:02",
    "template:ethernet": "52:54:00:96:ff:01",
}
UUIDS = {
    "router": "c381777f-7085-55af-87ef-29ea3f486d4e",
    "client1": "593aa73f-c671-5c47-8528-5e39fe995cab",
    "client2": "90e4cdaa-2417-5d21-a064-50671551bb3a",
    "template": "7cb2fae4-2ccb-5e46-8f3a-c75d1ced78bc",
}
DEFAULT_CONNECTIONS = [
    {
        "id": "default-client1",
        "a": "router:ether2",
        "b": "client1:ethernet",
        "color": "yellow",
    },
    {
        "id": "default-client2",
        "a": "router:ether3",
        "b": "client2:ethernet",
        "color": "blue",
    },
]
ALLOWED_COLORS = {"yellow", "blue", "red", "green", "black"}
MASSGRAVE_POLISH_ISO = {
    "filename": "pl-pl_windows_11_consumer_editions_version_25h2_updated_aug_2026_x64_dvd_ec320f81.iso",
    "size": 8735313920,
    "sha256": "2f9dd574edb242f5b3fe9ba4ccdf4fb604a963eb88e2ea738e0cd0fe5bb4e52a",
    "massgrave_url": "https://zerofs.link/f/6KDMJfF/",
}


class LabError(RuntimeError):
    pass


class Lab:
    def __init__(self, root: Path | None = None, uri: str | None = None) -> None:
        self.root = root or Path(
            os.environ.get(
                "MIKROTIK_LAB_HOME",
                Path.home() / ".local" / "share" / "mikrotik-cable-lab",
            )
        )
        self.uri = uri or os.environ.get("MIKROTIK_LIBVIRT_URI", "qemu:///system")
        self.source = Path(os.environ.get("MIKROTIK_LAB_SOURCE", Path(__file__).parent))
        self.project = Path.cwd().resolve()
        self.media = self.root / "media"
        self.config_path = self.root / "topology.json"
        self.applied_path = self.root / "applied-topology.json"
        self.storage_config_path = self.root / "storage.json"
        self.template_marker = self.root / "client-template-sealed"
        self.product_store = WorkspaceStore(self.root / "virtulab.sqlite3")
        self._set_storage(self._configured_storage())
        self._lock = threading.RLock()
        self._setup_status_lock = threading.Lock()
        self._setup_status = {
            "phase": "idle",
            "message": "Gotowy do konfiguracji",
            "downloaded": 0,
            "total": 0,
            "filename": None,
            "sha256": None,
            "error": None,
        }
        self._setup_thread: threading.Thread | None = None
        self._recovery_status_lock = threading.Lock()
        self._recovery_status = {
            "phase": "idle",
            "progress": 0.0,
            "source": None,
            "message": "",
            "error": None,
        }
        self._recovery_thread: threading.Thread | None = None

    def _configured_storage(self) -> Path:
        override = os.environ.get("MIKROTIK_VM_STORAGE")
        if override:
            return Path(override).expanduser().resolve()
        if self.storage_config_path.exists():
            try:
                value = json.loads(self.storage_config_path.read_text()).get("path")
                if value:
                    return Path(value).expanduser().resolve()
            except (OSError, json.JSONDecodeError):
                pass
        return self.root

    def _set_storage(self, path: Path) -> None:
        self.storage = path
        self.golden = path / "golden"
        self.runtime = path / "runtime"

    def choose_storage(self) -> None:
        configured = bool(os.environ.get("MIKROTIK_VM_STORAGE")) or self.storage_config_path.exists()
        if not configured and shutil.disk_usage(self.storage).free < 60 * 1024**3:
            if not sys.stdin.isatty():
                raise LabError(
                    "Less than 60 GiB is free for VM disks. Set MIKROTIK_VM_STORAGE to a larger filesystem"
                )
            free = shutil.disk_usage(self.storage).free / 1024**3
            print(f"Only {free:.1f} GiB is free on {self.storage}.")
            selected = input("VM storage directory with at least 60 GiB free: ").strip()
            if not selected:
                raise LabError("A VM storage directory is required")
            self._set_storage(Path(selected).expanduser().resolve())
        self.storage.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.storage).free < 60 * 1024**3:
            raise LabError(f"VM storage {self.storage} has less than 60 GiB free")
        self.storage_config_path.write_text(json.dumps({"path": str(self.storage)}, indent=2) + "\n")

    def run(self, *args: str, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args,
            check=False,
            input=input_text,
            text=True,
            capture_output=True,
        )
        if check and result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise LabError(f"{' '.join(args)}: {detail}")
        return result

    def virsh(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run("virsh", "-c", self.uri, *args, check=check)

    def ensure_dirs(self) -> None:
        for path in (self.root, self.storage, self.golden, self.runtime, self.media):
            path.mkdir(parents=True, exist_ok=True)

    def load_topology(self) -> dict:
        if not self.config_path.exists():
            return {"connections": DEFAULT_CONNECTIONS}
        try:
            data = json.loads(self.config_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise LabError(f"Cannot read {self.config_path}: {exc}") from exc
        return {"connections": validate_connections(data.get("connections", []))}

    def save_topology(self, connections: list[dict]) -> None:
        connections = validate_connections(connections)
        self.ensure_dirs()
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"connections": connections}, indent=2) + "\n")
        temporary.replace(self.config_path)

    def mark_applied(self, connections: list[dict]) -> None:
        temporary = self.applied_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"schema": TOPOLOGY_SCHEMA, "connections": connections}, indent=2) + "\n"
        )
        temporary.replace(self.applied_path)

    def topology_applied(self) -> bool:
        if not self.applied_path.exists():
            return False
        try:
            applied = json.loads(self.applied_path.read_text())
            return (
                applied.get("schema") == TOPOLOGY_SCHEMA
                and validate_connections(applied.get("connections", []))
                == self.load_topology()["connections"]
            )
        except (OSError, json.JSONDecodeError, LabError):
            return False

    def domain_name(self, vm: str) -> str:
        if vm not in (*VM_NAMES, "template"):
            raise LabError(f"Unknown VM: {vm}")
        return f"{LAB_PREFIX}{vm}"

    def vm_state(self, vm: str) -> str:
        result = self.virsh("domstate", self.domain_name(vm), check=False)
        if result.returncode:
            return "undefined"
        return result.stdout.strip().lower()

    def all_stopped(self) -> bool:
        return all(self.vm_state(vm) in {"shut off", "undefined"} for vm in VM_NAMES)

    def status(self) -> dict:
        prepared = (self.golden / "router.qcow2").exists()
        clients = {}
        for vm in ("client1", "client2"):
            clients[vm] = {
                "golden": (self.golden / "client-template.qcow2").exists()
                and self.template_marker.exists(),
                "runtime": (self.runtime / f"{vm}.qcow2").exists(),
            }
        return {
            "prepared": prepared,
            "isoFound": self.find_windows_iso() is not None,
            "libvirtUri": self.uri,
            "storage": str(self.storage),
            "vms": {vm: self.vm_state(vm) for vm in VM_NAMES},
            "clients": clients,
            "topology": self.load_topology(),
            "topologyApplied": self.topology_applied(),
            "recovery": self.recovery_status(),
            "downloads": {
                "chr": "https://download.mikrotik.com/routeros/7.24.1/chr-7.24.1.img.zip",
                "winbox": "https://download.mikrotik.com/routeros/winbox/4.3/WinBox_Windows.zip",
            },
        }

    def find_windows_iso(self) -> Path | None:
        override = os.environ.get("MIKROTIK_WIN11_ISO")
        candidates = [Path(override)] if override else []
        candidates.append(self.root / "win11.iso")
        return next((path.resolve() for path in candidates if path and path.is_file()), None)

    def prepare(self) -> None:
        with self._lock:
            self.prepare_base()
            if not self.template_marker.exists():
                self.launch_client_template()
                self.wait_for_client_template()
                self.seal_client_template()
            self.finalize_lab()

    def prepare_base(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.choose_storage()
        self.ensure_dirs()
        self.virsh("list", "--all")
        self.check_host_capabilities()
        if not self.all_stopped():
            raise LabError("Shut down the router and all client VMs before running setup")
        chr_archive = require_env_file("MIKROTIK_CHR_ARCHIVE")
        winbox_archive = require_env_file("MIKROTIK_WINBOX_ARCHIVE")
        windows_iso = self.find_windows_iso()
        if not windows_iso:
            raise LabError("Set MIKROTIK_WIN11_ISO or download Windows 11 in setup mode")
        saved_iso = self.root / "win11.iso"
        if saved_iso.is_symlink() and not saved_iso.exists():
            saved_iso.unlink()
        if not saved_iso.exists() and windows_iso != saved_iso:
            saved_iso.symlink_to(windows_iso)

        router_base = self.golden / "router.qcow2"
        if not router_base.exists():
            with zipfile.ZipFile(chr_archive) as archive, tempfile.TemporaryDirectory() as temp:
                image_names = [name for name in archive.namelist() if name.endswith(".img")]
                if len(image_names) != 1:
                    raise LabError("The CHR archive does not contain exactly one .img image")
                archive.extract(image_names[0], temp)
                temporary_base = router_base.with_suffix(".tmp")
                self.run(
                    "qemu-img",
                    "convert",
                    "-f",
                    "raw",
                    "-O",
                    "qcow2",
                    str(Path(temp) / image_names[0]),
                    str(temporary_base),
                )
                self.run("qemu-img", "check", "-f", "qcow2", str(temporary_base))
                temporary_base.replace(router_base)
        self.make_overlay("router", replace=False)
        self.make_tools_iso(winbox_archive)

    def launch_client_template(self) -> None:
        template_disk = self.golden / "client-template.qcow2"
        if self.template_marker.exists() and template_disk.exists():
            return
        if not template_disk.exists():
            self.run("qemu-img", "create", "-f", "qcow2", str(template_disk), "80G")

        installer_network = f"{LAB_PREFIX}installer"
        needs_start = self.vm_state("template") != "running"
        if needs_start:
            self.virsh("net-destroy", installer_network, check=False)
            self.virsh("net-undefine", installer_network, check=False)
            self.define_xml("net-define", network_xml(installer_network, "mlabinst"))
            self.virsh("net-start", installer_network)
            self.define_xml("define", self.domain_xml("template", {}))
        subprocess.Popen(
            ["virt-viewer", "--connect", self.uri, "--wait", self.domain_name("template")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if needs_start:
            print("The console is opening. Press any key when Windows asks to boot from CD/DVD.")
            time.sleep(1)
            self.virsh("start", self.domain_name("template"))

    def wait_for_client_template(self) -> None:
        print(
            "\nInstall Windows, WinBox and any other software in the template VM.\n"
            "When finished, shut Windows down normally. If you need distinct Windows identities, "
            "you may instead run Sysprep /generalize /oobe /shutdown.\n"
            "Wait until the VM is fully powered off, then return here."
        )
        while self.vm_state("template") != "shut off":
            try:
                input("Press Enter after the template VM has shut down: ")
            except EOFError as exc:
                raise LabError("Template setup requires an interactive terminal") from exc
            if self.vm_state("template") != "shut off":
                print("The template VM is still running; shut it down before continuing.")

    def seal_client_template(self) -> None:
        template_disk = self.golden / "client-template.qcow2"
        if self.vm_state("template") != "shut off":
            raise LabError("Shut down the Windows template before sealing it")
        if not template_disk.exists():
            raise LabError("The Windows template disk is missing")
        installer_network = f"{LAB_PREFIX}installer"
        self.virsh("undefine", self.domain_name("template"), "--nvram", "--tpm")
        self.virsh("net-destroy", installer_network, check=False)
        self.virsh("net-undefine", installer_network, check=False)
        self.template_marker.write_text("sealed\n")

    def finalize_lab(self) -> None:
        for vm in ("client1", "client2"):
            self.make_overlay(vm, replace=False)
        if not self.config_path.exists():
            self.save_topology(DEFAULT_CONNECTIONS)
        self.apply_topology()

    def _update_setup_status(self, **changes: object) -> None:
        with self._setup_status_lock:
            self._setup_status.update(changes)

    def setup_status(self) -> dict:
        with self._setup_status_lock:
            status = dict(self._setup_status)
        template_state = self.vm_state("template")
        status["templateState"] = template_state
        status["sealed"] = self.template_marker.exists()
        status["isoCandidates"] = [
            str(path.resolve())
            for path in sorted(self.project.glob("*.iso"))
            if path.is_file() and path.stat().st_size >= 3 * 1024**3
        ]
        if status["phase"] == "template-running" and template_state == "shut off":
            status["phase"] = "ready-to-seal"
            status["message"] = "Szablon jest wyłączony i gotowy do zapisania"
        return status

    def start_web_setup(self, language: str, source: str = "microsoft") -> None:
        if language not in {"Polish", "English", "English International"}:
            raise LabError("Unsupported Windows language")
        if source not in {"microsoft", "massgrave", "ntriver"}:
            raise LabError("Unsupported ISO source")
        if source in {"massgrave", "ntriver"} and language != "Polish":
            raise LabError("Fallback Massgrave/NTriver obsługuje obecnie polski obraz x64")
        if self._setup_thread and self._setup_thread.is_alive():
            raise LabError("Setup is already running")
        if source == "massgrave":
            webbrowser.open(MASSGRAVE_POLISH_ISO["massgrave_url"])
            self._update_setup_status(
                phase="waiting-local",
                message=(
                    "Massgrave otwarto w przeglądarce. Pobierz obraz, a następnie wybierz go "
                    "jako istniejący ISO poniżej."
                ),
                downloaded=0,
                total=MASSGRAVE_POLISH_ISO["size"],
                filename=MASSGRAVE_POLISH_ISO["filename"],
                sha256=MASSGRAVE_POLISH_ISO["sha256"],
                error=None,
                source=source,
            )
            return
        self._update_setup_status(
            phase="resolving",
            message="Pobieranie oficjalnego adresu ISO z Microsoft",
            downloaded=0,
            total=0,
            filename=None,
            sha256=None,
            error=None,
            source=source,
        )
        self._setup_thread = threading.Thread(
            target=self._web_setup_worker, args=(language, source), daemon=True
        )
        self._setup_thread.start()

    def _web_setup_worker(self, language: str, source: str) -> None:
        try:
            iso = self.download_windows_iso(language, source)
            self._prepare_web_template(iso)
        except Exception as exc:
            self._update_setup_status(phase="error", message=str(exc), error=str(exc))

    def start_web_setup_local(self, path_value: str) -> None:
        if self._setup_thread and self._setup_thread.is_alive():
            raise LabError("Setup is already running")
        iso = Path(path_value).expanduser()
        if not iso.is_absolute():
            raise LabError("Podaj bezwzględną ścieżkę do obrazu ISO")
        iso = iso.resolve()
        validate_local_windows_iso(iso)
        self._update_setup_status(
            phase="preparing",
            message="Przygotowywanie laboratorium z istniejącego obrazu ISO",
            downloaded=iso.stat().st_size,
            total=iso.stat().st_size,
            filename=iso.name,
            sha256=None,
            error=None,
        )
        self._setup_thread = threading.Thread(
            target=self._web_local_setup_worker, args=(iso,), daemon=True
        )
        self._setup_thread.start()

    def _web_local_setup_worker(self, iso: Path) -> None:
        try:
            self._prepare_web_template(iso)
        except Exception as exc:
            self._update_setup_status(phase="error", message=str(exc), error=str(exc))

    def _prepare_web_template(self, iso: Path) -> None:
        self._update_setup_status(phase="preparing", message="Przygotowywanie maszyn i sieci")
        with self._lock:
            os.environ["MIKROTIK_WIN11_ISO"] = str(iso)
            self.prepare_base()
            if self.template_marker.exists():
                self.finalize_lab()
                self._update_setup_status(phase="complete", message="Laboratorium jest gotowe")
            else:
                self.launch_client_template()
                self._update_setup_status(
                    phase="template-running",
                    message="Skonfiguruj Windows, a następnie wyłącz maszynę szablonową",
                )

    def finalize_web_setup(self) -> None:
        if self._setup_thread and self._setup_thread.is_alive():
            raise LabError("Setup is still running")
        if self.vm_state("template") != "shut off":
            raise LabError("Shut down the Windows template before sealing it")
        self._update_setup_status(phase="sealing", message="Zapisywanie wspólnego punktu przywracania")
        self._setup_thread = threading.Thread(target=self._web_seal_worker, daemon=True)
        self._setup_thread.start()

    def _web_seal_worker(self) -> None:
        try:
            with self._lock:
                self.seal_client_template()
                self.finalize_lab()
            self._update_setup_status(phase="complete", message="Laboratorium jest gotowe")
        except Exception as exc:
            self._update_setup_status(phase="error", message=str(exc), error=str(exc))

    def open_template_console(self) -> None:
        if self.vm_state("template") == "undefined":
            raise LabError("The template VM has not been created yet")
        subprocess.Popen(
            ["virt-viewer", "--connect", self.uri, "--wait", self.domain_name("template")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def download_windows_iso(self, language: str, source: str = "microsoft") -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / "win11.iso"
        if target.is_symlink():
            target.unlink()

        expected_hash = None
        expected_size = None
        if source == "ntriver":
            url, filename = resolve_ntriver_windows_iso(language)
            expected_hash = MASSGRAVE_POLISH_ISO["sha256"]
            expected_size = MASSGRAVE_POLISH_ISO["size"]
            validate_massgrave_mirror_url(url)
        else:
            cache_path = self.root / "microsoft-iso-url.json"
            url = filename = None
            try:
                cached = json.loads(cache_path.read_text())
                if (
                    cached.get("language") == language
                    and time.time() - float(cached.get("created", 0)) < 20 * 60 * 60
                ):
                    url = cached["url"]
                    filename = cached["filename"]
                    validate_microsoft_url(url)
            except (OSError, ValueError, KeyError, json.JSONDecodeError, LabError):
                pass
            if not url or not filename:
                url, filename = resolve_microsoft_windows_iso(language)
                cache_path.write_text(
                    json.dumps(
                        {"language": language, "url": url, "filename": filename, "created": time.time()},
                        indent=2,
                    )
                    + "\n"
                )
                cache_path.chmod(0o600)
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
        )
        with urlopen(request, timeout=60) as response:
            if source == "ntriver":
                validate_massgrave_mirror_url(response.geturl())
            else:
                validate_microsoft_url(response.geturl())
            total = int(response.headers.get("Content-Length", "0")) or expected_size or 0
            if expected_size and total != expected_size:
                raise LabError("Mirror returned a file size that does not match the published catalog")
            if total and shutil.disk_usage(self.root).free < total + 10 * 1024**3:
                raise LabError("Not enough free space to download and install Windows 11")
            temporary = target.with_suffix(".iso.part")
            temporary.unlink(missing_ok=True)
            digest = hashlib.sha256()
            downloaded = 0
            self._update_setup_status(
                phase="downloading",
                message=(
                    "Pobieranie Windows 11 z mirroru Massgrave/NTriver"
                    if source == "ntriver"
                    else "Pobieranie Windows 11 bezpośrednio z Microsoft"
                ),
                downloaded=0,
                total=total,
                filename=filename,
            )
            try:
                with temporary.open("wb") as output:
                    while chunk := response.read(8 * 1024**2):
                        output.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        self._update_setup_status(downloaded=downloaded, total=total)
                    output.flush()
                    os.fsync(output.fileno())
                if total and downloaded != total:
                    raise LabError("ISO download ended before the advertised size")
                with temporary.open("rb") as image:
                    image.seek(0x8001)
                    if image.read(5) != b"CD001":
                        raise LabError("Downloaded file is not a valid ISO 9660 image")
                if expected_hash and digest.hexdigest().lower() != expected_hash.lower():
                    raise LabError("Downloaded ISO SHA-256 does not match the published Massgrave/MVS hash")
                temporary.replace(target)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
        self._update_setup_status(sha256=digest.hexdigest(), downloaded=downloaded, total=downloaded)
        return target

    def check_host_capabilities(self) -> None:
        result = self.virsh(
            "domcapabilities",
            "--arch",
            "x86_64",
            "--machine",
            "q35",
            "--virttype",
            "kvm",
        )
        try:
            capabilities = ElementTree.fromstring(result.stdout)
        except ElementTree.ParseError as exc:
            raise LabError(f"Cannot parse libvirt domain capabilities: {exc}") from exc

        firmware = {
            node.text for node in capabilities.findall("./os/enum[@name='firmware']/value")
        }
        if "efi" not in firmware:
            raise LabError("The q35 KVM host does not expose UEFI firmware required by Windows 11")

        tpm_backends = {
            node.text
            for node in capabilities.findall("./devices/tpm/enum[@name='backendModel']/value")
        }
        if "emulator" not in tpm_backends:
            raise LabError(
                "libvirt does not expose the swtpm TPM 2.0 emulator required by Windows 11. "
                "On NixOS set virtualisation.libvirtd.qemu.swtpm.enable = true and rebuild; "
                "on other distributions install swtpm and restart libvirtd"
            )

    def make_tools_iso(self, winbox_archive: Path) -> None:
        output = self.media / "winbox-tools.iso"
        version_file = self.media / "winbox-tools.version"
        if output.exists() and version_file.exists() and version_file.read_text().strip() == str(TOOLS_VERSION):
            return
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            shutil.copy2(winbox_archive, stage / "WinBox_Windows.zip")
            legacy_winbox = os.environ.get("MIKROTIK_WINBOX3_EXE")
            if legacy_winbox and Path(legacy_winbox).is_file():
                shutil.copy2(legacy_winbox, stage / "WinBox3.exe")
            (stage / "README.txt").write_text(
                "MikroTik WinBox 4.3 - official Windows x64 build.\r\n"
                "Right-click Install-WinBox.cmd and choose Run as administrator.\r\n"
                "The installer also registers automatic CLIENT01/CLIENT02 hostname assignment.\r\n"
            )
            (stage / "Install-WinBox.cmd").write_text(
                "@echo off\r\n"
                "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0install-winbox.ps1\"\r\n"
                "pause\r\n"
            )
            (stage / "Enable-BlankRouterDiscovery.cmd").write_text(
                "@echo off\r\n"
                "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0Enable-BlankRouterDiscovery.ps1\"\r\n"
                "pause\r\n"
            )
            (stage / "Enable-BlankRouterDiscovery.ps1").write_text(
                "$ErrorActionPreference = 'Stop'\r\n"
                "$addresses = @{\r\n"
                "  '52-54-00-96-01-01' = '192.0.2.11'\r\n"
                "  '52-54-00-96-02-01' = '192.0.2.12'\r\n"
                "}\r\n"
                "$nic = Get-NetAdapter | Where-Object { $addresses.ContainsKey($_.MacAddress.ToUpperInvariant()) } | Select-Object -First 1\r\n"
                "if (-not $nic) { throw 'Primary MikroTik lab adapter was not found' }\r\n"
                "$address = $addresses[$nic.MacAddress.ToUpperInvariant()]\r\n"
                "Get-NetAdapter -IncludeHidden | Where-Object { $_.MacAddress -like '52-54-00-96-*' -and $_.ifIndex -ne $nic.ifIndex } | Disable-NetAdapter -Confirm:$false -ErrorAction SilentlyContinue\r\n"
                "Set-NetIPInterface -InterfaceIndex $nic.ifIndex -Dhcp Disabled\r\n"
                "Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue\r\n"
                "New-NetIPAddress -InterfaceIndex $nic.ifIndex -IPAddress $address -PrefixLength 24 | Out-Null\r\n"
                "Get-NetConnectionProfile -InterfaceIndex $nic.ifIndex -ErrorAction SilentlyContinue | Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue\r\n"
                "Enable-NetAdapterBinding -Name $nic.Name -ComponentID ms_server -ErrorAction SilentlyContinue\r\n"
                "Enable-NetAdapterBinding -Name $nic.Name -ComponentID ms_msclient -ErrorAction SilentlyContinue\r\n"
                "Set-Service -Name LanmanServer -StartupType Automatic\r\n"
                "Start-Service -Name LanmanServer -ErrorAction SilentlyContinue\r\n"
                "Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object Name -Like 'FPS-*' | Set-NetFirewallRule -Enabled True -Profile Any\r\n"
                "Set-NetIPInterface -InterfaceIndex $nic.ifIndex -NlMtuBytes 1500 -ErrorAction SilentlyContinue\r\n"
                "Get-Process -Name 'WinBox' -ErrorAction SilentlyContinue | Stop-Process -Force\r\n"
                "Write-Host \"Configured $($nic.Name) as $address/24 with File and Printer Sharing and MTU 1500. Reopen WinBox and wait up to 30 seconds.\"\r\n"
            )
            (stage / "Enable-AllLabAdapters.cmd").write_text(
                "@echo off\r\n"
                "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"Get-NetAdapter -IncludeHidden ^| Where-Object { $_.MacAddress -like '52-54-00-96-*' } ^| Enable-NetAdapter -Confirm:$false -ErrorAction SilentlyContinue\"\r\n"
                "pause\r\n"
            )
            (stage / "install-winbox.ps1").write_text(
                "$ErrorActionPreference = 'Stop'\r\n"
                "$target = Join-Path $env:ProgramFiles 'MikroTik\\WinBox'\r\n"
                "New-Item -ItemType Directory -Force -Path $target | Out-Null\r\n"
                "Expand-Archive -Force -Path (Join-Path $PSScriptRoot 'WinBox_Windows.zip') -DestinationPath $target\r\n"
                "$exe = Get-ChildItem -Path $target -Filter 'WinBox.exe' -Recurse | Select-Object -First 1\r\n"
                "if (-not $exe) { throw 'WinBox.exe was not found after extraction' }\r\n"
                "$shell = New-Object -ComObject WScript.Shell\r\n"
                "$shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'WinBox.lnk'))\r\n"
                "$shortcut.TargetPath = $exe.FullName\r\n"
                "$shortcut.WorkingDirectory = $exe.DirectoryName\r\n"
                "$shortcut.Save()\r\n"
                "$legacySource = Join-Path $PSScriptRoot 'WinBox3.exe'\r\n"
                "if (Test-Path $legacySource) {\r\n"
                "  $legacyTarget = Join-Path $env:ProgramFiles 'MikroTik\\WinBox3\\WinBox3.exe'\r\n"
                "  New-Item -ItemType Directory -Force -Path (Split-Path $legacyTarget) | Out-Null\r\n"
                "  Copy-Item -Force $legacySource $legacyTarget\r\n"
                "  $legacyShortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'WinBox 3.lnk'))\r\n"
                "  $legacyShortcut.TargetPath = $legacyTarget\r\n"
                "  $legacyShortcut.Save()\r\n"
                "  Get-NetFirewallRule -DisplayName 'MikroTik WinBox 3' -ErrorAction SilentlyContinue | Remove-NetFirewallRule\r\n"
                "  New-NetFirewallRule -DisplayName 'MikroTik WinBox 3' -Direction Inbound -Program $legacyTarget -Action Allow -Profile Any | Out-Null\r\n"
                "}\r\n"
                "Get-NetFirewallRule -DisplayName 'MikroTik WinBox Discovery' -ErrorAction SilentlyContinue | Remove-NetFirewallRule\r\n"
                "New-NetFirewallRule -DisplayName 'MikroTik WinBox Discovery' -Direction Inbound -Program $exe.FullName -Action Allow -Profile Any | Out-Null\r\n"
                "Get-NetFirewallRule -DisplayName 'MikroTik MNDP UDP' -ErrorAction SilentlyContinue | Remove-NetFirewallRule\r\n"
                "New-NetFirewallRule -DisplayName 'MikroTik MNDP UDP' -Direction Inbound -Protocol UDP -LocalPort 5678 -Action Allow -Profile Any | Out-Null\r\n"
                "Get-NetFirewallRule -DisplayName 'MikroTik MAC WinBox UDP' -ErrorAction SilentlyContinue | Remove-NetFirewallRule\r\n"
                "New-NetFirewallRule -DisplayName 'MikroTik MAC WinBox UDP' -Direction Inbound -Protocol UDP -LocalPort 20561 -Action Allow -Profile Any | Out-Null\r\n"
                "$labDir = Join-Path $env:ProgramData 'MikroTikLab'\r\n"
                "New-Item -ItemType Directory -Force -Path $labDir | Out-Null\r\n"
                "$renameScript = Join-Path $labDir 'Set-ClientHostname.ps1'\r\n"
                "Copy-Item -Force (Join-Path $PSScriptRoot 'Set-ClientHostname.ps1') $renameScript\r\n"
                "$taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File \"{0}\"' -f $renameScript)\r\n"
                "$taskTrigger = New-ScheduledTaskTrigger -AtStartup\r\n"
                "$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest\r\n"
                "Register-ScheduledTask -TaskName 'MikroTikLab-SetComputerName' -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Force | Out-Null\r\n"
                "Write-Host \"WinBox installed to $target\"\r\n"
                "Write-Host 'Automatic client hostname assignment registered'\r\n"
            )
            (stage / "Set-ClientHostname.ps1").write_text(
                "$ErrorActionPreference = 'Stop'\r\n"
                "$serial = (Get-CimInstance -ClassName Win32_BIOS).SerialNumber.Trim().ToUpperInvariant()\r\n"
                "if ($serial -notmatch '^CLIENT0[12]$') { exit 0 }\r\n"
                "if ($env:COMPUTERNAME -ne $serial) { Rename-Computer -NewName $serial -Force; Restart-Computer -Force }\r\n"
            )
            temporary_output = output.with_suffix(".tmp")
            self.run(
                "xorriso",
                "-as",
                "mkisofs",
                "-quiet",
                "-J",
                "-joliet-long",
                "-r",
                "-V",
                "WINTOOLS",
                "-o",
                str(temporary_output),
                str(stage),
            )
            temporary_output.replace(output)
            version_file.write_text(f"{TOOLS_VERSION}\n")

    def make_overlay(self, vm: str, replace: bool) -> Path:
        base = self.golden / ("router.qcow2" if vm == "router" else "client-template.qcow2")
        overlay = self.runtime / f"{vm}.qcow2"
        if not base.exists():
            raise LabError(f"Golden disk is missing: {base}")
        if overlay.exists() and not replace:
            return overlay
        temporary = overlay.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        self.run(
            "qemu-img",
            "create",
            "-f",
            "qcow2",
            "-F",
            "qcow2",
            "-b",
            str(base.resolve()),
            str(temporary),
        )
        self.run("qemu-img", "check", "-f", "qcow2", str(temporary))
        temporary.replace(overlay)
        return overlay

    def disk_for(self, vm: str) -> Path:
        if vm == "template":
            return self.golden / "client-template.qcow2"
        runtime = self.runtime / f"{vm}.qcow2"
        if runtime.exists():
            return runtime
        return self.golden / ("router.qcow2" if vm == "router" else "client-template.qcow2")

    def apply_topology(self) -> None:
        with self._lock:
            connections = self.load_topology()["connections"]
            assignments = network_assignments(connections)
            network_names = sorted(
                {
                    assignments[f"{vm}:{port}"]
                    for vm in VM_NAMES
                    for port in PORTS[vm]
                }
            )
            self.ensure_networks(network_names)
            for vm in VM_NAMES:
                state = self.vm_state(vm)
                if state == "undefined":
                    self.define_xml("define", self.domain_xml(vm, assignments))
                    continue
                model = "virtio"
                for port in PORTS[vm]:
                    endpoint = f"{vm}:{port}"
                    self.update_interface(
                        vm,
                        interface_xml(
                            MACS[endpoint],
                            assignments[endpoint],
                            model,
                            not assignments[endpoint].startswith(f"{LAB_PREFIX}loose-"),
                        ),
                        live=state not in {"shut off", "undefined"},
                    )
            self.remove_obsolete_cable_networks(set(network_names))
            self.mark_applied(connections)

    def ensure_networks(self, wanted: list[str]) -> None:
        result = self.virsh("net-list", "--all", "--name")
        existing = set(result.stdout.splitlines())
        for name in wanted:
            if name not in existing:
                self.define_xml("net-define", network_xml(name, bridge_name_for_network(name)))
            self.virsh("net-start", name, check=False)
            self.virsh("net-autostart", name)

    def remove_obsolete_cable_networks(self, wanted: set[str]) -> None:
        result = self.virsh("net-list", "--all", "--name")
        for name in result.stdout.splitlines():
            managed_cable = name.startswith(f"{LAB_PREFIX}cable-") or name.startswith(
                f"{LAB_PREFIX}wan-"
            )
            if managed_cable and name not in wanted:
                self.virsh("net-destroy", name, check=False)
                self.virsh("net-undefine", name, check=False)

    def update_interface(self, vm: str, xml: str, live: bool) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as handle:
            handle.write(xml)
            path = handle.name
        try:
            arguments = ["update-device", self.domain_name(vm), path]
            if live:
                arguments.append("--live")
            arguments.append("--config")
            self.virsh(*arguments)
        finally:
            Path(path).unlink(missing_ok=True)

    def define_xml(self, command: str, xml: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as handle:
            handle.write(xml)
            path = handle.name
        try:
            self.virsh(command, path)
        finally:
            Path(path).unlink(missing_ok=True)

    def domain_xml(self, vm: str, assignments: dict[str, str]) -> str:
        disk = self.disk_for(vm).resolve()
        if not disk.exists():
            raise LabError(f"Disk is missing for {vm}; run setup first")
        if vm == "router":
            interfaces = "".join(
                interface_xml(
                    MACS[f"router:{port}"],
                    assignments[f"router:{port}"],
                    "virtio",
                    not assignments[f"router:{port}"].startswith(f"{LAB_PREFIX}loose-"),
                )
                for port in PORTS["router"]
            )
            return f"""
<domain type='kvm'>
  <name>{self.domain_name(vm)}</name>
  <uuid>{UUIDS[vm]}</uuid>
  <title>RouterOS CHR - RB960PGS logical lab</title>
  <memory unit='MiB'>1024</memory><vcpu>1</vcpu>
  <os><type arch='x86_64' machine='pc'>hvm</type><boot dev='hd'/></os>
  <features><acpi/><apic/></features>
  <cpu mode='host-model'/>
  <devices>
    <disk type='file' device='disk'><driver name='qemu' type='qcow2'/><source file='{xml_attr(disk)}'/><target dev='vda' bus='virtio'/></disk>
    {interfaces}
    <serial type='pty'><target port='0'/></serial><console type='pty'><target type='serial' port='0'/></console>
    <channel type='unix'><target type='virtio' name='org.qemu.guest_agent.0'/></channel>
    <graphics type='spice' autoport='yes'><listen type='address'/></graphics>
    <video><model type='virtio'/></video>
  </devices>
</domain>"""

        tools = self.media / "winbox-tools.iso"
        if vm == "template":
            iso = self.find_windows_iso()
            if not iso:
                raise LabError("Set MIKROTIK_WIN11_ISO before preparing the Windows template")
            interface = interface_xml(
                MACS["template:ethernet"], f"{LAB_PREFIX}installer", "e1000e", True
            )
            return windows_domain_xml(
                self.domain_name(vm),
                UUIDS[vm],
                "Windows 11 client template",
                disk,
                cdrom_xml(iso.resolve(), "sda") + cdrom_xml(tools.resolve(), "sdb"),
                interface,
                "LABTEMPLATE",
            )
        interfaces = "".join(
            interface_xml(
                MACS[f"{vm}:{port}"],
                assignments[f"{vm}:{port}"],
                "virtio",
                not assignments[f"{vm}:{port}"].startswith(f"{LAB_PREFIX}loose-"),
            )
            for port in PORTS[vm]
        )
        cdroms = ""
        if not (self.runtime / f"{vm}.qcow2").exists():
            iso = self.find_windows_iso()
            if not iso:
                raise LabError("Set MIKROTIK_WIN11_ISO to your win11.iso before installing clients")
            cdroms += cdrom_xml(iso.resolve(), "sda")
        cdroms += cdrom_xml(tools.resolve(), "sdb")
        return windows_domain_xml(
            self.domain_name(vm),
            UUIDS[vm],
            f"Windows 11 training client {vm[-1]}",
            disk,
            cdroms,
            interfaces,
            f"CLIENT0{vm[-1]}",
        )

    def promote_client_template(self, vm: str) -> None:
        if vm not in {"client1", "client2"}:
            raise LabError("Only a Windows client can become the recovery image")
        if any(self.vm_state(client) not in {"shut off", "undefined"} for client in ("client1", "client2")):
            raise LabError("Shut down both Windows clients before updating the recovery image")
        source = self.runtime / f"{vm}.qcow2"
        if not source.exists():
            raise LabError(f"Runtime disk is missing for {vm}")
        target = self.golden / "client-template.qcow2"
        temporary = self.golden / "client-template.promote.tmp"
        temporary.unlink(missing_ok=True)
        try:
            process = subprocess.Popen(
                [
                    "qemu-img",
                    "convert",
                    "-p",
                    "-f",
                    "qcow2",
                    "-O",
                    "qcow2",
                    str(source),
                    str(temporary),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            progress_buffer = ""
            while process.stderr and (character := process.stderr.read(1)):
                if character in "\r\n":
                    match = re.search(r"\(([0-9.]+)/100%\)", progress_buffer)
                    if match:
                        self._update_recovery_status(progress=float(match.group(1)))
                    progress_buffer = ""
                else:
                    progress_buffer += character
            if process.wait() != 0:
                raise LabError("qemu-img failed while updating the recovery image")
            self.run("qemu-img", "check", "-f", "qcow2", str(temporary))
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        for client in ("client1", "client2"):
            self.make_overlay(client, replace=True)
        self.apply_topology()

    def _update_recovery_status(self, **changes: object) -> None:
        with self._recovery_status_lock:
            self._recovery_status.update(changes)

    def recovery_status(self) -> dict:
        with self._recovery_status_lock:
            return dict(self._recovery_status)

    def start_recovery_promotion(self, vm: str) -> None:
        if self._recovery_thread and self._recovery_thread.is_alive():
            raise LabError("A recovery image update is already running")
        if vm not in {"client1", "client2"}:
            raise LabError("Only a Windows client can become the recovery image")
        if any(self.vm_state(client) not in {"shut off", "undefined"} for client in ("client1", "client2")):
            raise LabError("Shut down both Windows clients before updating the recovery image")
        self._update_recovery_status(
            phase="running",
            progress=0.0,
            source=vm,
            message=f"Tworzenie obrazu odzyskiwania z {vm}",
            error=None,
        )
        self._recovery_thread = threading.Thread(
            target=self._recovery_promotion_worker, args=(vm,), daemon=True
        )
        self._recovery_thread.start()

    def _recovery_promotion_worker(self, vm: str) -> None:
        try:
            with self._lock:
                self.promote_client_template(vm)
            self._update_recovery_status(
                phase="complete",
                progress=100.0,
                message="Obraz odzyskiwania zaktualizowany; oba klienty zostały zresetowane",
            )
        except Exception as exc:
            self._update_recovery_status(phase="error", message=str(exc), error=str(exc))

    def action(self, vm: str, action: str) -> str:
        with self._lock:
            name = self.domain_name(vm)
            state = self.vm_state(vm)
            if action == "start":
                if state == "undefined":
                    self.apply_topology()
                self.virsh("start", name)
                return "Maszyna została uruchomiona"
            if action == "shutdown":
                self.virsh("shutdown", name)
                return "Wysłano żądanie wyłączenia"
            if action == "force-stop":
                self.virsh("destroy", name)
                return "Maszyna została zatrzymana"
            if action == "reset":
                if state not in {"shut off", "undefined"}:
                    raise LabError("Maszyna musi być wyłączona przed przywróceniem dysku")
                if vm != "router" and not (self.runtime / f"{vm}.qcow2").exists():
                    raise LabError("Najpierw zapisz czysty stan tej instalacji Windows")
                self.make_overlay(vm, replace=True)
                self.apply_topology()
                return "Przywrócono dysk ze stanu bazowego"
            if action == "promote":
                self.start_recovery_promotion(vm)
                return "Rozpoczęto aktualizację obrazu odzyskiwania"
            if action == "console":
                if state == "undefined":
                    self.apply_topology()
                    state = self.vm_state(vm)
                if state == "shut off":
                    self.virsh("start", name)
                subprocess.Popen(
                    ["virt-viewer", "--connect", self.uri, "--wait", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return "Otwarto konsolę"
            raise LabError(f"Nieznana akcja: {action}")


def microsoft_get(
    url: str,
    headers: dict[str, str] | None = None,
    opener: object | None = None,
) -> str:
    request_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json,text/html,*/*",
    }
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    open_request = opener.open if opener else urlopen
    with open_request(request, timeout=30) as response:
        return response.read().decode("utf-8")


def validate_local_windows_iso(path: Path) -> None:
    if not path.is_file():
        raise LabError(f"Nie znaleziono pliku ISO: {path}")
    if path.suffix.lower() != ".iso":
        raise LabError("Wybrany plik musi mieć rozszerzenie .iso; poczekaj na zakończenie pobierania")
    if path.stat().st_size < 3 * 1024**3:
        raise LabError("Obraz ISO jest zbyt mały; pobieranie mogło nie zostać zakończone")
    with path.open("rb") as image:
        image.seek(0x8001)
        if image.read(5) != b"CD001":
            raise LabError("Wybrany plik nie zawiera prawidłowego obrazu ISO 9660")


def validate_microsoft_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "microsoft.com" or hostname.endswith(".microsoft.com")
    ):
        raise LabError("Microsoft returned an unexpected download host")


def validate_massgrave_mirror_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    allowed = hostname == "tempdelivery.13376767.xyz" or hostname.endswith(".ntriver.org")
    if parsed.scheme != "https" or not allowed:
        raise LabError("Massgrave fallback returned an unexpected mirror host")


def resolve_ntriver_windows_iso(language: str) -> tuple[str, str]:
    if language != "Polish":
        raise LabError("NTriver fallback currently supports the Polish x64 image")
    filename = MASSGRAVE_POLISH_ISO["filename"]
    catalog = microsoft_get(
        "https://raw.githubusercontent.com/massgravel/massgrave.dev/main/docs/windows_11_links.md"
    )
    if filename not in catalog:
        raise LabError("The pinned Polish ISO is no longer present in the Massgrave catalog")
    resolver = (
        "https://delivery-api.ntriver.org/generate-link?" + urlencode({"filename": filename})
    )
    result = json.loads(microsoft_get(resolver))
    if not result.get("success") or not result.get("url"):
        raise LabError("NTriver could not generate the Massgrave mirror link")
    validate_massgrave_mirror_url(result["url"])
    return result["url"], filename


def resolve_microsoft_windows_iso(language: str) -> tuple[str, str]:
    page_url = "https://www.microsoft.com/en-us/software-download/windows11"
    api = "https://www.microsoft.com/software-download-connector/api/"
    get = microsoft_get
    page = get(page_url)
    edition_match = re.search(
        r'<option value="(\d+)">Windows 11 \(multi-edition ISO for x64 devices\)', page
    )
    edition = edition_match.group(1) if edition_match else "3321"
    session_id = str(uuid.uuid4())
    instance_id = "560dc9f3-1aa5-4a2f-b63c-9e18f8d0e175"

    get(
        "https://vlscppe.microsoft.com/tags?"
        + urlencode({"org_id": "y6jn8c31", "session_id": session_id})
    )
    device_script = get(
        "https://ov-df.microsoft.com/mdt.js?"
        + urlencode(
            {"instanceId": instance_id, "PageId": "si", "session_id": session_id}
        )
    )
    w_match = re.search(r"[?&]w=([A-F0-9]+)", device_script)
    rticks_match = re.search(r'rticks="\+?(\d+)', device_script)
    if not w_match or not rticks_match:
        raise LabError("Microsoft device verification response could not be parsed")
    get(
        "https://ov-df.microsoft.com/?"
        + urlencode(
            {
                "session_id": session_id,
                "CustomerId": instance_id,
                "PageId": "si",
                "w": w_match.group(1),
                "mdt": int(time.time() * 1000),
                "rticks": rticks_match.group(1),
            }
        )
    )

    common = {
        "profile": "606624d44113",
        "SKU": "undefined",
        "friendlyFileName": "undefined",
        "Locale": "en-US",
        "sessionID": session_id,
    }
    languages = None
    for attempt in range(3):
        languages = json.loads(
            get(
                api
                + "getskuinformationbyproductedition?"
                + urlencode(common | {"productEditionId": edition})
            )
        )
        if languages.get("Skus"):
            break
        if attempt < 2:
            time.sleep(2)
    if not languages or not languages.get("Skus"):
        raise LabError("Microsoft did not return Windows language options")
    try:
        sku = next(str(item["Id"]) for item in languages["Skus"] if item["Language"] == language)
    except StopIteration as exc:
        raise LabError(f"Microsoft does not currently offer the {language} ISO") from exc

    result = json.loads(
        get(
            api
            + "GetProductDownloadLinksBySku?"
            + urlencode(common | {"productEditionId": "undefined", "SKU": sku}),
            {"Referer": "https://www.microsoft.com/software-download/windows11"},
        )
    )
    if result.get("Errors"):
        error = result["Errors"][0]
        value = error.get("Value") or "unknown connector error"
        if int(error.get("Type", 0)) == 9 or "sentinel" in value.lower():
            raise LabError(
                "Microsoft zablokował generowanie ISO dla bieżącego publicznego IP (715-123130). "
                "Ponowne próby z tego samego IP nie pomogą: połącz się przez inną sieć albo odśwież adres WAN routera i spróbuj raz jeszcze."
            )
        raise LabError(f"Microsoft rejected the ISO request: {value}")
    try:
        option = next(
            item
            for item in result["ProductDownloadOptions"]
            if int(item["DownloadType"]) == 1
        )
    except (KeyError, StopIteration) as exc:
        raise LabError("Microsoft did not return a Windows x64 download") from exc
    url = option["Uri"]
    validate_microsoft_url(url)
    filename = unquote(Path(urlparse(url).path).name)
    if not filename.lower().endswith(".iso"):
        raise LabError("Microsoft returned a download that is not an ISO")
    return url, filename


def endpoint_parts(endpoint: str) -> tuple[str, str]:
    if not isinstance(endpoint, str) or endpoint.count(":") != 1:
        raise LabError(f"Invalid endpoint: {endpoint!r}")
    vm, port = endpoint.split(":")
    if vm not in PORTS or port not in PORTS[vm]:
        raise LabError(f"Unknown endpoint: {endpoint}")
    return vm, port


def validate_connections(connections: object) -> list[dict]:
    if not isinstance(connections, list):
        raise LabError("connections must be a list")
    clean = []
    for item in connections:
        if not isinstance(item, dict):
            raise LabError("Each cable must be an object")
        a, b = item.get("a"), item.get("b")
        endpoint_parts(a)
        endpoint_parts(b)
        if a == b:
            raise LabError("A cable cannot connect a port to itself")
        cable_id = str(item.get("id") or uuid.uuid4().hex[:12])
        if not cable_id.replace("-", "").isalnum():
            raise LabError("Cable IDs must contain only letters, digits, and hyphens")
        color = item.get("color", "yellow")
        if color not in ALLOWED_COLORS:
            raise LabError(f"Unsupported cable color: {color}")
        clean = [
            cable
            for cable in clean
            if cable["id"] != cable_id
            and a not in (cable["a"], cable["b"])
            and b not in (cable["a"], cable["b"])
        ]
        clean.append({"id": cable_id, "a": a, "b": b, "color": color})
    return clean


def network_assignments(connections: list[dict]) -> dict[str, str]:
    assignments = {
        f"{vm}:{port}": f"{LAB_PREFIX}loose-{vm}-{port}"
        for vm, ports in PORTS.items()
        for port in ports
    }
    for cable in validate_connections(connections):
        is_wan = cable["a"].startswith("wan:") or cable["b"].startswith("wan:")
        kind = "wan" if is_wan else "cable"
        name = f"{LAB_PREFIX}{kind}-{cable['id']}"
        assignments[cable["a"]] = name
        assignments[cable["b"]] = name
    return assignments


def bridge_name_for_network(name: str) -> str:
    return "ml" + hashlib.sha256(name.encode()).hexdigest()[:10]


def network_xml(name: str, bridge: str) -> str:
    installer = name == f"{LAB_PREFIX}installer"
    uplink = name.startswith(f"{LAB_PREFIX}wan-") or installer
    forward = "<forward mode='nat'/>" if uplink else ""
    addressing = (
        f"<ip address='172.31.{'254' if installer else '255'}.1' netmask='255.255.255.0'>"
        f"<dhcp><range start='172.31.{'254' if installer else '255'}.100' "
        f"end='172.31.{'254' if installer else '255'}.200'/></dhcp>"
        "</ip>"
        if uplink
        else ""
    )
    return (
        f"<network><name>{escape(name)}</name>{forward}"
        f"<bridge name='{xml_attr(bridge)}' stp='off' delay='0'/>{addressing}"
        "</network>"
    )


def xml_attr(value: object) -> str:
    return escape(str(value), {"'": "&apos;", '"': "&quot;"})


def interface_xml(mac: str, network: str, model: str, connected: bool) -> str:
    trusted = " trustGuestRxFilters='yes'" if model == "virtio" else ""
    driver = "<driver name='vhost'/>" if model == "virtio" else ""
    return (
        f"<interface type='network'{trusted}>"
        f"<mac address='{xml_attr(mac)}'/><source network='{xml_attr(network)}'/>"
        f"<model type='{xml_attr(model)}'/>{driver}"
        f"<link state='{'up' if connected else 'down'}'/></interface>"
    )


def cdrom_xml(path: Path, target: str) -> str:
    return (
        "<disk type='file' device='cdrom'><driver name='qemu' type='raw'/>"
        f"<source file='{xml_attr(path)}'/><target dev='{xml_attr(target)}' bus='sata'/><readonly/></disk>"
    )


def windows_domain_xml(
    name: str,
    domain_uuid: str,
    title: str,
    disk: Path,
    cdroms: str,
    interfaces: str,
    serial: str,
) -> str:
    return f"""
<domain type='kvm'>
  <name>{xml_attr(name)}</name>
  <uuid>{xml_attr(domain_uuid)}</uuid>
  <title>{escape(title)}</title>
  <sysinfo type='smbios'><system><entry name='manufacturer'>MikroTik Cable Lab</entry><entry name='product'>Windows training client</entry><entry name='serial'>{xml_attr(serial)}</entry></system></sysinfo>
  <memory unit='MiB'>6144</memory><vcpu placement='static'>4</vcpu>
  <os firmware='efi'><type arch='x86_64' machine='q35'>hvm</type><firmware><feature enabled='yes' name='secure-boot'/></firmware><smbios mode='sysinfo'/><boot dev='hd'/><boot dev='cdrom'/><bootmenu enable='yes' timeout='10000'/></os>
  <features><acpi/><apic/><smm state='on'/><hyperv mode='custom'><relaxed state='on'/><vapic state='on'/><spinlocks state='on' retries='8191'/></hyperv></features>
  <cpu mode='host-passthrough' check='none' migratable='on'/>
  <clock offset='localtime'><timer name='hypervclock' present='yes'/></clock>
  <devices>
    <disk type='file' device='disk'><driver name='qemu' type='qcow2' discard='unmap'/><source file='{xml_attr(disk)}'/><target dev='sdc' bus='sata'/></disk>
    {cdroms}{interfaces}
    <controller type='usb' model='qemu-xhci'/><input type='tablet' bus='usb'/>
    <tpm model='tpm-crb'><backend type='emulator' version='2.0'/></tpm>
    <graphics type='spice' autoport='yes'><listen type='address'/><image compression='off'/></graphics>
    <video><model type='virtio' heads='1' primary='yes'/></video>
    <sound model='ich9'/>
  </devices>
</domain>"""


def require_env_file(name: str) -> Path:
    value = os.environ.get(name)
    if not value or not Path(value).is_file():
        raise LabError(f"{name} is not set to a file; run through nix run")
    return Path(value)


class ApiHandler(SimpleHTTPRequestHandler):
    lab: Lab
    web_root: Path

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(self.web_root), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[ui] " + fmt % args + "\n")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, value: object, status: int = 200) -> None:
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self) -> dict:
        if self.headers.get_content_type() != "application/json":
            raise LabError("Requests must use application/json")
        length = int(self.headers.get("Content-Length", "0"))
        if length > 64 * 1024:
            raise LabError("Request is too large")
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise LabError("Invalid JSON") from exc

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/product/catalog":
                self.send_json(self.lab.product_store.catalog())
                return
            if parsed.path == "/api/product/workspaces":
                self.send_json({"workspaces": self.lab.product_store.list_workspaces()})
                return
            match = re.fullmatch(r"/api/product/workspaces/([^/]+)", parsed.path)
            if match:
                self.send_json(self.lab.product_store.snapshot(unquote(match.group(1))))
                return
        except WorkspaceError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/setup/status":
            self.send_json(self.lab.setup_status())
            return
        if parsed.path == "/api/state":
            try:
                self.send_json(self.lab.status())
            except LabError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        super().do_GET()

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            match = re.fullmatch(r"/api/product/workspaces/([^/]+)/canvas", path)
            if match:
                body = self.read_json()
                snapshot = self.lab.product_store.update_canvas(
                    unquote(match.group(1)),
                    body.get("positions", []),
                    body.get("cableMode"),
                )
                self.send_json(snapshot)
                return
            if path != "/api/topology":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = self.read_json()
            self.lab.save_topology(body.get("connections", []))
            self.send_json({"ok": True, "topology": self.lab.load_topology()})
        except (LabError, WorkspaceError, KeyError, TypeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            match = re.fullmatch(r"/api/product/workspaces/([^/]+)/devices", path)
            if match:
                body = self.read_json()
                snapshot = self.lab.product_store.add_device(
                    unquote(match.group(1)),
                    str(body.get("profileId", "")),
                    float(body.get("x", 0)),
                    float(body.get("y", 0)),
                    body.get("name"),
                )
                self.send_json(snapshot, HTTPStatus.CREATED)
                return
            if path == "/api/setup/start":
                body = self.read_json()
                self.lab.start_web_setup(
                    body.get("language", "Polish"), body.get("source", "microsoft")
                )
                self.send_json({"ok": True, "message": "Rozpoczęto konfigurację"})
                return
            if path == "/api/setup/start-local":
                body = self.read_json()
                self.lab.start_web_setup_local(body.get("path", ""))
                self.send_json({"ok": True, "message": "Rozpoczęto konfigurację z lokalnego ISO"})
                return
            if path == "/api/setup/seal":
                self.read_json()
                self.lab.finalize_web_setup()
                self.send_json({"ok": True, "message": "Zapisywanie szablonu"})
                return
            if path == "/api/setup/console":
                self.read_json()
                self.lab.open_template_console()
                self.send_json({"ok": True, "message": "Otwarto konsolę szablonu"})
                return
            if path == "/api/apply":
                self.read_json()
                self.lab.apply_topology()
                self.send_json({"ok": True, "message": "Zastosowano okablowanie"})
                return
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "vm"]:
                self.read_json()
                message = self.lab.action(parts[2], parts[3])
                self.send_json({"ok": True, "message": message})
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except (LabError, WorkspaceError, TypeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        try:
            match = re.fullmatch(r"/api/product/workspaces/([^/]+)/devices/([^/]+)", path)
            if not match:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            snapshot = self.lab.product_store.remove_device(
                unquote(match.group(1)), unquote(match.group(2))
            )
            self.send_json(snapshot)
        except WorkspaceError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def process_start_time(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()
        return fields[19]
    except (FileNotFoundError, IndexError, PermissionError):
        return None


def active_firewall_units(systemctl: str) -> list[str]:
    return [
        unit
        for unit in HOST_FIREWALL_UNITS
        if subprocess.run(
            [systemctl, "is-active", "--quiet", unit],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    ]


def run_firewall_guard(parent_pid: int, parent_start_time: str, systemctl: str, units: list[str]) -> int:
    if os.geteuid() != 0:
        raise LabError("The firewall guard must run as root")
    stopped: list[str] = []
    try:
        if process_start_time(parent_pid) != parent_start_time:
            return 1
        for unit in units:
            subprocess.run([systemctl, "stop", unit], check=True)
            stopped.append(unit)
        while process_start_time(parent_pid) == parent_start_time:
            time.sleep(0.5)
    finally:
        if stopped:
            subprocess.run([systemctl, "start", *stopped], check=False)
    return 0


def pause_host_firewall() -> subprocess.Popen | None:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return None
    units = active_firewall_units(systemctl)
    if not units:
        return None
    pkexec = shutil.which("pkexec") or "/run/wrappers/bin/pkexec"
    if not Path(pkexec).exists():
        raise LabError("Install pkexec so the lab can pause and restore the active host firewall")
    start_time = process_start_time(os.getpid())
    if not start_time:
        raise LabError("Cannot identify the backend process for firewall restoration")
    guard = subprocess.Popen(
        [
            pkexec,
            sys.executable,
            str(Path(__file__).resolve()),
            "firewall-guard",
            str(os.getpid()),
            start_time,
            systemctl,
            *units,
        ],
        start_new_session=True,
    )
    deadline = time.monotonic() + 60
    while active_firewall_units(systemctl):
        if guard.poll() is not None:
            raise LabError("Host firewall authorization was cancelled or failed")
        if time.monotonic() >= deadline:
            guard.terminate()
            raise LabError("Timed out while pausing the host firewall")
        time.sleep(0.2)
    print(
        f"Host firewall temporarily paused ({', '.join(units)}); it will restart when the backend exits",
        flush=True,
    )
    return guard


def serve(lab: Lab, host: str, port: int, no_browser: bool) -> None:
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise LabError("The VM controller may bind only to a loopback address")
    except ValueError as exc:
        raise LabError("Use a numeric loopback address such as 127.0.0.1") from exc
    handler = type(
        "ConfiguredApiHandler",
        (ApiHandler,),
        {"lab": lab, "web_root": lab.source / "web"},
    )
    server = ThreadingHTTPServer((host, port), handler)
    firewall_guard = None
    try:
        firewall_guard = pause_host_firewall()
        url = f"http://{host}:{server.server_port}"
        print(f"MikroTik Cable Lab: {url}", flush=True)
        if not no_browser:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if firewall_guard and firewall_guard.poll() is not None and active_firewall_units(
            shutil.which("systemctl") or "systemctl"
        ):
            print("Warning: the host firewall guard exited before the backend", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, help="lab data directory")
    parser.add_argument("--uri", help="libvirt URI (default: qemu:///system)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="prepare disks, media, networks, and domains")
    serve_parser = commands.add_parser("serve", help="run the cable management UI")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8787, type=int)
    serve_parser.add_argument("--no-browser", action="store_true")
    action_parser = commands.add_parser("vm", help="control a VM")
    action_parser.add_argument("vm", choices=VM_NAMES)
    action_parser.add_argument(
        "action", choices=("start", "shutdown", "force-stop", "reset", "promote", "console")
    )
    guard_parser = commands.add_parser("firewall-guard", help=argparse.SUPPRESS)
    guard_parser.add_argument("parent_pid", type=int)
    guard_parser.add_argument("parent_start_time")
    guard_parser.add_argument("systemctl")
    guard_parser.add_argument("units", nargs="+")
    commands.add_parser("apply", help="apply saved cabling to libvirt")
    commands.add_parser("status", help="print machine-readable lab status")
    args = parser.parse_args()
    if args.command == "firewall-guard":
        return run_firewall_guard(
            args.parent_pid, args.parent_start_time, args.systemctl, args.units
        )
    lab = Lab(args.home, args.uri)
    try:
        if args.command == "prepare":
            lab.prepare()
            print(f"Lab prepared in {lab.root}")
        elif args.command == "serve":
            serve(lab, args.host, args.port, args.no_browser)
        elif args.command == "vm":
            print(lab.action(args.vm, args.action))
        elif args.command == "apply":
            lab.apply_topology()
            print("Cabling applied")
        elif args.command == "status":
            print(json.dumps(lab.status(), indent=2))
    except LabError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
