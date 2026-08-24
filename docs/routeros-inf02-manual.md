# RouterOS 7 / MikroTik manual for INF.02

Version: 1.0, RouterOS CHR 7.24.1, WinBox 4.3

This manual targets the Polish qualification **INF.02: Administracja i eksploatacja systemow komputerowych, urzadzen peryferyjnych i lokalnych sieci komputerowych**. INF.03 concerns websites, databases and web applications; it is not the network-device qualification. MikroTik is not mandated by CKE. RouterOS is used here to practice vendor-neutral INF.02 outcomes.

Polish characters are intentionally omitted from commands and object names. Explanatory text uses English so the RouterOS menu and command names match the software.

## 1. Scope and evidence

The exercises cover addressing, managed switching, VLANs, IPv4/IPv6, DHCP, DNS integration, static routing, NAT, firewalling, monitoring, backup/restore, troubleshooting and bandwidth control. Wireless configuration and physical copper termination require equipment that is not present in this three-VM lab.

For every exercise retain four artifacts:

1. a physical/logical topology and address table;
2. `/export file=...` from RouterOS (RouterOS v7 hides sensitive values by default);
3. objective test results: `ping`, `tracert`, interface counters or packet capture;
4. a short work report listing changes, tests, faults and corrections.

Treat the lab as real equipment. Plan the addresses before touching WinBox, change one subsystem at a time, verify immediately, and record the result. Unless an exercise explicitly says to continue, exercises A-F are independent: reset R1, complete Standard preparation, and clear old static addresses/routes from Windows before starting. Exercise G continues F, I continues G, and J may continue any working routed topology.

## 2. Lab mapping and limitations

| UI socket | RouterOS after fresh reset | RB960PGS role |
|---|---|---|
| ether1 | `ether1` | copper port 1, PoE-in physically |
| ether2-ether5 | `ether2`-`ether5` | copper ports 2-5, PoE-out physically |
| SFP | `ether6`, renamed `sfp1` below | logical substitute for SFP |
| Client 01 NIC 1/2 | Windows Ethernet / Ethernet 2 | two virtual E1000e NICs |
| Client 02 NIC 1/2 | Windows Ethernet / Ethernet 2 | two virtual E1000e NICs |
| Wall WAN | libvirt NAT and DHCP | simulated upstream, `172.31.255.0/24` |

One UI cable creates one isolated Ethernet segment. An unplugged socket remains attached to a private dead-end segment so interface numbering does not change. Cable changes are applied only while all guests are off.

CHR does not model PoE, optics, the QCA8337 switch chip, MIPS performance or hardware offload. Do not use this lab to claim that `H` flags, PoE current limits, SFP DDM values or RouterBOOT behavior match an RB960PGS.

## 3. Standard preparation

Use this procedure after each RouterOS reset.

1. Cable Client 01 to `ether2` and Client 02 to `ether3`; cable changes apply live, so the VMs may already be running.
2. Open WinBox on Client 01. Select **Neighbors**, wait for the router MAC, connect as `admin` with an empty password.
3. If RouterOS offers a default-configuration dialog, choose **Remove Configuration** only when the exercise requires the clean baseline used in this manual.
4. Open **New Terminal** and run:

```routeros
/system identity set name=R1-INF02
/interface ethernet set [find default-name=ether6] name=sfp1
/user add name=student group=full password="USE-A-UNIQUE-LAB-PASSWORD"
/system clock set time-zone-name=Europe/Warsaw
/system note set show-at-login=yes note="INF.02 training router - changes must be documented"
```

5. Open a second WinBox session and verify the `student` login. Only then run `/user disable [find name=admin]` in the first session. Never leave a blank administrator password or disable the only tested administrator.
6. Enter Safe Mode with `Ctrl+X` before a risky remote change. `SAFE` appears in the terminal prompt. Press `Ctrl+X` again to commit. If connectivity is lost, the Safe Mode changes roll back when the session times out.

If MAC discovery does not show the router, verify the cable in the UI, apply it with all VMs off, and check that both VMs are running. MAC WinBox works only within the same layer-2 segment.

## 4. Exercise A: IPv4 addressing and basic diagnosis

Objective: configure two routed LANs, prove local and routed connectivity, and interpret the route table.

Address plan:

| Node | Interface | IPv4 address | Gateway |
|---|---|---|---|
| R1 | ether2 | `192.168.10.1/24` | none |
| Client 01 | Ethernet | `192.168.10.10/24` | `192.168.10.1` |
| R1 | ether3 | `192.168.20.1/24` | none |
| Client 02 | Ethernet | `192.168.20.10/24` | `192.168.20.1` |

RouterOS:

```routeros
/ip address add address=192.168.10.1/24 interface=ether2 comment="LAN10 gateway"
/ip address add address=192.168.20.1/24 interface=ether3 comment="LAN20 gateway"
/ip address print detail
/ip route print detail
```

Windows, in an elevated PowerShell window on each client:

```powershell
Get-NetAdapter
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.10.10 -PrefixLength 24 -DefaultGateway 192.168.10.1
Set-DnsClientServerAddress -InterfaceAlias "Ethernet" -ServerAddresses 192.168.10.1
```

Use `192.168.20.10`, prefix `24` and gateway/DNS `192.168.20.1` on Client 02.

Tests:

```powershell
ipconfig /all
ping 192.168.10.1
ping 192.168.20.10
tracert -d 192.168.20.10
route print -4
```

Expected result: each client reaches its gateway and the other client. `tracert` crosses R1. `/ip route print` shows two dynamic active connected network routes (`DAc`/`DAC`, depending on print format), one for each `/24`. Windows Firewall may block inbound echo; if cross-client ping fails but gateway pings work, temporarily enable the built-in **Core Networking Diagnostics - ICMP Echo Request (ICMPv4-In)** rule rather than disabling the whole firewall.

## 5. Exercise B: DHCP server, leases and DNS forwarding

Start from Exercise A's cabling, but reset RouterOS and return both Windows adapters to DHCP:

```powershell
Remove-NetIPAddress -InterfaceAlias "Ethernet" -Confirm:$false -ErrorAction SilentlyContinue
Remove-NetRoute -InterfaceAlias "Ethernet" -Confirm:$false -ErrorAction SilentlyContinue
Set-NetIPInterface -InterfaceAlias "Ethernet" -Dhcp Enabled
Set-DnsClientServerAddress -InterfaceAlias "Ethernet" -ResetServerAddresses
```

Configure R1:

```routeros
/ip address add address=192.168.10.1/24 interface=ether2 comment="CLIENT01 LAN"
/ip address add address=192.168.20.1/24 interface=ether3 comment="CLIENT02 LAN"
/ip pool add name=pool10 ranges=192.168.10.100-192.168.10.149
/ip pool add name=pool20 ranges=192.168.20.100-192.168.20.149
/ip dhcp-server add name=dhcp10 interface=ether2 address-pool=pool10 lease-time=1h disabled=no
/ip dhcp-server add name=dhcp20 interface=ether3 address-pool=pool20 lease-time=1h disabled=no
/ip dhcp-server network add address=192.168.10.0/24 gateway=192.168.10.1 dns-server=192.168.10.1 domain=lab.inf02
/ip dhcp-server network add address=192.168.20.0/24 gateway=192.168.20.1 dns-server=192.168.20.1 domain=lab.inf02
/ip dns set allow-remote-requests=yes servers=1.1.1.1,9.9.9.9 cache-size=4096KiB
/ip dns static add name=r1.lab.inf02 address=192.168.10.1 ttl=1h
```

Renew each client:

```powershell
ipconfig /release
ipconfig /renew
ipconfig /all
nslookup r1.lab.inf02
```

Inspect and reserve a lease in WinBox under **IP > DHCP Server > Leases**, or use:

```routeros
/ip dhcp-server lease print detail
/ip dhcp-server lease print detail
# Note the selected lease item ID, then replace *1 below with that actual ID:
/ip dhcp-server lease make-static *1
```

Do not copy the example item ID blindly and do not make every lease static. Identify the intended MAC address first. Expected result: each client receives an address from its own pool, correct gateway, DNS server and `lab.inf02` suffix. External DNS queries require a real upstream and will fail in this isolated lab; the static local record must still resolve.

## 6. Exercise C: software bridge and MAC learning

Objective: place both clients in one broadcast domain and inspect layer-2 learning.

```routeros
/interface bridge add name=br-lan protocol-mode=rstp comment="INF02 access bridge"
/interface bridge port add bridge=br-lan interface=ether2
/interface bridge port add bridge=br-lan interface=ether3
/ip address add address=192.168.30.1/24 interface=br-lan
/interface bridge port print detail
/interface bridge host print
```

Set Client 01 to `192.168.30.10/24` and Client 02 to `192.168.30.20/24`; a gateway is not required for same-subnet tests. Generate traffic with `ping`, then repeat `/interface bridge host print`.

Expected result: dynamic MAC entries identify which client is learned on `ether2` and `ether3`. Client-to-client frames are switched by RouterOS software. The CHR result does not demonstrate RB960PGS QCA8337 hardware offload.

Loop test, optional and disruptive: with all VMs off, connect `ether4` to `ether5`, apply cabling and start R1. Add both to `br-lan`; inspect `/interface bridge port print detail` and logs. RSTP should block one side of the loop. Remove this cable before later exercises.

## 7. Exercise D: VLAN access ports and inter-VLAN routing

Objective: build VLAN 10 and VLAN 20 on access ports, route between them, and verify isolation at layer 2.

Keep Client 01 on `ether2` and Client 02 on `ether3`. Start with VLAN filtering disabled so management is not cut off:

```routeros
/interface bridge add name=br-vlan protocol-mode=rstp vlan-filtering=no
/interface bridge port add bridge=br-vlan interface=ether2 pvid=10 ingress-filtering=yes frame-types=admit-only-untagged-and-priority-tagged
/interface bridge port add bridge=br-vlan interface=ether3 pvid=20 ingress-filtering=yes frame-types=admit-only-untagged-and-priority-tagged
/interface bridge vlan add bridge=br-vlan vlan-ids=10 tagged=br-vlan untagged=ether2
/interface bridge vlan add bridge=br-vlan vlan-ids=20 tagged=br-vlan untagged=ether3
/interface vlan add name=vlan10 interface=br-vlan vlan-id=10
/interface vlan add name=vlan20 interface=br-vlan vlan-id=20
/ip address add address=10.10.10.1/24 interface=vlan10
/ip address add address=10.20.20.1/24 interface=vlan20
/interface bridge set br-vlan vlan-filtering=yes
```

Set Client 01 to `10.10.10.10/24`, gateway `10.10.10.1`; set Client 02 to `10.20.20.10/24`, gateway `10.20.20.1`.

Verify:

```routeros
/interface bridge vlan print detail
/interface bridge port print detail
/interface vlan print detail
/ip route print where dst-address in 10.10.10.0/24,10.20.20.0/24
```

Expected result: untagged client traffic is classified into the port PVID, R1 is a tagged bridge member for both VLANs, and routed traffic crosses the `vlan10`/`vlan20` interfaces. If management is lost, let Safe Mode roll back. Common errors are omitting `br-vlan` from the tagged list, assigning the gateway IP to a physical port, and enabling filtering before the VLAN table is complete.

Trunk extension: cable a client to `ether4`, add `ether4` as a tagged member of VLAN 10 and 20, and create VLAN interfaces in a VLAN-capable guest. Windows client NIC drivers do not consistently expose VLAN tagging, so this is best completed with a managed switch or Linux client.

## 8. Exercise E: IPv6 addressing and firewall baseline

Use deterministic lab-only ULA subnets `fd20:2:10:10::/64` for Client 01 and `fd20:2:10:20::/64` for Client 02. Production ULA global IDs should be pseudo-random as required by RFC 4193.

```routeros
/ipv6 address add address=fd20:2:10:10::1/64 interface=ether2 advertise=yes
/ipv6 address add address=fd20:2:10:20::1/64 interface=ether3 advertise=yes
/ipv6 nd set [find interface=all] disabled=yes
/ipv6 nd add interface=ether2 managed-address-configuration=no other-configuration=no
/ipv6 nd add interface=ether3 managed-address-configuration=no other-configuration=no
/ipv6 firewall filter add chain=input action=accept connection-state=established,related,untracked comment="allow established"
/ipv6 firewall filter add chain=input action=drop connection-state=invalid comment="drop invalid"
/ipv6 firewall filter add chain=input action=accept protocol=icmpv6 comment="ICMPv6 is required"
/ipv6 firewall filter add chain=input action=accept in-interface=ether2 protocol=tcp dst-port=22,8291 comment="LAN management"
/ipv6 firewall filter add chain=input action=drop comment="INPUT default deny"
/ipv6 firewall filter add chain=forward action=accept connection-state=established,related,untracked comment="FORWARD established"
/ipv6 firewall filter add chain=forward action=drop connection-state=invalid comment="FORWARD invalid"
/ipv6 firewall filter add chain=forward action=accept protocol=icmpv6 comment="required ICMPv6"
/ipv6 firewall filter add chain=forward action=accept in-interface=ether2 out-interface=ether3 comment="LAN10 to LAN20 exercise"
/ipv6 firewall filter add chain=forward action=accept in-interface=ether3 out-interface=ether2 comment="LAN20 to LAN10 exercise"
/ipv6 firewall filter add chain=forward action=drop comment="FORWARD default deny"
```

On Windows run `ipconfig /all`, then ping the router's link-local address with its zone ID and the ULA address. Do not block all ICMPv6: neighbor discovery, router advertisements, path MTU discovery and error reporting depend on it.

The isolated lab has no global IPv6 upstream. Success means clients learn prefixes/default routers as intended and can reach the local R1 addresses.

## 9. Exercise F: WAN/LAN, source NAT and destination NAT

Recable Client 01 to `ether1` (WAN test host) and Client 02 to `ether2` (LAN host).

| Node | Address | Role |
|---|---|---|
| Client 01 | `198.51.100.2/24`, GW `198.51.100.1` | simulated Internet server |
| R1 ether1 | `198.51.100.1/24` | WAN |
| R1 ether2 | `192.168.10.1/24` | LAN |
| Client 02 | `192.168.10.10/24`, GW `192.168.10.1` | internal client/server |

`198.51.100.0/24` is an RFC 5737 documentation network. It is not public Internet access.

```routeros
/interface list add name=WAN
/interface list add name=LAN
/interface list member add list=WAN interface=ether1
/interface list member add list=LAN interface=ether2
/ip address add address=198.51.100.1/24 interface=ether1
/ip address add address=192.168.10.1/24 interface=ether2
/ip firewall nat add chain=srcnat src-address=192.168.10.0/24 out-interface-list=WAN action=src-nat to-addresses=198.51.100.1 comment="LAN source NAT"
```

Enable IIS on Client 01 and Client 02 from elevated PowerShell, then reboot if requested:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName IIS-WebServerRole -All -NoRestart
Set-Content C:\inetpub\wwwroot\index.html "INF02 test server on $env:COMPUTERNAME"
```

From Client 02, run `curl.exe http://198.51.100.2/`. Inspect translations:

```routeros
/ip firewall connection print detail where dst-address~"198.51.100.2"
/tool torch interface=ether1
```

Publish Client 02's IIS through R1's WAN address on TCP 8080:

```routeros
/ip firewall nat add chain=dstnat in-interface-list=WAN protocol=tcp dst-address=198.51.100.1 dst-port=8080 action=dst-nat to-addresses=192.168.10.10 to-ports=80 comment="publish Client02 IIS"
```

From Client 01 run `curl.exe http://198.51.100.1:8080/`. Expected result: the Client 02 page is returned. This proves destination NAT without pretending the lab has Internet access.

## 10. Exercise G: stateful firewall and secure management

Continue from Exercise F. Add rules in this exact order. RouterOS evaluates top to bottom and stops at the first match.

```routeros
/ip firewall filter add chain=input action=accept connection-state=established,related,untracked comment="INPUT established"
/ip firewall filter add chain=input action=drop connection-state=invalid comment="INPUT invalid"
/ip firewall filter add chain=input action=accept protocol=icmp comment="INPUT diagnostic ICMP"
/ip firewall filter add chain=input action=accept in-interface-list=LAN protocol=udp dst-port=53,67,68 comment="LAN DNS DHCP"
/ip firewall filter add chain=input action=accept in-interface-list=LAN protocol=tcp dst-port=22,53,8291 comment="LAN management"
/ip firewall filter add chain=input action=drop comment="INPUT default deny"
/ip firewall filter add chain=forward action=fasttrack-connection connection-state=established,related hw-offload=no comment="FORWARD fasttrack"
/ip firewall filter add chain=forward action=accept connection-state=established,related,untracked comment="FORWARD established"
/ip firewall filter add chain=forward action=drop connection-state=invalid comment="FORWARD invalid"
/ip firewall filter add chain=forward action=accept connection-nat-state=dstnat in-interface-list=WAN comment="published services"
/ip firewall filter add chain=forward action=accept in-interface-list=LAN out-interface-list=WAN comment="LAN to WAN"
/ip firewall filter add chain=forward action=drop comment="FORWARD default deny"
/ip service set winbox address=192.168.10.0/24
/ip service set ssh address=192.168.10.0/24
/ip service disable telnet,ftp,www,api,api-ssl
/tool mac-server set allowed-interface-list=LAN
/tool mac-server mac-winbox set allowed-interface-list=LAN
/tool mac-server ping set enabled=no
/ip neighbor discovery-settings set discover-interface-list=LAN
```

Tests:

- Client 02 can open WinBox to `192.168.10.1` and reach Client 01 through source NAT.
- Client 01 cannot open IP WinBox to `198.51.100.1` and cannot discover/connect to R1 with MAC WinBox.
- Client 01 can reach the explicitly published `198.51.100.1:8080` service.
- Rule counters increase under **IP > Firewall > Filter Rules**.

Do not add an unconditional allow rule above the policy and then call the firewall complete. Export and annotate the final order.

## 11. Exercise H: static routes

INF.02 requires interpreting route tables and configuring static routes. A fully routed multi-router topology needs another router; this lab has one. Use this limited exercise to validate syntax and route selection, then repeat on physical equipment with two routers.

With Client 01 attached to `ether1` at `198.51.100.2/24`, add a test route through that next hop:

```routeros
/ip route add dst-address=203.0.113.0/24 gateway=198.51.100.2 check-gateway=arp distance=1 comment="training static route"
/ip route add blackhole dst-address=203.0.113.0/24 distance=250 comment="fallback blackhole"
/ip route print detail where dst-address=203.0.113.0/24
/ip route check dst-ip=203.0.113.10
```

Expected result: the gateway route is active while ARP confirms the next hop; the high-distance blackhole is inactive as a fallback. Stop Client 01 and wait roughly two check intervals to observe failover. A UI cable change is applied only while R1 is off. This does **not** prove end-to-end forwarding because Client 01 has no downstream `203.0.113.0/24` network.

On a two-router extension, configure a loopback or LAN behind R2, add reciprocal routes, ping both directions, run traceroute, then remove one return route to demonstrate asymmetric failure.

Recognition task: inspect the route flags/protocol columns in RouterOS documentation and distinguish connected/static routes from RIP, OSPF and BGP routes. Explain that OSPF is an interior link-state protocol, RIP is an interior distance-vector protocol, and BGP exchanges reachability between autonomous systems. Dynamic protocol configuration is an extension; do not invent a second neighbor in this one-router topology.

## 12. Exercise I: queues and bandwidth measurement

CHR free is already limited to 1 Mbps upload per interface. A queue configured above that rate cannot overcome the license limit. Use a lower value for a visible result.

Continue with Client 02 at `192.168.10.10`:

```routeros
/queue simple add name="CLIENT02-256K" target=192.168.10.10/32 max-limit=256k/256k burst-limit=384k/384k burst-threshold=192k/192k burst-time=10s/10s
/queue simple print stats interval=1
```

Create a deterministic 2 MiB IIS test file on Client 01:

```powershell
fsutil file createnew C:\inetpub\wwwroot\test.bin 2097152
```

FastTrack bypasses simple queues. Disable it and clear existing tracked connections before measuring:

```routeros
/ip firewall filter disable [find where action=fasttrack-connection]
/ip firewall connection remove [find]
```

From Client 02 run `curl.exe -o NUL http://198.51.100.2/test.bin`. Record queue bytes/packets and measured before/after rates. Change `max-limit` to `512k/512k`, clear the connection table again, and compare.

## 13. Exercise J: logging, packet capture and fault diagnosis

RouterOS local tools:

```routeros
/interface ethernet monitor ether2 once
/interface print stats-detail
/log print follow
/tool ping 192.168.10.10 count=5 size=1400 do-not-fragment
/tool traceroute 198.51.100.2
/tool profile cpu=all
/tool sniffer quick interface=ether2 ip-protocol=icmp
```

Save a packet capture for Wireshark:

```routeros
/tool sniffer set file-name=inf02-capture.pcap filter-interface=ether2 file-limit=10MiB
/ip arp remove [find where interface=ether2]
/tool sniffer start
/tool ping 192.168.10.10 count=5
/tool sniffer stop
/file print where name="inf02-capture.pcap"
```

Download the file through WinBox **Files** and inspect Ethernet, ARP, IPv4 and ICMP headers in Wireshark.

Remote logging exercise: install or use an instructor-approved syslog collector on Client 02, or use Wireshark to prove UDP delivery even without a collector. Then configure R1:

```routeros
/system logging action add name=remote-client target=remote remote=192.168.10.10 remote-port=514
/system logging add topics=warning action=remote-client
/log warning "INF02 remote logging test"
```

Capture `udp.port == 514` on Client 02 and verify the message. In production, use a protected management network and authenticated/encrypted transport where supported; plain UDP syslog provides neither confidentiality nor delivery confirmation.

Seed and diagnose these faults one at a time:

1. wrong Windows prefix (`/16` instead of `/24`);
2. duplicate IPv4 address;
3. wrong default gateway;
4. DHCP pool outside the interface subnet;
5. access port with the wrong PVID;
6. default-deny firewall rule placed first;
7. missing return route;
8. cable shown in the UI but not yet applied;
9. DNS forwarding disabled while clients use R1 as DNS;
10. service listening on a host but blocked by Windows Firewall.

Use a layer-by-layer order: power/VM state, cable/link, MAC/ARP, local IP, gateway, route, firewall/NAT, DNS, application. Record evidence before changing configuration.

## 14. Exercise K: backup, export, update planning and restore

Binary backup is version/device oriented; text export is reviewable and useful for migration. Create both:

```routeros
/system backup save name=inf02-clean password="Backup-Inf02!"
/export file=inf02-clean
/file print
/system package print
/system resource print
/system routerboard print
```

`/system routerboard print` on CHR will not report a physical RB960PGS RouterBOARD. That is expected.

Before updating production equipment:

1. read the stable changelog and architecture requirements;
2. verify free space and current backup/export;
3. define a maintenance window and rollback method;
4. update RouterOS packages, reboot, then update RouterBOOT on physical hardware if required;
5. verify interfaces, routes, services, logs and monitoring after reboot.

The lab uses a Nix-pinned CHR image. Do not update the golden router merely to complete this exercise. Practice the planning and inspection commands, and update a disposable copy only.

Restore test A: make a harmless identity change, then import selected text commands from the `.rsc` export. Read an export before importing it; imports execute commands and are not transactional.

Restore test B, binary backup: on a disposable runtime copy, change the identity, then run `/system backup load name=inf02-clean.backup password="Backup-Inf02!"`. Confirm the reboot and verify the restored identity, users, addresses, firewall and services. Binary backup restore is intentionally disruptive and should be tested before relying on it.

Restore test C: shut down R1 and use the UI **Reset** button. This deletes the runtime overlay and restores the official clean CHR golden image. It is a hypervisor reset, not RouterOS `/system backup load`.

## 15. Integrated 150-minute practical task

Start from a clean R1 reset and cleared Windows network settings. Scenario: an office has a WAN test host on Client 01 and an internal workstation/web server on Client 02. Configure R1 so the workstation receives DHCP, convert that lease to static, resolve a local DNS name to the reserved address, reach the WAN through source NAT, and publish IIS as TCP 8080. Secure both IP and MAC router management to the LAN, enforce default-deny firewall policy, cap the workstation at 512 kbps, and provide evidence.

Required values:

| Item | Value |
|---|---|
| WAN | `198.51.100.0/24` |
| R1 WAN | `198.51.100.1` |
| Client 01 | `198.51.100.2`, gateway `198.51.100.1` |
| LAN | `10.50.0.0/26` |
| R1 LAN | first usable address |
| DHCP pool | usable addresses 20 through 40 |
| Local DNS record | `server.inf02.test` -> Client 02 lease |
| Published service | R1 WAN TCP 8080 -> Client 02 TCP 80 |
| WinBox | LAN only |
| Queue | Client 02, `512k/512k` |

Deliverables:

1. physical and logical diagrams with port labels;
2. completed address table including prefix, mask, gateway and DNS;
3. RouterOS v7 export with meaningful comments (sensitive values hidden by default);
4. DHCP lease and DNS test evidence;
5. source NAT and destination NAT tests;
6. firewall rule counters proving allowed and denied cases;
7. queue statistics;
8. a six-line service report: work performed, tests, one encountered fault and its correction.

Suggested time budget: 15 minutes planning, 20 cabling/addresses, 25 DHCP/DNS, 20 NAT/service, 25 firewall, 10 queue, 20 testing/evidence, 15 review. This is a RouterOS-focused partial INF.02 task, not a complete mock exam: official tasks may also require physical cabling, workstation/server administration, costing and broader documentation. Do not use this manual's finished commands during a timed assessment; derive and verify them from the requirements.

## 16. Assessment checklist

- Interfaces are identified by both name and MAC before configuration.
- Prefix lengths and address ranges are mathematically correct.
- Gateway addresses belong to their client subnet.
- DHCP pools exclude network, broadcast, gateway and reserved static addresses.
- VLAN access/trunk membership and PVIDs match the diagram.
- Connected, static and default routes are distinguishable.
- NAT is separated from firewall permission.
- Stateful rules precede default-deny rules; counters prove matches.
- Management services are restricted by interface/source and unused services disabled.
- IPv6 policy permits required ICMPv6.
- Backups and exports are created before disruptive work.
- Tests cover positive and negative cases.
- Documentation reflects the final state, not the intended state.

## 17. Topics requiring additional equipment

Complete these INF.02 outcomes outside this VM lab:

- terminate T568A/T568B on 8P8C, keystone and patch panel; certify wire map, length and faults;
- configure a managed physical switch, tagged uplink, port mirror and loop protection;
- configure an access point, SSID, channel plan and WPA2/WPA3 security;
- test actual RB960PGS passive/802.3af/at PoE safely with correct voltage and load limits;
- insert a supported SFP, inspect module information/DDM and diagnose optical levels;
- compare RB960PGS switch-chip offload against software bridging.
- add Windows Server and Linux server VMs for AD DS, Group Policy, server DHCP/DNS, RRAS, WDS, file/print services and other server outcomes not covered by Windows 11 clients.

## 18. Authoritative references

- [CKE INF.02 sample practical task](https://cke.gov.pl/images/_EGZAMIN_ZAWODOWY/Formula_2019/Przykladowe_zadania/inf_02.pdf)
- [CKE technician-informatics examination guide](https://cke.gov.pl/images/_EGZAMIN_ZAWODOWY/Formula_2019/Informatory/technik_informatyk.pdf)
- [Official technician-informatics curriculum](https://infozawodowe.men.gov.pl/image/professionCoreCurriculum/technik-informatyk_24d8e416b7d1838ec161bd91a891df84.pdf)
- [CKE INF.02 equipment specification](https://cke.gov.pl/images/_EGZAMIN_ZAWODOWY/Formula_2019/Wyposazenie/2023_2024/INF.02_wyp_2024-2026_WK.pdf)
- [RouterOS documentation](https://help.mikrotik.com/docs/)
- [CHR documentation and licensing](https://help.mikrotik.com/docs/spaces/ROS/pages/18350234/Cloud+Hosted+Router+CHR)
- [RB960PGS product specifications](https://mikrotik.com/product/RB960PGS)
- [hEX PoE hardware manual](https://manual.mikrotik.com/hardware/hex-poe/)
- [RouterOS bridge VLAN table](https://help.mikrotik.com/docs/spaces/ROS/pages/28606465/Bridge+VLAN+Table)
- [RouterOS firewall](https://help.mikrotik.com/docs/spaces/ROS/pages/48660574/Filter)

When testing the manual, report the exercise, exact command, RouterOS error text, current cabling and relevant RouterOS v7 `/export`. Sensitive values are hidden by default. That is enough context to distinguish a documentation error from stale state or a topology mismatch.
