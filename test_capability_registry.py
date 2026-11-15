import unittest

from src.capability_registry import (
    CapabilityRegistry,
    InvalidCapabilityArguments,
    UnknownCapabilityError,
)


class CapabilityRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = CapabilityRegistry()

    def test_catalogue_contains_all_thirteen_existing_actions(self):
        items = self.registry.list_capabilities()
        self.assertEqual(len(items), 13)
        self.assertEqual(
            {item["legacy_action"] for item in items},
            {
                "battery", "volume up", "volume down", "mute music", "camera",
                "open youtube", "open google", "open gmail", "open maps",
                "open instagram", "toast", "speak", "send_sms",
            },
        )

    def test_tool_ids_are_stable_and_unique(self):
        items = self.registry.list_capabilities()
        ids = [item["tool_id"] for item in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            self.registry.get("app.youtube.open").legacy_action,
            "open youtube",
        )

    def test_unknown_tool_is_rejected(self):
        with self.assertRaises(UnknownCapabilityError):
            self.registry.get("device.run_shell")

    def test_non_parameterized_action_accepts_only_empty_object(self):
        self.assertTrue(self.registry.validate_arguments("device.battery", {}))
        with self.assertRaises(InvalidCapabilityArguments):
            self.registry.validate_arguments(
                "device.battery", {"command": "termux-battery-status"}
            )

    def test_sms_requires_recipient_and_message(self):
        with self.assertRaises(InvalidCapabilityArguments):
            self.registry.validate_arguments(
                "messaging.sms.compose", {"recipient": "+919876543210"}
            )

    def test_sms_accepts_valid_basic_arguments(self):
        self.assertTrue(self.registry.validate_arguments(
            "messaging.sms.compose",
            {"recipient": "+919876543210", "message": "Hello"},
        ))

    def test_sms_rejects_wrong_types_and_extra_fields(self):
        with self.assertRaises(InvalidCapabilityArguments):
            self.registry.validate_arguments(
                "messaging.sms.compose",
                {"recipient": 9876543210, "message": "Hello"},
            )
        with self.assertRaises(InvalidCapabilityArguments):
            self.registry.validate_arguments(
                "messaging.sms.compose",
                {
                    "recipient": "+919876543210",
                    "message": "Hello",
                    "send_now": True,
                },
            )

    def test_sms_message_length_is_bounded(self):
        with self.assertRaises(InvalidCapabilityArguments):
            self.registry.validate_arguments(
                "messaging.sms.compose",
                {"recipient": "+919876543210", "message": "x" * 1601},
            )

    def test_every_capability_keeps_approval_and_permission_metadata(self):
        for item in self.registry.list_capabilities():
            with self.subTest(tool_id=item["tool_id"]):
                self.assertTrue(item["requires_approval"])
                self.assertTrue(item["permission"])
                self.assertEqual(item["risk"], "medium")
                self.assertGreater(item["timeout_seconds"], 0)

    def test_sms_is_android_only_and_battery_is_read_only(self):
        sms = self.registry.get("messaging.sms.compose")
        battery = self.registry.get("device.battery")
        self.assertEqual(sms.platforms, ("android",))
        self.assertTrue(battery.read_only)

    def test_returned_metadata_cannot_mutate_registry_schema(self):
        metadata = self.registry.list_capabilities()
        metadata[-1]["input_schema"]["properties"]["message"]["maxLength"] = 1
        self.assertEqual(
            self.registry.get("messaging.sms.compose")
            .input_schema["properties"]["message"]["maxLength"],
            1600,
        )


if __name__ == "__main__":
    unittest.main()
