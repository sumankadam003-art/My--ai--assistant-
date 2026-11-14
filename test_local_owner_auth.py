import json
import tempfile
import unittest
from pathlib import Path
from src.local_owner_auth import LocalOwnerAuth, OwnerAccountError


class LocalOwnerAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "owner_auth.json"
        self.auth = LocalOwnerAuth(self.path, session_ttl_seconds=3600)

    def tearDown(self):
        self.temp.cleanup()

    def test_setup_stores_hash_not_plain_password(self):
        result = self.auth.setup("govind-owner", "correct horse battery staple")
        raw = self.path.read_text()
        self.assertNotIn("correct horse battery staple", raw)
        self.assertEqual(result["username"], "govind-owner")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_login_and_session_verification(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        login = self.auth.login("govind-owner", "correct horse battery staple")
        self.assertIsNotNone(login)
        self.assertTrue(self.auth.verify_session(login["access_token"])["id"])

    def test_challenge_is_single_use_and_session_survives_restart(self):
        import os
        from unittest.mock import patch
        self.auth.setup("govind-owner", "correct horse battery staple")
        with patch.dict(os.environ, {"NEHA_LOGIN_OFFSET": "2003"}):
            challenge = self.auth.create_challenge()
            result = self.auth.login_challenge(
                challenge["challenge_id"], str(challenge["challenge"] + 2003)
            )
            self.assertIsNotNone(result)
            token = result["access_token"]
            self.assertTrue(LocalOwnerAuth(self.path, session_ttl_seconds=None).verify_session(token))
            self.assertIsNone(self.auth.login_challenge(
                challenge["challenge_id"], str(challenge["challenge"] + 2003)
            ))
            self.assertTrue(self.auth.logout(token))
            self.assertIsNone(self.auth.verify_session(token))

    def test_challenge_expires_after_two_minutes(self):
        import os
        from unittest.mock import patch
        self.auth.setup("govind-owner", "correct horse battery staple")
        with patch.dict(os.environ, {"NEHA_LOGIN_OFFSET": "2003"}):
            with patch("src.local_owner_auth.time.monotonic", side_effect=[100.0, 221.0]):
                challenge = self.auth.create_challenge()
                self.assertIsNone(self.auth.login_challenge(
                    challenge["challenge_id"], str(challenge["challenge"] + 2003)
                ))

    def test_challenge_rejects_five_wrong_answers(self):
        import os
        from unittest.mock import patch
        self.auth.setup("govind-owner", "correct horse battery staple")
        with patch.dict(os.environ, {"NEHA_LOGIN_OFFSET": "2003"}):
            challenge = self.auth.create_challenge()
            for _ in range(5):
                self.assertIsNone(self.auth.login_challenge(challenge["challenge_id"], "1"))
            self.assertIsNone(self.auth.login_challenge(
                challenge["challenge_id"], str(challenge["challenge"] + 2003)
            ))

    def test_wrong_credentials_rejected(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        self.assertIsNone(self.auth.login("other", "correct horse battery staple"))
        self.assertIsNone(self.auth.login("govind-owner", "wrong password"))

    def test_setup_cannot_overwrite_existing_account(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        with self.assertRaises(OwnerAccountError):
            self.auth.setup("another-owner", "another correct horse battery")

    def test_logout_revokes_session(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        token = self.auth.login("govind-owner", "correct horse battery staple")["access_token"]
        self.assertTrue(self.auth.logout(token))
        self.assertIsNone(self.auth.verify_session(token))

    def test_password_and_username_validation(self):
        with self.assertRaises(OwnerAccountError):
            self.auth.setup("ab", "correct horse battery staple")
        with self.assertRaises(OwnerAccountError):
            self.auth.setup("valid-user", "short")

    def test_login_rejects_oversized_credentials(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        self.assertIsNone(self.auth.login("govind-owner", "x" * 1025))
        self.assertIsNone(self.auth.login("x" * 65, "correct horse battery staple"))

    def test_biometric_recovery_rotation_waits_for_client_confirmation(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        owner_id = self.auth.owner_id
        session = self.auth.login("govind-owner", "correct horse battery staple")["access_token"]
        recovery_secret = self.auth.begin_recovery_enrollment(session)
        self.auth.activate_recovery_enrollment(session, recovery_secret)

        first_replacement = self.auth.reset_password_with_recovery(
            recovery_secret, "a-new-strong-password"
        )
        self.assertTrue(first_replacement)
        self.assertNotEqual(first_replacement, recovery_secret)
        self.assertEqual(self.auth.owner_id, owner_id)
        self.assertIsNone(self.auth.verify_session(session))
        self.assertIsNotNone(self.auth.login("govind-owner", "a-new-strong-password"))

        # Simulate Android failing to save the first replacement: the old
        # credential must remain usable so recovery is not permanently lost.
        second_replacement = self.auth.reset_password_with_recovery(
            recovery_secret, "another-new-strong-password"
        )
        self.assertTrue(second_replacement)
        self.assertNotEqual(second_replacement, first_replacement)
        self.assertTrue(self.auth.confirm_recovery_rotation(second_replacement))

        record = json.loads(self.path.read_text())
        self.assertEqual(
            record["recovery_secret_hash"], self.auth._recovery_digest(second_replacement)
        )
        self.assertNotIn("pending_recovery_secret_hash", record)
        self.assertFalse(self.auth.confirm_recovery_rotation(first_replacement))
        self.assertFalse(self.auth.reset_password_with_recovery(
            recovery_secret, "third-new-strong-password"
        ))
        self.assertFalse(self.auth.reset_password_with_recovery(
            first_replacement, "third-new-strong-password"
        ))

        # A confirmed replacement can be used repeatedly after each confirmation.
        next_secret = self.auth.reset_password_with_recovery(
            second_replacement, "third-new-strong-password"
        )
        self.assertTrue(next_secret)
        self.assertTrue(self.auth.confirm_recovery_rotation(next_secret))
        self.assertFalse(self.auth.reset_password_with_recovery(
            second_replacement, "fourth-new-strong-password"
        ))
        self.assertIsNotNone(self.auth.login("govind-owner", "third-new-strong-password"))

    def test_wrong_recovery_secret_cannot_reset_password(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        session = self.auth.login("govind-owner", "correct horse battery staple")["access_token"]
        recovery_secret = self.auth.begin_recovery_enrollment(session)
        self.auth.activate_recovery_enrollment(session, recovery_secret)
        self.assertFalse(self.auth.reset_password_with_recovery(
            "wrong-recovery-secret-value-that-is-long-enough", "a-new-strong-password"
        ))
        self.assertIsNotNone(self.auth.login("govind-owner", "correct horse battery staple"))

    def test_recovery_enrollment_requires_valid_session_and_is_one_time(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        with self.assertRaises(OwnerAccountError):
            self.auth.begin_recovery_enrollment("invalid-session")
        session = self.auth.login("govind-owner", "correct horse battery staple")["access_token"]
        secret = self.auth.begin_recovery_enrollment(session)
        self.auth.activate_recovery_enrollment(session, secret)
        with self.assertRaises(OwnerAccountError):
            self.auth.begin_recovery_enrollment(session)

    def test_recovery_enrollment_must_be_activated_with_matching_secret(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        session = self.auth.login("govind-owner", "correct horse battery staple")["access_token"]
        self.auth.begin_recovery_enrollment(session)
        with self.assertRaises(OwnerAccountError):
            self.auth.activate_recovery_enrollment(
                session, "incorrect-recovery-secret-value-long-enough"
            )

    def test_reset_rejects_short_new_password(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        session = self.auth.login("govind-owner", "correct horse battery staple")["access_token"]
        secret = self.auth.begin_recovery_enrollment(session)
        self.auth.activate_recovery_enrollment(session, secret)
        with self.assertRaises(OwnerAccountError):
            self.auth.reset_password_with_recovery(secret, "short")


    def test_challenge_creation_is_rate_limited_across_auth_instances(self):
        import os
        from unittest.mock import patch
        self.auth.setup("govind-owner", "correct horse battery staple")
        other = LocalOwnerAuth(Path(self.temp.name) / "other-owner.json")
        with patch.dict(os.environ, {"NEHA_LOGIN_OFFSET": "2003"}):
            with patch("src.local_owner_auth._CHALLENGE_CREATION_TIMES", []):
                for _ in range(self.auth.MAX_CHALLENGES_PER_WINDOW):
                    self.auth.create_challenge()
                with self.assertRaises(OwnerAccountError):
                    other.create_challenge()

    def test_stale_record_temp_file_does_not_block_writes(self):
        self.path.with_name(self.path.name + ".tmp").write_text("stale")
        self.auth.setup("govind-owner", "correct horse battery staple")
        self.assertTrue(self.path.is_file())
        self.assertNotEqual(self.path.read_text(), "stale")

    def test_failed_session_revocation_does_not_change_password(self):
        from unittest.mock import patch
        self.auth.setup("govind-owner", "correct horse battery staple")
        token = self.auth.login("govind-owner", "correct horse battery staple")["access_token"]
        secret = self.auth.begin_recovery_enrollment(token)
        self.auth.activate_recovery_enrollment(token, secret)
        with patch.object(self.auth, "_write_sessions", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.auth.reset_password_with_recovery(secret, "a-new-strong-password")
        self.assertTrue(self.auth.verify_session(token))
        self.assertIsNotNone(self.auth.login("govind-owner", "correct horse battery staple"))
        self.assertIsNone(self.auth.login("govind-owner", "a-new-strong-password"))

if __name__ == "__main__":
    unittest.main()
