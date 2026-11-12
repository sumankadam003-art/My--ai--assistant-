import unittest

from src.action_engine import ActionEngine, RiskLevel


class ActionEngineTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.engine = ActionEngine(
            permission_checker=lambda actor, permission: (
                actor == "owner" and permission == "device.camera"
            )
        )
        self.engine.register(
            "camera.open",
            "Open the camera",
            lambda: self.calls.append("camera") or "Camera launch requested",
            risk=RiskLevel.MEDIUM,
            required_permissions=("device.camera",),
            requires_approval=True,
        )

    def test_unknown_action_is_rejected(self):
        result = self.engine.execute("unknown", actor="owner", approved=True)
        self.assertEqual(result.status, "not_found")
        self.assertEqual(self.calls, [])

    def test_approval_is_required_before_handler_runs(self):
        result = self.engine.execute("camera.open", actor="owner")
        self.assertEqual(result.status, "approval_required")
        self.assertEqual(self.calls, [])

    def test_permission_is_checked_before_handler_runs(self):
        result = self.engine.execute(
            "camera.open", actor="not-owner", approved=True
        )
        self.assertEqual(result.status, "permission_denied")
        self.assertEqual(self.calls, [])

    def test_approved_and_authorized_action_runs(self):
        result = self.engine.execute(
            "camera.open", actor="owner", approved=True
        )
        self.assertEqual(result.status, "executed_unverified")
        self.assertIsNone(result.ok)
        self.assertEqual(result.verification, "not_performed")
        self.assertEqual(self.calls, ["camera"])

    def test_emergency_stop_blocks_execution(self):
        self.engine.emergency_stop()
        result = self.engine.execute(
            "camera.open", actor="owner", approved=True
        )
        self.assertEqual(result.status, "emergency_stopped")
        self.assertEqual(self.calls, [])

    def test_only_owner_authorized_caller_can_resume(self):
        self.engine.emergency_stop()
        self.assertFalse(self.engine.resume(owner_authorized=False))
        self.assertTrue(self.engine.stopped)
        self.assertTrue(self.engine.resume(owner_authorized=True))
        self.assertFalse(self.engine.stopped)

    def test_disabled_action_is_rejected(self):
        self.assertTrue(
            self.engine.set_enabled(
                "camera.open", False, owner_authorized=True
            )
        )
        result = self.engine.execute(
            "camera.open", actor="owner", approved=True
        )
        self.assertEqual(result.status, "disabled")
        self.assertEqual(self.calls, [])

    def test_enable_requires_owner_authorization(self):
        self.assertFalse(
            self.engine.set_enabled("camera.open", False)
        )
        self.assertTrue(
            self.engine.set_enabled(
                "camera.open", False, owner_authorized=True
            )
        )

    def test_permission_fails_closed_without_checker(self):
        engine = ActionEngine()
        engine.register(
            "files.delete",
            "Delete a file",
            lambda: "deleted",
            risk=RiskLevel.HIGH,
            required_permissions=("files.delete",),
        )
        result = engine.execute(
            "files.delete", actor="owner", approved=True
        )
        self.assertEqual(result.status, "permission_denied")

    def test_handler_failure_is_not_reported_as_success(self):
        engine = ActionEngine()
        engine.register(
            "test.failure",
            "Test failing handler",
            lambda: 1 / 0,
            risk=RiskLevel.LOW,
            requires_approval=False,
        )
        result = engine.execute("test.failure", actor="owner")
        self.assertEqual(result.status, "execution_failed")
        self.assertFalse(result.ok)

    def test_duplicate_registration_is_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.register(
                "camera.open", "Duplicate", lambda: "no",
                risk=RiskLevel.LOW,
            )

    def test_audit_receives_action_status(self):
        events = []
        engine = ActionEngine(audit_sink=events.append)
        engine.register(
            "test.low",
            "Low-risk test",
            lambda: "ran",
            risk=RiskLevel.LOW,
            requires_approval=False,
        )
        result = engine.execute("test.low", actor="owner")
        self.assertEqual(result.status, "executed_unverified")
        self.assertEqual(events[-1]["status"], "executed_unverified")
        self.assertEqual(events[-1]["action"], "test.low")


if __name__ == "__main__":
    unittest.main()
