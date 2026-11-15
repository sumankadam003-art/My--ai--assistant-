import unittest
from unittest.mock import patch

from src.action_registry import BUILTIN_ACTIONS, build_default_action_manager


class BuiltinActionRegistryTests(unittest.TestCase):
    def test_registers_all_existing_builtin_actions_without_running_them(self):
        with patch("src.action_registry.run_action") as run_action:
            manager = build_default_action_manager()
        actions = manager.list_actions()
        self.assertEqual({item["name"] for item in actions}, set(BUILTIN_ACTIONS))
        self.assertTrue(all(item["enabled"] for item in actions if item["name"] != "send_sms"))
        self.assertFalse(next(item for item in actions if item["name"] == "send_sms")["enabled"])
        self.assertTrue(all(item["requires_approval"] for item in actions))
        run_action.assert_not_called()

    def test_permissions_match_declared_builtin_registry(self):
        manager = build_default_action_manager()
        actual = {item["name"]: item["permission"] for item in manager.list_actions()}
        expected = {name: permission for name, (_, permission) in BUILTIN_ACTIONS.items()}
        self.assertEqual(actual, expected)

    def test_default_handlers_preserve_termux_run_action_behavior(self):
        with patch("src.action_registry.run_action", return_value="termux opened") as run_action:
            manager = build_default_action_manager()
            actions = {name: manager.get_action(name) for name in BUILTIN_ACTIONS}

            result = actions["open youtube"].handler()

        self.assertEqual(result, "termux opened")
        run_action.assert_called_once_with("open youtube")

    def test_send_sms_is_disabled_in_termux_and_mobile_handoff_is_available(self):
        manager = build_default_action_manager()
        action = manager.get_action("send_sms")
        metadata = {item["name"]: item for item in manager.list_actions()}["send_sms"]
        self.assertIsNotNone(action)
        self.assertEqual(action.permission, "device.sms")
        self.assertFalse(metadata["enabled"])
        self.assertEqual(action.handler(" +919876543210", "Hello"),
                         "Owner-approved SMS details are ready for the Android SMS composer.")

        mobile_manager = build_default_action_manager(mobile_url_launch=True)
        mobile_metadata = {item["name"]: item for item in mobile_manager.list_actions()}["send_sms"]
        self.assertTrue(mobile_metadata["enabled"])

    def test_mobile_url_handlers_do_not_call_termux_run_action(self):
        with patch("src.action_registry.run_action") as run_action:
            manager = build_default_action_manager(mobile_url_launch=True)
            actions = {name: manager.get_action(name) for name in BUILTIN_ACTIONS}

            for name in (
                "open youtube",
                "open google",
                "open gmail",
                "open maps",
                "open instagram",
            ):
                self.assertEqual(
                    actions[name].handler(),
                    "Mobile launch authorized.",
                )

        run_action.assert_not_called()


    def test_legacy_device_error_message_is_raised_as_execution_failure(self):
        with patch("src.action_registry.run_action", return_value="Volume control unavailable. Check Termux:API installation."):
            manager = build_default_action_manager()
            action = manager.get_action("volume up")
            with self.assertRaisesRegex(RuntimeError, "Volume control unavailable"):
                action.handler()

    def test_legacy_device_success_message_is_preserved(self):
        with patch("src.action_registry.run_action", return_value="Battery is at 80 percent."):
            manager = build_default_action_manager()
            action = manager.get_action("battery")
            self.assertEqual(action.handler(), "Battery is at 80 percent.")


if __name__ == "__main__":
    unittest.main()
