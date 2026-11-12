import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "src"))
import app_api
from action_service_factory import build_authorized_action_service
from local_owner_auth import LocalOwnerAuth
from plugin_manager import ActionPluginManager


class ActionAPIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.auth = LocalOwnerAuth(root / "owner_auth.json")
        self.auth.setup("test-owner", "a-strong-test-password")
        self.calls = []
        manager = ActionPluginManager()
        manager.register("test action", "Run a harmless test action",
                         lambda: self.calls.append("ran") or "test returned",
                         "test.execute", True, "test")
        service = build_authorized_action_service(
            manager, owner_auth=self.auth,
            environ={"NEHA_ACTION_PERMISSIONS": "test.execute"},
            audit_path=str(root / "audit.jsonl"),
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app_api.NehaAPIHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%s" % self.server.server_address[1]
        self.auth_patch = patch.object(app_api, "owner_auth", self.auth)
        self.service_patch = patch.object(app_api, "get_action_service", lambda: service)
        self.auth_patch.start()
        self.service_patch.start()
        self.addCleanup(self.service_patch.stop)
        self.addCleanup(self.auth_patch.stop)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, body=None, token=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        return response.code, json.loads(response.read().decode())

    def login(self):
        status, result = self.request("POST", "/owner/login", {
            "username": "test-owner", "password": "a-strong-test-password"
        })
        self.assertEqual(status, 200)
        return result["access_token"]

    def test_action_routes_require_owner_authentication(self):
        status, _ = self.request("GET", "/actions")
        self.assertEqual(status, 401)
        self.assertEqual(self.calls, [])

    def test_owner_can_list_approve_and_execute_once(self):
        token = self.login()
        status, listed = self.request("GET", "/actions", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(listed["actions"][0]["name"], "test action")

        status, _ = self.request("POST", "/actions/approve",
                                 {"action": "test action"}, token)
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

        status, approval = self.request("POST", "/actions/approve",
            {"action": "test action", "owner_confirmed": True}, token)
        self.assertEqual(status, 200)
        self.assertEqual(self.calls, [])

        status, result = self.request("POST", "/actions/execute",
            {"action": "test action", "approval_token": approval["approval_token"]}, token)
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "executed_unverified")
        self.assertEqual(self.calls, ["ran"])

        status, replay = self.request("POST", "/actions/execute",
            {"action": "test action", "approval_token": approval["approval_token"]}, token)
        self.assertEqual(status, 200)
        self.assertEqual(replay["status"], "approval_invalid")
        self.assertEqual(self.calls, ["ran"])

    def test_logout_revokes_owner_session(self):
        token = self.login()
        status, _ = self.request("POST", "/owner/logout", {}, token)
        self.assertEqual(status, 200)
        status, _ = self.request("GET", "/actions", token=token)
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
