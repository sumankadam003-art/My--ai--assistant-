import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from src.app_api import NehaAPIHandler


class AppAPISecurityTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), NehaAPIHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_chat_rejects_missing_authorization(self):
        import httpx
        response = httpx.post(
            self.base + "/chat",
            json={"message": "hello"},
            timeout=3,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Authentication required")

    @patch("src.app_api.get_authenticated_user", return_value=None)
    def test_chat_rejects_invalid_token(self, _mock_user):
        import httpx
        response = httpx.post(
            self.base + "/chat",
            json={"message": "hello"},
            headers={"Authorization": "Bearer invalid"},
            timeout=3,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Invalid or expired session")


if __name__ == "__main__":
    unittest.main()
