import unittest

from src.action_authorization import ApprovalStore, AuthorizationError, OwnerAuthorizer
from src.authorized_action_service import AuthorizedActionService
from src.action_engine_bridge import ActionEngineBridge
from src.plugin_manager import ActionPluginManager


class AuthorizedActionServiceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.plugins = ActionPluginManager()
        self.plugins.register(
            "open youtube",
            "Open YouTube",
            lambda: self.calls.append("youtube") or "Launch requested",
            "app.youtube",
            True,
            "apps",
        )
        self.bridge = ActionEngineBridge(
            self.plugins,
            permission_checker=lambda actor, permission: (
                actor == "owner-1" and permission == "app.youtube"
            ),
        )
        self.auth = OwnerAuthorizer(
            "owner-1",
            lambda token: {"id": "owner-1"} if token == "valid-session" else None,
        )
        self.store = ApprovalStore(ttl_seconds=60)
        self.service = AuthorizedActionService(
            self.bridge, owner_authorizer=self.auth, approval_store=self.store
        )

    def test_requires_valid_owner_session_to_request_approval(self):
        with self.assertRaises(AuthorizationError):
            self.service.request_approval("bad-session", "open youtube")
        self.assertEqual(self.calls, [])

    def test_list_actions_requires_owner_and_returns_action_metadata(self):
        with self.assertRaises(AuthorizationError):
            self.service.list_actions("bad-session")
        actions = self.service.list_actions("valid-session")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["name"], "open youtube")
        self.assertEqual(actions[0]["description"], "Open YouTube")
        self.assertEqual(self.calls, [])

    def test_approval_request_does_not_execute_action(self):
        result = self.service.request_approval(
            "valid-session", "open youtube"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["expires_in_seconds"], 60)
        self.assertEqual(self.calls, [])

    def test_approval_token_executes_action_once(self):
        approval = self.service.request_approval(
            "valid-session", "open youtube"
        )
        result = self.service.execute(
            "valid-session", "open youtube",
            approval_token=approval["approval_token"],
        )
        self.assertEqual(result["status"], "executed_unverified")
        self.assertEqual(self.calls, ["youtube"])
        replay = self.service.execute(
            "valid-session", "open youtube",
            approval_token=approval["approval_token"],
        )
        self.assertEqual(replay["status"], "approval_invalid")
        self.assertEqual(self.calls, ["youtube"])

    def test_approval_cannot_be_used_by_other_owner(self):
        approval = self.service.request_approval(
            "valid-session", "open youtube"
        )
        other_auth = OwnerAuthorizer("other", lambda token: {"id": "other"})
        other_service = AuthorizedActionService(
            self.bridge, owner_authorizer=other_auth,
            approval_store=self.store,
        )
        result = other_service.execute(
            "valid-session", "open youtube",
            approval_token=approval["approval_token"],
        )
        self.assertEqual(result["status"], "approval_invalid")
        self.assertEqual(self.calls, [])

    def test_unsupported_arguments_are_rejected_before_approval(self):
        with self.assertRaises(ValueError):
            self.service.request_approval(
                "valid-session", "open youtube", {"url": "https://evil.invalid"}
            )
        self.assertEqual(self.calls, [])

    def test_missing_approval_does_not_execute(self):
        result = self.service.execute(
            "valid-session", "open youtube"
        )
        self.assertEqual(result["status"], "approval_required")
        self.assertEqual(self.calls, [])

    def test_non_owner_cannot_execute_even_with_approval(self):
        approval = self.service.request_approval(
            "valid-session", "open youtube"
        )
        with self.assertRaises(AuthorizationError):
            self.service.execute(
                "bad-session", "open youtube",
                approval_token=approval["approval_token"],
            )
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
