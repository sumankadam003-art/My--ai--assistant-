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
        return [
            {"name": "safe test", "description": "A safe test action", "enabled": True},
            {"name": "send_sms", "description": "Prepare SMS", "enabled": True},
        ]

    def _find_action(self, action):
        if action not in ("safe test", "send_sms"):
            raise ValueError("This action is not registered.")
        return {"name": action, "enabled": True}

    @staticmethod
    def _validate_arguments(action, arguments):
        if action == "safe test" and arguments == {}:
            return {}
        if action == "send_sms" and set(arguments) == {"recipient", "message"}:
            return arguments
        raise ValueError("Invalid arguments.")

    def request_approval(self, identity, action, arguments):
        return {"success": True, "approval_token": "single-use-token"}

    def execute(self, identity, action, arguments, approval_token):
        if approval_token != "single-use-token":
            return {"success": False, "status": "approval_invalid"}
        self.executed.append(action)
        if action in self.fail_actions:
            return {"success": False, "status": "execution_failed", "action": action}
        if action in ("safe test", "send_sms") or action in app_api.MOBILE_ACTION_URLS:
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
        app_api._pending_chat_plans.clear()
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

    def test_chat_action_plan_requires_owner_confirmation_then_executes(self):
        planned = {
            "route": "action_plan",
            "reply": "I can run the safe test.",
            "steps": [{"legacy_action": "safe test", "arguments": {}}],
        }
        with patch.object(app_api.request_orchestrator, "handle", return_value=planned):
            status, proposal = self.request("POST", "/chat", {"message": "run safe test"}, token="valid")
        self.assertEqual(status, 200)
        self.assertIn("pending_plan", proposal)
        self.assertEqual(self.service.executed, [])

        status, denied = self.request("POST", "/chat/approve", {
            "plan_id": proposal["pending_plan"]["plan_id"], "owner_confirmed": False,
        }, token="valid")
        self.assertEqual(status, 403)
        self.assertEqual(self.service.executed, [])

        status, result = self.request("POST", "/chat/approve", {
            "plan_id": proposal["pending_plan"]["plan_id"], "owner_confirmed": True,
        }, token="valid")
        self.assertEqual(status, 200)
        self.assertEqual(result["completed_steps"], 1)
        self.assertEqual(self.service.executed, ["safe test"])

    def test_chat_plan_can_be_cancelled(self):
        planned = {
            "route": "action_plan", "reply": "Proposed.",
            "steps": [{"legacy_action": "safe test", "arguments": {}}],
        }
        with patch.object(app_api.request_orchestrator, "handle", return_value=planned):
            _, proposal = self.request("POST", "/chat", {"message": "run it"}, token="valid")
        status, result = self.request("POST", "/chat/cancel", {
            "plan_id": proposal["pending_plan"]["plan_id"]
        }, token="valid")
        self.assertEqual(status, 200)
        self.assertTrue(result["cancelled"])
        status, expired = self.request("POST", "/chat/approve", {
            "plan_id": proposal["pending_plan"]["plan_id"], "owner_confirmed": True
        }, token="valid")
        self.assertEqual(status, 409)
        self.assertEqual(self.service.executed, [])

    def test_chat_multi_step_plan_executes_in_order_after_single_owner_approval(self):
        planned = {
            "route": "action_plan", "reply": "Two-step plan.",
            "steps": [
                {"legacy_action": "safe test", "arguments": {}},
                {"legacy_action": "safe test", "arguments": {}},
            ],
        }
        with patch.object(app_api.request_orchestrator, "handle", return_value=planned):
            _, proposal = self.request("POST", "/chat", {"message": "do two things"}, token="valid")
        status, result = self.request("POST", "/chat/approve", {
            "plan_id": proposal["pending_plan"]["plan_id"], "owner_confirmed": True
        }, token="valid")
        self.assertEqual(status, 200)
        self.assertEqual(result["completed_steps"], 2)
        self.assertEqual(self.service.executed, ["safe test", "safe test"])

    def test_chat_sms_plan_returns_review_payload_for_android_composer(self):
        planned = {
            "route": "action_plan", "reply": "I can prepare that SMS.",
            "steps": [{
                "legacy_action": "send_sms",
                "arguments": {"recipient": "+919876543210", "message": "Hello"},
            }],
        }
        with patch.object(app_api.request_orchestrator, "handle", return_value=planned):
            _, proposal = self.request("POST", "/chat", {"message": "text this person"}, token="valid")
        status, result = self.request("POST", "/chat/approve", {
            "plan_id": proposal["pending_plan"]["plan_id"], "owner_confirmed": True,
        }, token="valid")
        self.assertEqual(status, 200)
        self.assertEqual(result["sms_payload"], {
            "recipient": "+919876543210", "message": "Hello",
        })
        self.assertEqual(self.service.executed, ["send_sms"])

    def test_chat_sms_is_not_allowed_inside_multi_step_plan(self):
        planned = {
            "route": "action_plan", "reply": "Mixed plan.",
            "steps": [
                {"legacy_action": "safe test", "arguments": {}},
                {"legacy_action": "send_sms", "arguments": {"recipient": "+919876543210", "message": "Hello"}},
            ],
        }
        with patch.object(app_api.request_orchestrator, "handle", return_value=planned):
            status, result = self.request("POST", "/chat", {"message": "do both"}, token="valid")
        self.assertEqual(status, 400)
        self.assertEqual(self.service.executed, [])

    def test_chat_unsupported_action_returns_honest_message_without_pending_plan(self):
        with patch.object(app_api.request_orchestrator, "handle", return_value={
            "route": "unsupported",
            "reply": "That capability is not available yet.",
            "steps": [],
        }):
            status, result = self.request(
                "POST", "/chat", {"message": "Do an unsupported action"}, token="valid"
            )
        self.assertEqual(status, 200)
        self.assertEqual(result["route"], "unsupported")
        self.assertEqual(result["reply"], "That capability is not available yet.")
        self.assertNotIn("pending_plan", result)
        self.assertEqual(self.service.executed, [])

    def test_chat_clarification_does_not_create_pending_plan(self):
        with patch.object(app_api.request_orchestrator, "handle", return_value={
            "route": "clarification", "reply": "Who is the recipient?", "steps": []
        }):
            status, result = self.request("POST", "/chat", {"message": "send a message"}, token="valid")
        self.assertEqual(status, 200)
        self.assertEqual(result["reply"], "Who is the recipient?")
        self.assertNotIn("pending_plan", result)

    def test_chat_history_is_forwarded_to_orchestrator(self):
        with patch.object(app_api.request_orchestrator, "handle", return_value={
            "route": "conversation", "reply": "Hello", "steps": []
        }) as handle:
            status, result = self.request("POST", "/chat", {
                "message": "hello",
                "history": [{"role": "user", "content": "Earlier message"}],
            }, token="valid")
        self.assertEqual(status, 200)
        self.assertEqual(result["reply"], "Hello")
        self.assertEqual(handle.call_args.kwargs["history"], [
            {"role": "user", "content": "Earlier message"}
        ])
        self.assertEqual(handle.call_args.kwargs["user_id"], app_api.NEHA_CLOUD_OWNER_ID or None)

    def test_challenge_login_routes_are_available(self):
        status, challenge = self.request("POST", "/auth/challenge", {})
        self.assertEqual(status, 200)
        self.assertTrue(challenge["challenge_id"])
        status, _ = self.request("POST", "/auth/logout", {}, token="invalid")
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
