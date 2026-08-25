import tempfile
import unittest
from pathlib import Path

from virtulab import WorkspaceError, WorkspaceStore


class WorkspaceStoreTests(unittest.TestCase):
    def make_store(self, root: str) -> WorkspaceStore:
        return WorkspaceStore(Path(root) / "virtulab.sqlite3")

    def test_default_workspace_and_catalog_include_product_profiles(self):
        with tempfile.TemporaryDirectory() as root:
            store = self.make_store(root)
            snapshot = store.snapshot("default")
            self.assertEqual(snapshot["schemaVersion"], 2)
            self.assertEqual({device["id"] for device in snapshot["devices"]}, {"router", "client1", "client2", "internet"})
            profile_ids = {profile["id"] for profile in store.catalog()["profiles"]}
            self.assertIn("tplink-sg3428", profile_ids)
            self.assertIn("virtual-printer", profile_ids)
            self.assertIn("server-rack", profile_ids)
            template_ids = {template["id"] for template in store.catalog()["templates"]}
            self.assertIn("nixos", template_ids)
            self.assertIn("rhel", template_ids)

    def test_positions_and_cable_mode_are_persisted(self):
        with tempfile.TemporaryDirectory() as root:
            store = self.make_store(root)
            updated = store.update_canvas(
                "default", [{"id": "router", "x": 320, "y": -45}], "hidden"
            )
            router = next(device for device in updated["devices"] if device["id"] == "router")
            self.assertEqual((router["x"], router["y"]), (320, -45))
            self.assertEqual(updated["workspace"]["cable_mode"], "hidden")
            self.assertEqual(updated["workspace"]["revision"], 2)

    def test_dynamic_device_add_and_remove(self):
        with tempfile.TemporaryDirectory() as root:
            store = self.make_store(root)
            added = store.add_device("default", "tplink-sg3428", 500, 100, "SW1")
            switch = next(device for device in added["devices"] if device["name"] == "SW1")
            self.assertEqual(len(switch["ports"]), 30)
            removed = store.remove_device("default", switch["id"])
            self.assertNotIn(switch["id"], {device["id"] for device in removed["devices"]})

    def test_invalid_profile_and_mode_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            store = self.make_store(root)
            with self.assertRaisesRegex(WorkspaceError, "Unknown device profile"):
                store.add_device("default", "missing", 0, 0)
            with self.assertRaisesRegex(WorkspaceError, "Unsupported cable mode"):
                store.update_canvas("default", [], "diagonal")

    def test_os_picker_and_cable_mutations_use_catalog_values(self):
        with tempfile.TemporaryDirectory() as root:
            store = self.make_store(root)
            updated = store.update_device_os("default", "client1", "nixos")
            client = next(device for device in updated["devices"] if device["id"] == "client1")
            self.assertEqual(client["os_template"], "nixos")
            with self.assertRaisesRegex(WorkspaceError, "Unknown OS template"):
                store.update_device_os("default", "client1", "made-up-os")

            connected = store.add_cable(
                "default", "default:router:ether4", "default:client1:nic2", "#12abef"
            )
            cable = next(cable for cable in connected["cables"] if cable["port_a"] == "default:router:ether4")
            self.assertEqual(cable["color"], "#12abef")
            recolored = store.update_cable_color("default", cable["id"], "purple")
            self.assertEqual(next(item for item in recolored["cables"] if item["id"] == cable["id"])["color"], "purple")
            removed = store.remove_cable("default", cable["id"])
            self.assertNotIn(cable["id"], {item["id"] for item in removed["cables"]})

    def test_hardware_configuration_scales_network_ports(self):
        with tempfile.TemporaryDirectory() as root:
            store = self.make_store(root)
            updated = store.update_device_hardware(
                "default",
                "client1",
                {"cpuType": "host-passthrough", "cpuCores": 8, "memoryMib": 16384, "diskGib": 160, "networkCards": 5, "usbPorts": 6},
            )
            client = next(device for device in updated["devices"] if device["id"] == "client1")
            self.assertEqual(client["hardware"]["cpuCores"], 8)
            self.assertEqual(len([port for port in client["ports"] if port["medium"] == "ethernet"]), 5)
            self.assertEqual(len([port for port in client["ports"] if port["medium"] == "usb"]), 6)

    def test_rack_mount_and_os_project_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            store = self.make_store(root)
            added = store.add_device("default", "server-rack", 100, 100, "RACK-A")
            rack = next(device for device in added["devices"] if device["profile_id"] == "server-rack")
            mounted = store.mount_device("default", "client1", rack["id"], 3)
            client = next(device for device in mounted["devices"] if device["id"] == "client1")
            self.assertEqual(client["hardware"]["rackId"], rack["id"])
            project = store.create_os_project(
                "PHP lab", "Debian for INF.03", "server", "hard-drive", ["linux", "inf03"], "local-iso", "/tmp/debian.iso"
            )["project"]
            self.assertEqual(project["status"], "draft")
            self.assertEqual(project["tags"], ["linux", "inf03"])


if __name__ == "__main__":
    unittest.main()
