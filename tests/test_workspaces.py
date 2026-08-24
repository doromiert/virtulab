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
            self.assertEqual(snapshot["schemaVersion"], 1)
            self.assertEqual({device["id"] for device in snapshot["devices"]}, {"router", "client1", "client2", "internet"})
            profile_ids = {profile["id"] for profile in store.catalog()["profiles"]}
            self.assertIn("tplink-sg3428", profile_ids)
            self.assertIn("virtual-printer", profile_ids)
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


if __name__ == "__main__":
    unittest.main()
