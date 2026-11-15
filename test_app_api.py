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
        self.fail_actions = set()

    def list_actions(self, identity=None):
        return [{"name": "safe test", "description": "A safe test action", "enabled": True}]

    def request_approval(self, identity, action, arguments):
        return {"success": True, "approval_token": "single-use-token"}

    def execute(self, identity, action, arguments, approval_token):
        if approval_token != "single-use-token":
            return {"success": False, "status": "approval_invalid"}
        self.executed.append(action)
        if action in self.fail_actions:
            return {"success": False, "status": "execution_failed", "action": action}
        if action == "safe test" or action in app_api.MOBILE_ACTION_URLS:
            return {
                "success": True,
                "status": "executed_unverified",
                "action": action,
                "message": "Test action ran",
            }
        return {
            "success": False,
            "status": "action_unavailable",
            "action": action,
        }


class ActionAPIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeActionService()
        app_api._pending_chat_actions.clear()
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

    def execute_with_approval(self, action):
        status, approval = self.request("POST", "/actions/approve", {
            "action": action, "arguments": {}, "owner_confirmed": True
        }, token="valid")
        self.assertEqual(status, 200)
        return self.request("POST", "/actions/execute", {
            "action": action, "arguments": {},
            "approval_token": approval["approval_token"]
        }, token="valid")

    def test_approved_url_actions_return_fixed_launch_urls(self):
        for action, expected_url in app_api.MOBILE_ACTION_URLS.items():
            with self.subTest(action=action):
                status, result = self.execute_with_approval(action)
                self.assertEqual(status, 200)
                self.assertEqual(result["status"], "executed_unverified")
                self.assertEqual(result["launch_url"], expected_url)

    def test_ordinary_action_does_not_return_launch_url(self):
        status, result = self.execute_with_approval("safe test")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "executed_unverified")
        self.assertNotIn("launch_url", result)

    def test_failed_url_action_does_not_return_launch_url(self):
        self.service.fail_actions.add("open youtube")
        status, result = self.execute_with_approval("open youtube")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "execution_failed")
        self.assertNotIn("launch_url", result)

    def test_invalid_action_does_not_return_launch_url(self):
        status, result = self.execute_with_approval("open nonexistent")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "action_unavailable")
        self.assertNotIn("launch_url", result)

    def test_chat_action_requires_confirmation_then_executes(self):
        with patch.object(app_api, "interpret_request", return_value={"type": "action", "action": "safe test"}):
            status, proposal = self.request("POST", "/chat", {"message": "please do the safe test"}, token="valid")
        self.assertEqual(status, 200)
        self.assertIn("Should I do that?", proposal["reply"])
        self.assertEqual(self.service.executed, [])

        status, result = self.request("POST", "/chat", {"message": "yes"}, token="valid")
        self.assertEqual(status, 200)
        self.assertEqual(self.service.executed, ["safe test"])
        self.assertIn("was launched", result["reply"])

    def test_chat_action_can_be_cancelled_without_execution(self):
        with patch.object(app_api, "interpret_request", return_value={"type": "action", "action": "safe test"}):
            self.request("POST", "/chat", {"message": "do the safe test"}, token="valid")
        status, result = self.request("POST", "/chat", {"message": "no"}, token="valid")
        self.assertEqual(status, 200)
        self.assertIn("cancelled", result["reply"])
        self.assertEqual(self.service.executed, [])

    def test_chat_history_is_forwarded_to_gateway(self):
        with patch.object(app_api, "interpret_request", return_value={"type": "chat"}), patch.object(
            app_api.gateway, "ask", return_value="Hello"
        ) as ask:
            status, result = self.request("POST", "/chat", {
                "message": "hello",
                "history": [{"role": "user", "content": "Earlier message"}],
            }, token="valid")
        self.assertEqual(status, 200)
        self.assertEqual(result["reply"], "Hello")
        self.assertEqual(ask.call_args.kwargs["history"], [
            {"role": "user", "content": "Earlier message"}
        ])

    def test_challenge_login_routes_are_available(self):
        status, challenge = self.request("POST", "/auth/challenge", {})
        self.assertEqual(status, 200)
        self.assertTrue(challenge["challenge_id"])
        status, _ = self.request("POST", "/auth/logout", {}, token="invalid")
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
