import unittest

from src.action_authorization import (
    ApprovalStore,
    AuthorizationError,
    OwnerAuthorizer,
)


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class OwnerAuthorizerTests(unittest.TestCase):
    def test_accepts_configured_owner_session(self):
        auth = OwnerAuthorizer(
            "owner-123",
            lambda token: {"id": "owner-123"} if token == "valid" else None,
        )
        self.assertEqual(auth.authenticate_owner("valid")["id"], "owner-123")

    def test_rejects_non_owner_account(self):
        auth = OwnerAuthorizer(
            "owner-123", lambda token: {"id": "other-user"}
        )
        with self.assertRaises(AuthorizationError):
            auth.authenticate_owner("valid")

    def test_rejects_invalid_session(self):
        auth = OwnerAuthorizer("owner-123", lambda token: None)
        with self.assertRaises(AuthorizationError):
            auth.authenticate_owner("expired")

    def test_requires_configured_owner_and_verifier(self):
        with self.assertRaises(ValueError):
            OwnerAuthorizer("", lambda token: None)
        with self.assertRaises(TypeError):
            OwnerAuthorizer("owner-123", None)


class ApprovalStoreTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.store = ApprovalStore(ttl_seconds=30, clock=self.clock)
        self.arguments = {"app": "youtube", "mode": "open"}

    def test_approval_matches_exact_action_arguments_and_owner(self):
        token = self.store.issue("app.open", self.arguments, "owner-123")
        self.assertTrue(
            self.store.consume(token, "app.open", self.arguments, "owner-123")
        )

    def test_approval_is_single_use(self):
        token = self.store.issue("app.open", self.arguments, "owner-123")
        self.assertTrue(
            self.store.consume(token, "app.open", self.arguments, "owner-123")
        )
        self.assertFalse(
            self.store.consume(token, "app.open", self.arguments, "owner-123")
        )

    def test_wrong_action_cannot_reuse_approval(self):
        token = self.store.issue("app.open", self.arguments, "owner-123")
        self.assertFalse(
            self.store.consume(token, "files.delete", self.arguments, "owner-123")
        )

    def test_changed_arguments_cannot_reuse_approval(self):
        token = self.store.issue("app.open", self.arguments, "owner-123")
        self.assertFalse(
            self.store.consume(
                token, "app.open", {"app": "gmail", "mode": "open"}, "owner-123"
            )
        )

    def test_different_owner_cannot_use_approval(self):
        token = self.store.issue("app.open", self.arguments, "owner-123")
        self.assertFalse(
            self.store.consume(token, "app.open", self.arguments, "other-user")
        )

    def test_expired_approval_is_rejected(self):
        token = self.store.issue("app.open", self.arguments, "owner-123")
        self.clock.advance(31)
        self.assertFalse(
            self.store.consume(token, "app.open", self.arguments, "owner-123")
        )

    def test_clear_invalidates_pending_approvals(self):
        token = self.store.issue("app.open", self.arguments, "owner-123")
        self.store.clear()
        self.assertFalse(
            self.store.consume(token, "app.open", self.arguments, "owner-123")
        )

    def test_non_json_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.issue("app.open", {"bad": object()}, "owner-123")

    def test_invalid_ttl_is_rejected(self):
        with self.assertRaises(ValueError):
            ApprovalStore(ttl_seconds=0)


if __name__ == "__main__":
    unittest.main()
