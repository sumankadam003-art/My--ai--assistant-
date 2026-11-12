import unittest
from unittest.mock import patch

from src.action_registry import BUILTIN_ACTIONS, build_default_action_manager


class BuiltinActionRegistryTests(unittest.TestCase):
    def test_registers_all_existing_builtin_actions_without_running_them(self):
        with patch("src.action_registry.run_action") as run_action:
            manager = build_default_action_manager()
        actions = manager.list_actions()
        self.assertEqual({item["name"] for item in actions}, set(BUILTIN_ACTIONS))
        self.assertTrue(all(item["enabled"] for item in actions))
        self.assertTrue(all(item["requires_approval"] for item in actions))
        run_action.assert_not_called()

    def test_permissions_match_declared_builtin_registry(self):
        manager = build_default_action_manager()
        actual = {item["name"]: item["permission"] for item in manager.list_actions()}
        expected = {name: permission for name, (_, permission) in BUILTIN_ACTIONS.items()}
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
