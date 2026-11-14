import unittest

from src.plugin_manager import ActionPluginManager


class ActionPluginManagerTests(unittest.TestCase):
    def test_successful_handler_return_is_reported_as_success(self):
        manager = ActionPluginManager()
        manager.register(
            "test.action",
            "Run a harmless test action",
            lambda: "handler returned",
            "test.permission",
            requires_approval=False,
        )

        result = manager.execute("test.action")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "returned")
        self.assertEqual(result["message"], "handler returned")

    def test_handler_failure_is_not_reported_as_success(self):
        manager = ActionPluginManager()

        def fail():
            raise RuntimeError("internal detail must not leak")

        manager.register(
            "test.failure",
            "Fail safely",
            fail,
            "test.permission",
            requires_approval=False,
        )
        result = manager.execute("test.failure")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("internal detail", result["message"])


if __name__ == "__main__":
    unittest.main()
