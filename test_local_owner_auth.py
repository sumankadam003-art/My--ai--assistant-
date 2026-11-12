import tempfile, unittest
from pathlib import Path
from src.local_owner_auth import LocalOwnerAuth, OwnerAccountError

class LocalOwnerAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "owner_auth.json"
        self.auth = LocalOwnerAuth(self.path, session_ttl_seconds=3600)
    def tearDown(self): self.temp.cleanup()
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
        with self.assertRaises(OwnerAccountError): self.auth.setup("ab", "correct horse battery staple")
        with self.assertRaises(OwnerAccountError): self.auth.setup("valid-user", "short")

    def test_login_rejects_oversized_credentials(self):
        self.auth.setup("govind-owner", "correct horse battery staple")
        self.assertIsNone(self.auth.login("govind-owner", "x" * 1025))
        self.assertIsNone(self.auth.login("x" * 65, "correct horse battery staple"))

if __name__ == "__main__": unittest.main()
