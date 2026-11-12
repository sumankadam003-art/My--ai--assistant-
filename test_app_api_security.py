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

    @patch("src.app_api.gateway.ask", return_value="Hello from Neha")
    def test_chat_works_without_user_authentication(self, ask):
        import httpx
        response = httpx.post(self.base + "/chat", json={"message": "hello"}, timeout=3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "Hello from Neha")
        ask.assert_called_once()

    def test_user_authentication_routes_are_not_exposed(self):
        import httpx
        for path in ("/auth/signup", "/auth/login", "/owner/login", "/owner/logout"):
            response = httpx.post(self.base + path, json={}, timeout=3)
            self.assertEqual(response.status_code, 404, path)

    def test_chat_still_validates_message(self):
        import httpx
        response = httpx.post(self.base + "/chat", json={"message": " "}, timeout=3)
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
