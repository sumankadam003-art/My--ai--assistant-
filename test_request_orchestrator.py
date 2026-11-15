import unittest
from unittest.mock import Mock

from src.request_orchestrator import RequestOrchestrator
from src.action_brain import ActionPlanningError


class RequestOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.gateway = Mock()
        self.gateway.ask.return_value = "Conversation answer"
        self.brain = Mock()
        self.orchestrator = RequestOrchestrator(self.gateway, self.brain)

    def test_normal_conversation_uses_gateway_and_passes_history_and_user(self):
        self.brain.plan.return_value = {
            "status": "not_action", "message": "Not an action",
            "steps": [], "missing_fields": [],
        }
        history = [{"role": "user", "content": "Earlier"}]
        result = self.orchestrator.handle("Explain gravity", history, "owner-1")
        self.assertEqual(result["route"], "conversation")
        self.assertEqual(result["reply"], "Conversation answer")
        self.gateway.ask.assert_called_once_with(
            "Explain gravity", history=history, user_id="owner-1"
        )

    def test_unsupported_action_returns_honest_message_without_gateway(self):
        self.brain.plan.return_value = {
            "status": "unsupported", "message": "That capability is not available yet.",
            "steps": [], "missing_fields": [],
        }
        result = self.orchestrator.handle("Delete every file on my phone")
        self.assertEqual(result["route"], "unsupported")
        self.assertEqual(result["reply"], "That capability is not available yet.")
        self.assertEqual(result["steps"], [])
        self.gateway.ask.assert_not_called()

    def test_clarification_returns_question_without_gateway_or_execution(self):
        self.brain.plan.return_value = {
            "status": "clarification", "message": "Who is the recipient?",
            "steps": [], "missing_fields": ["recipient"],
        }
        result = self.orchestrator.handle("Send a message")
        self.assertEqual(result["route"], "clarification")
        self.assertEqual(result["steps"], [])
        self.gateway.ask.assert_not_called()

    def test_action_plan_is_returned_but_never_executed(self):
        steps = [{"tool_id": "app.youtube.open", "legacy_action": "open youtube", "arguments": {}}]
        self.brain.plan.return_value = {
            "status": "action", "message": "I can open YouTube.",
            "steps": steps, "missing_fields": [],
        }
        result = self.orchestrator.handle("Open YouTube")
        self.assertEqual(result["route"], "action_plan")
        self.assertEqual(result["steps"], steps)
        self.gateway.ask.assert_not_called()

    def test_planning_error_does_not_fall_back_to_conversation(self):
        self.brain.plan.side_effect = ActionPlanningError("provider failure")
        result = self.orchestrator.handle("Open YouTube")
        self.assertEqual(result["route"], "planning_error")
        self.assertEqual(result["steps"], [])
        self.gateway.ask.assert_not_called()

    def test_rejects_empty_or_oversized_message(self):
        with self.assertRaises(ValueError):
            self.orchestrator.handle(" ")
        with self.assertRaises(ValueError):
            self.orchestrator.handle("x" * 10_001)
        self.brain.plan.assert_not_called()

    def test_rejects_oversized_history_list(self):
        with self.assertRaises(ValueError):
            self.orchestrator.handle("Hello", history=[{}] * 41)


if __name__ == "__main__":
    unittest.main()
