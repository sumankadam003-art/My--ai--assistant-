import unittest

from src.action_engine_bridge import ActionEngineBridge
from src.plugin_manager import ActionPluginManager


class ActionEngineBridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.plugins = ActionPluginManager()
        self.plugins.register(
            "camera",
            "Open the camera",
            lambda: self.calls.append("opened") or "Camera launch requested",
            "device.camera",
            True,
            "device",
        )
        self.bridge = ActionEngineBridge(
            self.plugins,
            permission_checker=lambda actor, permission: (
                actor == "owner" and permission == "device.camera"
            ),
        )

    def test_registration_does_not_execute_plugin(self):
        self.assertEqual(self.calls, [])
        self.assertEqual(self.bridge.list_actions()[0]["name"], "camera")

    def test_owner_approval_is_required(self):
        result = self.bridge.execute("camera", actor="owner")
        self.assertEqual(result.status, "approval_required")
        self.assertEqual(self.calls, [])

    def test_permission_is_checked(self):
        result = self.bridge.execute(
            "camera", actor="untrusted", approved=True
        )
        self.assertEqual(result.status, "permission_denied")
        self.assertEqual(self.calls, [])

    def test_approved_action_runs_through_engine(self):
        result = self.bridge.execute(
            "camera", actor="owner", approved=True
        )
        self.assertEqual(result.status, "executed_unverified")
        self.assertIsNone(result.ok)
        self.assertEqual(self.calls, ["opened"])

    def test_disabled_plugin_remains_disabled(self):
        self.plugins.disable("camera")
        bridge = ActionEngineBridge(
            self.plugins,
            permission_checker=lambda actor, permission: True,
        )
        result = bridge.execute(
            "camera", actor="owner", approved=True
        )
        self.assertEqual(result.status, "disabled")
        self.assertEqual(self.calls, [])

    def test_missing_permission_checker_is_rejected(self):
        with self.assertRaises(TypeError):
            ActionEngineBridge(self.plugins, permission_checker=None)


if __name__ == "__main__":
    unittest.main()
