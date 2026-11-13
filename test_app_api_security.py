import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from src import app_api
from src.local_owner_auth import LocalOwnerAuth


class AppAPISecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.auth = LocalOwnerAuth(os.path.join(self.temp.name, "owner_auth.json"), session_ttl_seconds=None)
        self.auth.setup("owner-test", "a sufficiently long test password")
        self.auth_patch = patch.object(app_api, "owner_auth", self.auth)
        self.auth_patch.start()
        self.env_patch = patch.dict(os.environ, {"NEHA_LOGIN_OFFSET": "2003"})
        self.env_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app_api.NehaAPIHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.auth_patch.stop()
        self.env_patch.stop()
        self.temp.cleanup()

    def login(self):
        import httpx
        challenge = httpx.post(self.base + "/auth/challenge", timeout=3).json()
        response = httpx.post(self.base + "/auth/login", json={
            "challenge_id": challenge["challenge_id"],
            "answer": str(challenge["challenge"] + 2003),
        }, timeout=3)
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def test_chat_requires_bearer_session(self):
        import httpx
        response = httpx.post(self.base + "/chat", json={"message": "hello"}, timeout=3)
        self.assertEqual(response.status_code, 401)

    @patch("src.app_api.gateway.ask", return_value="Hello from Neha")
    def test_chat_works_with_valid_session(self, ask):
        import httpx
        token = self.login()
        response = httpx.post(self.base + "/chat", json={"message": "hello"},
                              headers={"Authorization": f"Bearer {token}"}, timeout=3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "Hello from Neha")
        ask.assert_called_once()

    def test_challenge_login_and_logout_revoke_token(self):
        import httpx
        token = self.login()
        self.assertTrue(self.auth.verify_session(token))
        response = httpx.post(self.base + "/auth/logout",
                              headers={"Authorization": f"Bearer {token}"}, timeout=3)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.auth.verify_session(token))

    def test_protected_endpoints_reject_missing_session(self):
        import httpx
        for method, path in (("GET", "/actions"), ("POST", "/memory/save"),
                             ("POST", "/memory/load"), ("POST", "/actions/approve"),
                             ("POST", "/actions/execute")):
            response = httpx.request(method, self.base + path, json={} if method == "POST" else None, timeout=3)
            self.assertEqual(response.status_code, 401, path)


if __name__ == "__main__":
    unittest.main()
