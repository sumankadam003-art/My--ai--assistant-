import unittest

from src.action_engine_bridge import ActionEngineBridge
from src.authorized_action_service import AuthorizedActionService
from src.plugin_manager import ActionPluginManager


class SmsArgumentValidationTests(unittest.TestCase):
    def test_normalizes_phone_number_and_preserves_message(self):
        result = AuthorizedActionService._validate_arguments(
            "send_sms",
            {"recipient": " +91 (98765) 43210 ", "message": "Hello Govind"},
        )
        self.assertEqual(result, {
            "recipient": "+919876543210",
            "message": "Hello Govind",
        })

    def test_rejects_missing_or_extra_fields(self):
        for arguments in (
            {"recipient": "+919876543210"},
            {"recipient": "+919876543210", "message": "Hi", "extra": "no"},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                AuthorizedActionService._validate_arguments("send_sms", arguments)

    def test_rejects_invalid_phone_number(self):
        for recipient in ("", "123", "0123456789", "+0123456789", "abc1234567"):
            with self.subTest(recipient=recipient), self.assertRaises(ValueError):
                AuthorizedActionService._validate_arguments(
                    "send_sms", {"recipient": recipient, "message": "Hello"}
                )

    def test_rejects_empty_oversized_or_control_character_message(self):
        invalid_messages = ("", " " * 3, "x" * 1601, "hello\x00world")
        for message in invalid_messages:
            with self.subTest(message_length=len(message)), self.assertRaises(ValueError):
                AuthorizedActionService._validate_arguments(
                    "send_sms", {"recipient": "+919876543210", "message": message}
                )

    def test_non_sms_actions_still_reject_arguments(self):
        with self.assertRaises(ValueError):
            AuthorizedActionService._validate_arguments("battery", {"unexpected": True})

    def test_bridge_forwards_validated_arguments_to_registered_handler(self):
        received = {}
        def handler(recipient, message):
            received.update(recipient=recipient, message=message)
            return "SMS adapter placeholder"

        manager = ActionPluginManager()
        manager.register(
            name="send_sms",
            description="send sms",
            handler=handler,
            permission="device.sms",
            requires_approval=True,
            category="device",
        )
        bridge = ActionEngineBridge(manager, permission_checker=lambda actor, permission: True)
        result = bridge.execute(
            "send_sms",
            arguments={"recipient": "+919876543210", "message": "Hello"},
            actor="owner",
            approved=True,
        )
        self.assertEqual(result.status, "executed_unverified")
        self.assertEqual(received, {"recipient": "+919876543210", "message": "Hello"})


if __name__ == "__main__":
    unittest.main()
