# VirtuLab Product Plan

Status: approved for the `product` branch.

## Product Direction

VirtuLab is a local-first virtual infrastructure workbench aimed primarily at Polish INF.02 and INF.03 education. The stable `main` branch preserves the original MikroTik lab. Product development happens on `product` until a milestone is ready to merge.

Confirmed decisions:

- public repository: `doromiert/virtulab`;
- multiple named labs from the first product milestone;
- Polish default UI with complete English translation support;
- dark Figma-style interface with controls floating above an infinite canvas;
- React, TypeScript, Vite and React Flow for the canvas;
- a versioned SQLite workspace model and structured Python API;
- an SG3428 behavioral profile backed by Linux and Open vSwitch, not TP-Link firmware;
- `main` remains GitHub's default stable branch.

## Canvas Foundation

The first milestone provides:

1. infinite two-dimensional pan and zoom;
2. persisted device positions and stacking order;
3. dynamic device add, remove, duplicate and rename operations;
4. a toggleable floating toolbox and contextual inspector;
5. opaque status and quick-action bars beneath devices that act as drag handles;
6. typed ports and connector compatibility;
7. realistic, straight and hidden cable display modes;
8. multiple named labs with versioned import and export;
9. migration of the current router, clients, ports and cable topology;
10. keyboard-accessible selection, deletion and zoom controls.

Interaction requirements:

- devices can be dragged from any non-interactive part of their body; the status bar is not the only drag handle;
- device profiles are dragged from the toolbox onto an exact canvas position, with click-to-add retained only as a keyboard fallback;
- visible sockets are the cable drag targets, matching the stable lab's socket-to-socket interaction instead of exposing editor handles;
- connected socket outlines use their cable's exact color;
- operating systems are selected from the template catalog, never edited as an arbitrary string;
- printer devices visibly expose a paper output tray, network port and USB-B port;
- cable paths render above the chassis surface while port labels, sockets and device controls remain legible above the path;
- the cable palette includes built-in colors and three persistent custom slots; choosing a new custom value overwrites that slot;
- selecting a cable and choosing a palette color recolors the existing cable, while the active color is used for new cables.

Cable runtime type is separate from cable presentation. Initial connector types are Ethernet copper, fiber/SFP, RJ45 console, USB-A/B/C, serial, power and visual-only. Hidden mode suppresses cable paths while retaining connected-port indicators.

## Device Profiles

Initial and planned profiles:

- MikroTik RB960PGS logical profile backed by RouterOS CHR;
- generic x86 workstation and server;
- TP-Link JetStream SG3428 behavioral profile;
- generic unmanaged 5, 8, 16 and 24-port switches;
- virtual network printer;
- OpenWrt wireless access point with RF propagation explicitly out of scope;
- OpenWrt, VyOS, OPNsense and pfSense router/firewall appliances where image terms permit;
- NAS and service appliances for Samba, NFS, DNS, DHCP, web and database exercises;
- passive patch panels, wall jacks, SFP modules and media converters.

### SG3428 Behavioral Profile

The profile exposes 24 gigabit RJ45 ports, 4 SFP slots, an RJ45 console port and a Micro-USB console port. The first functional release targets 802.1Q access/trunk VLANs, STP/RSTP, LACP, LLDP, port mirroring and port isolation through Open vSwitch. Static routing can be added with FRR.

The profile must not claim TP-Link firmware, Omada adoption, proprietary CLI/GUI fidelity, hardware ACL limits or switch-silicon behavior.

### Virtual Printer

The printer appliance uses CUPS or `ippeveprinter`, IPP Everywhere discovery and a JetDirect-compatible TCP 9100 listener. Ghostscript renders accepted jobs into PDF files. The internal device view provides an output tray with job state, page count, preview, download, cancel, delete and reprint actions.

Network printing is functional first. USB printer connections remain clearly marked visual-only until cross-VM USB device emulation is implemented safely.

## OS Template Catalog

Templates are immutable revisions. Each device runtime uses its own qcow2 overlay, so switching templates does not destroy another installation. Built-in entries are download manifests or source connectors; proprietary installation media is never committed or redistributed.

Initial catalog:

- Windows 11 from Microsoft's official connector or user ISO;
- Windows Server Evaluation;
- Debian;
- Ubuntu LTS;
- Fedora;
- openSUSE Leap and Tumbleweed;
- Alpine Linux;
- NixOS from official release media;
- Red Hat Enterprise Linux from a user-supplied ISO or authenticated Red Hat Developer download;
- FreeBSD;
- OpenWrt and other device-specific appliance images.

macOS remains a user-supplied, Apple-hardware-only stretch goal. VirtuLab will not provide an automated non-Apple macOS installation path.

## Hardware Editor

Double-clicking a workstation or server enters a focused internal view. A simplified motherboard grows as components are added and maps to structured libvirt configuration:

- CPU and memory;
- machine type, firmware and TPM;
- storage controllers and disks;
- PCIe slots and network adapters;
- USB controllers and devices;
- display, boot order and removable media.

Changes are classified before application as live, shutdown-required or destructive. Stable device identifiers retain MAC addresses, libvirt aliases, disk targets and domain UUIDs.

## Persistence and Runtime

SQLite is the transactional source of truth for workspaces, devices, ports, cables, templates, immutable template revisions, hardware configuration, printer jobs and canvas state. Existing JSON state receives a one-time, repeatable importer with a backup.

Runtime drivers are separated by capability:

- libvirt virtual machine;
- switch appliance;
- printer appliance;
- passive device;
- Internet/NAT connector;
- visual-only peripheral.

The product branch will replace whole-host firewall suspension with a narrowly scoped privileged exception for VirtuLab bridges.

## Delivery Order

1. Versioned workspace schema and current-lab importer.
2. Infinite canvas, floating chrome and dynamic device toolbox.
3. Device and cable CRUD with persisted positions and display modes.
4. Structured libvirt reconciler and visual hardware editor.
5. SG3428 Open vSwitch appliance.
6. Immutable template catalog and setup workflows.
7. Virtual printer and PDF output tray.
8. Additional appliances, passive infrastructure and course-oriented lab packs.
