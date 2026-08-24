# MikroTik Cable Lab

Product development is tracked on the `product` branch. See [the VirtuLab product plan](docs/product-plan.md) for the approved infinite-canvas, dynamic-device and multi-template architecture.

The in-progress product canvas runs beside the stable interface:

```bash
python3 labctl.py serve --no-browser
cd product-ui
npm install
npm run dev
```

Open `http://127.0.0.1:5173` for the product canvas and `http://127.0.0.1:8787` for the stable lab UI.

A reproducible KVM/libvirt lab built with Nix flakes. It provides:

- one RouterOS CHR `7.24.1` VM with a logical RB960PGS front panel;
- two Windows 11 client VMs;
- two Intel E1000e network cards in each Windows client;
- a wall WAN socket backed by libvirt NAT and DHCP on `172.31.255.0/24`;
- the official WinBox `4.3` Windows x64 build on an attached tools CD;
- a drag-and-drop cable workbench backed by actual isolated layer-2 libvirt networks;
- per-VM reset using immutable golden disks and disposable qcow2 overlays;
- a browser setup mode that resolves and downloads the current Windows 11 ISO directly from Microsoft;
- an INF.02-oriented [RouterOS training manual](docs/routeros-inf02-manual.md).

## MikroTik Downloads

The router software you were looking for is **Cloud Hosted Router (CHR)**, MikroTik's RouterOS build for virtual machines:

- [Official CHR download page](https://mikrotik.com/download/chr)
- [CHR 7.24.1 raw image used by this flake](https://download.mikrotik.com/routeros/7.24.1/chr-7.24.1.img.zip)
- [Official WinBox download page](https://mikrotik.com/download/winbox)
- [WinBox 4.3 Windows x64 used by this flake](https://download.mikrotik.com/routeros/winbox/4.3/WinBox_Windows.zip)

Both artifacts are fetched and hash-verified by Nix. CHR's free license enables all RouterOS features but limits upload to 1 Mbps per interface. MikroTik offers paid P1/P10/P-Unlimited licenses and 60-day paid-tier trials; see [CHR licensing](https://help.mikrotik.com/docs/spaces/ROS/pages/18350234/Cloud+Hosted+Router+CHR#CloudHostedRouter,CHR-CHRLicensing).

## Host Requirements

- x86-64 Linux with KVM enabled in firmware;
- a running system libvirt daemon with QEMU, UEFI/OVMF and `swtpm` support;
- membership in the `libvirtd` group;
- about 13 GiB RAM while all VMs run, plus at least 60 GiB free VM storage;
- your Windows ISO, named `win11.iso`, stored outside this flake directory;

## Run with Nix or NixOS

Nix is the recommended route because it pins and verifies CHR, WinBox, Lucide and every host-side command used by the project. On NixOS, add:

```nix
{
  virtualisation.libvirtd = {
    enable = true;
    qemu.swtpm.enable = true;
  };
  programs.virt-manager.enable = true;
  users.users.YOUR_USER.extraGroups = [ "libvirtd" ];
}
```

Rebuild, log out and back in after adding the group. Confirm access with:

```bash
virsh -c qemu:///system list --all
```

Keep the multi-gigabyte ISO outside the project so Nix does not copy proprietary installation media into `/nix/store`, then prepare the lab:

```bash
MIKROTIK_WIN11_ISO=/absolute/path/to/win11.iso \
MIKROTIK_VM_STORAGE=/path/on/a/fast/large/filesystem \
nix run .#setup
nix run .#ui
```

Setup stores the selected VM storage path in `~/.local/share/mikrotik-cable-lab/storage.json`. If the default filesystem has less than 60 GiB free, setup asks for another directory. The ISO may be removed after the client template has been sealed.

The UI opens at `http://127.0.0.1:8787`. If that port is occupied:

```bash
nix run .#ui -- --port 8788
```

## Run without Nix

The native route uses the same Python controller and libvirt definitions. Install the host dependencies for your distribution.

Debian or Ubuntu:

```bash
sudo apt update
sudo apt install qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients virt-viewer swtpm ovmf xorriso python3 curl
sudo usermod -aG libvirt,kvm "$USER"
```

Fedora:

```bash
sudo dnf install @virtualization virt-viewer swtpm edk2-ovmf xorriso python3 curl
sudo usermod -aG libvirt,kvm "$USER"
```

openSUSE Leap or Tumbleweed:

```bash
sudo zypper install -t pattern kvm_server kvm_tools
sudo zypper install libvirt-client virt-viewer swtpm swtpm-tools ovmf xorriso python3 curl
sudo usermod -aG libvirt,kvm "$USER"
```

See the official [openSUSE VM host and libvirt guide](https://doc.opensuse.org/documentation/leap/virtualization/html/book-virtualization/cha-libvirt-host.html).

Arch Linux:

```bash
sudo pacman -S qemu-full libvirt virt-viewer swtpm edk2-ovmf xorriso dnsmasq python curl
sudo usermod -aG libvirt,kvm "$USER"
```

Enable libvirt, then log out and back in so the new groups take effect:

```bash
sudo systemctl enable --now libvirtd
virsh -c qemu:///system list --all
```

From the project directory, download the pinned assets. Windows is not downloaded; provide your own `win11.iso` separately.

```bash
mkdir -p "$HOME/.cache/mikrotik-cable-lab"
curl -fL https://download.mikrotik.com/routeros/7.24.1/chr-7.24.1.img.zip -o "$HOME/.cache/mikrotik-cable-lab/chr-7.24.1.img.zip"
curl -fL https://download.mikrotik.com/routeros/winbox/4.3/WinBox_Windows.zip -o "$HOME/.cache/mikrotik-cable-lab/WinBox_Windows.zip"
curl -fL https://unpkg.com/lucide@0.468.0/dist/umd/lucide.min.js -o web/lucide.min.js
```

Verify all downloads before executing them:

```bash
printf '%s  %s\n' \
  50345f0197164321f1c6c933cd2a92b94222e7df76311b22b46adc3eca7a1aa8 "$HOME/.cache/mikrotik-cable-lab/chr-7.24.1.img.zip" \
  f2dc282abe7e1b8f63b13b2ba6a893b6d1c16671e2c8f8a6a5a9d3956f36100b "$HOME/.cache/mikrotik-cable-lab/WinBox_Windows.zip" \
  3411692820cb8d47543f69496aa25fd603a358f4498046f41c508a5a3342210e web/lucide.min.js \
  | sha256sum --check
```

Prepare the disks, networks and domains:

```bash
MIKROTIK_WIN11_ISO=/absolute/path/to/win11.iso \
MIKROTIK_VM_STORAGE=/path/on/a/fast/large/filesystem \
MIKROTIK_CHR_ARCHIVE="$HOME/.cache/mikrotik-cable-lab/chr-7.24.1.img.zip" \
MIKROTIK_WINBOX_ARCHIVE="$HOME/.cache/mikrotik-cable-lab/WinBox_Windows.zip" \
python3 labctl.py prepare
```

Run the web UI:

```bash
python3 labctl.py serve
```

For a different port use `python3 labctl.py serve --port 8788`. The native CLI equivalents are `python3 labctl.py status`, `python3 labctl.py apply`, and `python3 labctl.py vm router console`.

## First Lab Setup

### Browser setup mode

Start the UI before preparing any VMs:

```bash
nix run .#ui
```

Open `http://127.0.0.1:8787`, press **Tryb konfiguracji**, choose the Windows language, then press **Pobierz i rozpocznij**. The server:

1. obtains a short-lived signed ISO URL through Microsoft's software-download connector;
2. validates that the final HTTPS host belongs to Microsoft;
3. downloads the ISO atomically while showing byte progress and SHA-256;
4. prepares RouterOS, WinBox media, the installer NAT and one Windows template VM;
5. opens the template console before boot so the CD/DVD prompt is visible;
6. waits for you to install software and shut Windows down;
7. seals the template when you press **Zapisz szablon**, then creates both client overlays.

Microsoft’s generated links expire after 24 hours. The connector is used only to retrieve a public Microsoft-hosted ISO; downloading Windows does not provide a license. Manual setup with `MIKROTIK_WIN11_ISO` remains supported.

If Microsoft blocks ISO generation with error `715-123130`, open **Opcje zaawansowane** in setup mode and enter the absolute path to an existing ISO. Completed `.iso` files in the project root are suggested automatically; `.part` downloads are deliberately ignored. Local images are checked for minimum size and an ISO 9660 signature, but you remain responsible for verifying the source and SHA-256.

Advanced options provide three source choices:

- **Microsoft** resolves and downloads a signed Microsoft CDN URL.
- **Massgrave** opens the cataloged ZeroFS page interactively; after downloading, select the resulting local ISO.
- **NTriver** downloads the cataloged Polish Windows 11 Consumer 25H2 x64 image automatically and refuses to use it unless both the exact byte length and SHA-256 match the published Massgrave/MVS metadata.

This project does not download or run any activation tooling; a valid Windows license is still required.

### Terminal setup mode

The initial cabling connects `router:ether2` to Client 01 and `router:ether3` to Client 02.

The wall WAN socket is an actual libvirt NAT network, not only a visual marker. After cabling it to a RouterOS port, add a DHCP client on that interface to receive an address from `172.31.255.100-200` and use the host's Internet connection. Each Windows VM exposes `NIC 1` and `NIC 2`; Windows normally names them `Ethernet` and `Ethernet 2`.

## Install Windows and WinBox Once

`nix run .#setup` opens one template VM with NAT access and waits in the terminal:

1. Install Windows 11 normally. The template has UEFI Secure Boot, TPM 2.0, 6 GiB RAM, four vCPUs, a SATA disk, and an Intel E1000e NIC.
2. Open the `WINTOOLS` CD. Run `Install-WinBox.cmd` as administrator and verify the WinBox shortcuts. It installs WinBox 4.3 plus legacy WinBox 3.43 for discovery/MAC-connect comparison, explicit MNDP/MAC-WinBox firewall rules, and the hostname task.
3. Install any other software and configure the exact state you want Reset to restore.
4. Shut Windows down normally. Optionally run `C:\Windows\System32\Sysprep\Sysprep.exe /generalize /oobe /shutdown` first if the two clients need distinct Windows identities.
5. When the template is fully off, return to the setup terminal and press Enter.

Setup makes the template read-only and creates two small qcow2 overlays from it. Windows is installed only once. Windows licensing remains your responsibility.

Each client exposes `CLIENT01` or `CLIENT02` through SMBIOS. On its first clone boot, the task installed from `WINTOOLS` reads that serial with built-in Windows CIM, renames the computer, removes itself, and reboots once. No VirtIO or QEMU guest-agent driver is required.

For MAC discovery against a completely addressless RouterOS interface, WINTOOLS also contains `Enable-BlankRouterDiscovery.cmd`. Run it as administrator on a client only when needed. It assigns that client's primary lab NIC an RFC 5737 workstation-only address (`192.0.2.11/24` or `192.0.2.12/24`) with no gateway or DNS, disables competing lab adapters, enables the Windows File and Printer Sharing adapter binding required by MAC WinBox, and sets MTU 1500. Run `Enable-AllLabAdapters.cmd` later when the exercise needs the secondary NIC. It does not configure the router.

## Cable and VM Controls

- Pick a cable spool color, then drag from one empty socket to another.
- Select a cable and press `Delete` or `Backspace` to unplug it.
- Cable edits are applied live. Libvirt changes each stable NIC's network source in place, preserving RouterOS interface numbering and Windows adapter identity. Dropping onto an occupied port replaces its previous cable.
- **Reset** requires the VM to be off. RouterOS resets to the official blank CHR image. Both Windows clients reset to the shared template state. Libvirt's emulated TPM and UEFI variable state persist; disable device encryption unless you maintain the recovery keys.
- **Update recovery image** is the archive icon on either Windows client. Shut down both clients first. The selected client is flattened into the new shared base, then both overlays are recreated from it.
- Hold `Shift` while clicking a running VM's power button to force-stop an unresponsive guest. This is equivalent to removing power and may corrupt guest data.
- **Force stop** is available from the CLI if a guest will not shut down: `nix run . -- vm client1 force-stop`.

When the UI backend starts, it detects an active `firewall` or `firewalld` systemd service and asks Polkit for permission to pause it. Bridged WinBox MAC traffic can otherwise be dropped by host reverse-path filtering. A privileged watchdog restarts exactly the services that were active as soon as the backend process exits, including after a crash. The firewall is not changed if it was already inactive.

Useful CLI commands:

```bash
nix run . -- status
nix run . -- vm router console
nix run . -- vm router reset
nix run . -- apply
```

Persistent data lives at `~/.local/share/mikrotik-cable-lab`. Set `MIKROTIK_LAB_HOME` to override it and `MIKROTIK_LIBVIRT_URI` to use a different libvirt URI.

## Fidelity Boundary

This is a RouterOS training simulation, not an RB960PGS hardware emulator. CHR accurately supports routing, firewall, DHCP, DNS, NAT, software bridging, VLANs, queues, logs and WinBox/CLI workflows. It cannot emulate:

- the QCA8337 switch chip or hardware offload behavior;
- passive/802.3af/at PoE input/output, current sensing or voltage limits;
- SFP module EEPROM/DDM, optical levels or physical media faults;
- the MIPSBE QCA9557 CPU's performance, 128 MiB RAM or 16 MiB flash limits;
- RouterBOOT, USB power reset, beeper, voltage and board-temperature sensors.

The UI labels CHR's sixth Ethernet NIC as SFP. Inside a fresh RouterOS VM it initially appears as `ether6`; the manual renames it to `sfp1`. Use a physical RB960PGS for PoE, SFP and switch-chip labs.

## Development Checks

```bash
nix fmt flake.nix
nix flake check
```

The web server binds only to loopback by default. Do not expose it to an untrusted network: it controls local VMs and destructive reset operations.
