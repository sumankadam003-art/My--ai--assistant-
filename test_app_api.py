import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import app_api


class FakeActionService:
    def __init__(self):
        self.executed = []

    def list_actions(self, identity=None):
        return [{"name": "safe test", "description": "A safe test action", "enabled": True}]

    def request_approval(self, identity, action, arguments):
        return {"success": True, "approval_token": "single-use-token"}

    def execute(self, identity, action, arguments, approval_token):
        if approval_token != "single-use-token" or action != "safe test":
            return {"success": False, "status": "approval_invalid"}
        self.executed.append(action)
        return {"success": True, "status": "executed_unverified", "message": "Test action ran"}


class ActionAPIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeActionService()
        class FakeAuth:
            def verify_session(self, token):
                return {"id": "test-owner"} if token == "valid" else None
            def logout(self, token):
                return token == "valid"
            def create_challenge(self):
                return {"challenge_id": "test-challenge", "challenge": 1234, "expires_in": 120}
        self.auth_patch = patch.object(app_api, "owner_auth", FakeAuth())
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app_api.NehaAPIHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%s" % self.server.server_address[1]
        self.service_patch = patch.object(app_api, "get_action_service", lambda: self.service)
        self.service_patch.start()
        self.addCleanup(self.service_patch.stop)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, token=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(self.base + path, data=data,
                          headers=headers, method=method)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        return response.code, json.loads(response.read().decode())

    def test_actions_list_requires_login(self):
        status, _ = self.request("GET", "/actions")
        self.assertEqual(status, 401)
        status, result = self.request("GET", "/actions", token="valid")
        self.assertEqual(status, 200)
        self.assertEqual(result["actions"][0]["name"], "safe test")

    def test_action_requires_explicit_confirmation(self):
        status, _ = self.request("POST", "/actions/approve", {"action": "safe test"}, token="valid")
        self.assertEqual(status, 403)
        self.assertEqual(self.service.executed, [])

    def test_confirmed_action_executes_with_single_use_approval(self):
        status, approval = self.request("POST", "/actions/approve", {
            "action": "safe test", "arguments": {}, "owner_confirmed": True
        }, token="valid")
        self.assertEqual(status, 200)
        status, result = self.request("POST", "/actions/execute", {
            "action": "safe test", "arguments": {},
            "approval_token": approval["approval_token"]
        }, token="valid")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "executed_unverified")
        self.assertEqual(self.service.executed, ["safe test"])

    def test_challenge_login_routes_are_available(self):
        status, challenge = self.request("POST", "/auth/challenge", {})
        self.assertEqual(status, 200)
        self.assertTrue(challenge["challenge_id"])
        status, _ = self.request("POST", "/auth/logout", {}, token="invalid")
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
