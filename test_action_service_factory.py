import tempfile
import unittest
from pathlib import Path

from src.plugin_manager import ActionPluginManager
from src.action_service_factory import (
    ActionServiceConfigurationError,
    PermissionPolicy,
    build_authorized_action_service,
)


class PermissionPolicyTests(unittest.TestCase):
    def test_empty_allowlist_denies_every_permission(self):
        policy = PermissionPolicy("owner-1")
        self.assertFalse(policy.allows("owner-1", "device.volume"))

    def test_exact_permission_and_owner_are_required(self):
        policy = PermissionPolicy("owner-1", ["device.volume"])
        self.assertTrue(policy.allows("owner-1", "device.volume"))
        self.assertFalse(policy.allows("other-user", "device.volume"))
        self.assertFalse(policy.allows("owner-1", "device.camera"))
        self.assertFalse(policy.allows("owner-1", "*"))

    def test_rejects_malformed_permission_names(self):
        for value in ("*", "device.", ".volume", " device.volume ", "device.volume;device.camera"):
            if value == " device.volume ":
                # Whitespace around a single entry is intentionally normalized.
                self.assertTrue(PermissionPolicy("owner-1", [value]).allows("owner-1", "device.volume"))
            else:
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        PermissionPolicy("owner-1", [value])

    def test_environment_allowlist_is_exact(self):
        policy = PermissionPolicy.from_environment(
            "owner-1",
            {"NEHA_ACTION_PERMISSIONS": "device.volume, app.youtube"},
        )
        self.assertEqual(
            policy.allowed_permissions,
            frozenset({"device.volume", "app.youtube"}),
        )

    def test_invalid_environment_allowlist_fails_closed(self):
        with self.assertRaises(ActionServiceConfigurationError):
            PermissionPolicy.from_environment(
                "owner-1", {"NEHA_ACTION_PERMISSIONS": "device.*"}
            )


class ActionServiceFactoryTests(unittest.TestCase):
    def setUp(self):
        self.manager = ActionPluginManager()
        self.calls = []
        self.manager.register(
            "volume up", "Increase volume",
            lambda: self.calls.append("ran") or "volume changed",
            "device.volume", True, "device",
        )

    def test_missing_owner_configuration_rejects_factory(self):
        with self.assertRaises(ActionServiceConfigurationError):
            build_authorized_action_service(
                self.manager,
                environ={},
                session_verifier=lambda token: {"id": "owner-1"},
            )

    def test_factory_builds_owner_authenticated_service(self):
        with tempfile.TemporaryDirectory() as directory:
            service = build_authorized_action_service(
                self.manager,
                environ={
                    "NEHA_OWNER_USER_ID": "owner-1",
                    "NEHA_ACTION_PERMISSIONS": "device.volume",
                },
                session_verifier=lambda token: {"id": "owner-1"} if token == "valid" else None,
                audit_path=str(Path(directory) / "audit.jsonl"),
            )
            self.assertEqual(service._bridge.list_actions()[0]["name"], "volume up")
            approval = service.request_approval("valid", "volume up")
            result = service.execute(
                "valid", "volume up",
                approval_token=approval["approval_token"],
            )
            self.assertEqual(result["status"], "executed_unverified")
            self.assertEqual(self.calls, ["ran"])

    def test_empty_allowlist_denies_execution_even_after_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            service = build_authorized_action_service(
                self.manager,
                environ={"NEHA_OWNER_USER_ID": "owner-1"},
                session_verifier=lambda token: {"id": "owner-1"},
                audit_path=str(Path(directory) / "audit.jsonl"),
            )
            approval = service.request_approval("valid", "volume up")
            result = service.execute(
                "valid", "volume up",
                approval_token=approval["approval_token"],
            )
            self.assertEqual(result["status"], "permission_denied")
            self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
