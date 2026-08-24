import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import labctl


class TopologyTests(unittest.TestCase):
    def test_default_topology_shares_network_at_each_cable_end(self):
        assignments = labctl.network_assignments(labctl.DEFAULT_CONNECTIONS)
        self.assertEqual(assignments["router:ether2"], assignments["client1:ethernet"])
        self.assertEqual(assignments["router:ether3"], assignments["client2:ethernet"])
        self.assertNotEqual(assignments["router:ether1"], assignments["router:ether2"])
        self.assertIn("client1:ethernet2", assignments)
        self.assertIn("client2:ethernet2", assignments)

    def test_wan_cable_creates_nat_network(self):
        cable = [{"id": "internet", "a": "wan:uplink", "b": "router:ether1", "color": "red"}]
        assignments = labctl.network_assignments(cable)
        self.assertEqual(assignments["wan:uplink"], assignments["router:ether1"])
        self.assertIn("mikrolab-wan-", assignments["router:ether1"])
        document = ET.fromstring(labctl.network_xml(assignments["router:ether1"], "mlab00"))
        self.assertEqual(document.find("forward").attrib["mode"], "nat")
        self.assertEqual(document.find("ip").attrib["address"], "172.31.255.1")

    def test_installer_network_has_separate_nat_subnet(self):
        document = ET.fromstring(labctl.network_xml("mikrolab-installer", "mlabinst"))
        self.assertEqual(document.find("forward").attrib["mode"], "nat")
        self.assertEqual(document.find("ip").attrib["address"], "172.31.254.1")

    def test_network_bridge_names_are_stable_and_kernel_safe(self):
        first = labctl.bridge_name_for_network("mikrolab-cable-example")
        self.assertEqual(first, labctl.bridge_name_for_network("mikrolab-cable-example"))
        self.assertLessEqual(len(first), 15)
        self.assertNotEqual(first, labctl.bridge_name_for_network("mikrolab-cable-other"))

    def test_live_interface_update_affects_live_and_persistent_domain(self):
        with tempfile.TemporaryDirectory() as root:
            lab = labctl.Lab(Path(root), "test:///default")
            calls = []
            lab.virsh = lambda *args, **kwargs: calls.append((args, kwargs))
            lab.update_interface(
                "client1",
                labctl.interface_xml(
                    labctl.MACS["client1:ethernet"], "mikrolab-cable-test", "e1000e", True
                ),
                live=True,
            )
            self.assertEqual(calls[0][0][0:2], ("update-device", "mikrolab-client1"))
            self.assertEqual(calls[0][0][-2:], ("--live", "--config"))

    def test_microsoft_download_host_validation(self):
        labctl.validate_microsoft_url(
            "https://software.download.prss.microsoft.com/dbazure/Win11.iso?token=test"
        )
        with self.assertRaisesRegex(labctl.LabError, "unexpected download host"):
            labctl.validate_microsoft_url("https://example.com/Win11.iso")

    def test_massgrave_mirror_host_validation(self):
        labctl.validate_massgrave_mirror_url(
            "https://tempdelivery.13376767.xyz/db/file.iso?sig=test"
        )
        with self.assertRaisesRegex(labctl.LabError, "unexpected mirror host"):
            labctl.validate_massgrave_mirror_url("https://example.com/file.iso")

    def test_local_iso_validation_rejects_partial_and_accepts_iso_signature(self):
        with tempfile.TemporaryDirectory() as root:
            partial = Path(root) / "windows.iso.part"
            partial.touch()
            with self.assertRaisesRegex(labctl.LabError, "rozszerzenie .iso"):
                labctl.validate_local_windows_iso(partial)

            image = Path(root) / "windows.iso"
            with image.open("wb") as handle:
                handle.truncate(3 * 1024**3 + 1)
                handle.seek(0x8001)
                handle.write(b"CD001")
            labctl.validate_local_windows_iso(image)

    def test_latest_cable_overwrites_an_occupied_port(self):
        cables = [
            {"id": "a", "a": "router:ether1", "b": "client1:ethernet", "color": "red"},
            {"id": "b", "a": "router:ether1", "b": "client2:ethernet", "color": "blue"},
        ]
        self.assertEqual(labctl.validate_connections(cables), [cables[1]])

    def test_rejects_unknown_port_and_color(self):
        with self.assertRaisesRegex(labctl.LabError, "Unknown endpoint"):
            labctl.validate_connections([{"a": "router:ether9", "b": "client1:ethernet"}])
        with self.assertRaisesRegex(labctl.LabError, "Unsupported cable color"):
            labctl.validate_connections([
                {"a": "router:ether1", "b": "client1:ethernet", "color": "purple"}
            ])

    def test_topology_round_trip(self):
        with tempfile.TemporaryDirectory() as root:
            lab = labctl.Lab(Path(root), "test:///default")
            lab.save_topology(labctl.DEFAULT_CONNECTIONS)
            self.assertEqual(lab.load_topology()["connections"], labctl.DEFAULT_CONNECTIONS)

    def test_applied_topology_is_authoritative(self):
        with tempfile.TemporaryDirectory() as root:
            lab = labctl.Lab(Path(root), "test:///default")
            lab.save_topology(labctl.DEFAULT_CONNECTIONS)
            self.assertFalse(lab.topology_applied())
            lab.mark_applied(labctl.DEFAULT_CONNECTIONS)
            self.assertTrue(lab.topology_applied())
            lab.save_topology([])
            self.assertFalse(lab.topology_applied())

    def test_recovery_promotion_requires_both_clients_stopped(self):
        with tempfile.TemporaryDirectory() as root:
            lab = labctl.Lab(Path(root), "test:///default")
            lab.ensure_dirs()
            (lab.runtime / "client1.qcow2").touch()
            lab.vm_state = lambda vm: "running" if vm == "client2" else "shut off"
            with self.assertRaisesRegex(labctl.LabError, "both Windows clients"):
                lab.promote_client_template("client1")

    def test_domain_uuids_are_stable(self):
        self.assertEqual(len(set(labctl.UUIDS.values())), 4)
        self.assertTrue(all(value.count("-") == 4 for value in labctl.UUIDS.values()))

    def test_process_start_time_identifies_current_process(self):
        value = labctl.process_start_time(os.getpid())
        self.assertIsNotNone(value)
        self.assertTrue(value.isdigit())
        self.assertIsNone(labctl.process_start_time(999_999_999))

    def test_generated_domain_xml_is_well_formed_and_stable(self):
        with tempfile.TemporaryDirectory() as root:
            lab = labctl.Lab(Path(root), "test:///default")
            lab.ensure_dirs()
            for vm in labctl.VM_NAMES:
                (lab.runtime / f"{vm}.qcow2").touch()
            (lab.media / "winbox-tools.iso").touch()
            assignments = labctl.network_assignments(labctl.DEFAULT_CONNECTIONS)
            for vm in labctl.VM_NAMES:
                document = ET.fromstring(lab.domain_xml(vm, assignments))
                self.assertEqual(document.findtext("uuid"), labctl.UUIDS[vm])
                machine = document.find("./os/type").attrib["machine"]
                self.assertEqual(machine, "pc" if vm == "router" else "q35")
                interfaces = document.findall("./devices/interface")
                self.assertEqual(len(interfaces), 6 if vm == "router" else 2)
                self.assertTrue(all(interface.find("model").attrib["type"] == "virtio" for interface in interfaces))
                self.assertTrue(all(interface.attrib.get("trustGuestRxFilters") == "yes" for interface in interfaces))
                if vm == "router":
                    self.assertEqual(
                        document.find("./devices/channel/target").attrib["name"],
                        "org.qemu.guest_agent.0",
                    )
                if vm != "router":
                    self.assertEqual(
                        document.find("./sysinfo/system/entry[@name='serial']").text,
                        f"CLIENT0{vm[-1]}",
                    )

            (lab.golden / "client-template.qcow2").touch()
            (lab.root / "win11.iso").touch()
            template = ET.fromstring(lab.domain_xml("template", {}))
            self.assertEqual(template.findtext("name"), "mikrolab-template")
            self.assertEqual(
                template.find("./sysinfo/system/entry[@name='serial']").text,
                "LABTEMPLATE",
            )
            firmware = {
                feature.attrib["name"]: feature.attrib["enabled"]
                for feature in template.findall("./os/firmware/feature")
            }
            self.assertEqual(firmware, {"secure-boot": "yes"})
            self.assertEqual(template.find("./os/bootmenu").attrib["enable"], "yes")
            self.assertEqual(
                [boot.attrib["dev"] for boot in template.findall("./os/boot")],
                ["hd", "cdrom"],
            )
            self.assertEqual(len(template.findall("./devices/interface")), 1)
            self.assertEqual(template.find("./devices/interface/model").attrib["type"], "e1000e")
            self.assertEqual(
                template.find("./devices/interface/source").attrib["network"],
                "mikrolab-installer",
            )


if __name__ == "__main__":
    unittest.main()
