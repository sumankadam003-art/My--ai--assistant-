"""Deterministic routing between Neha conversation and Action AI planning.

This layer routes requests only. It does not execute tools or issue approvals.
"""
try:
    from .action_brain import ActionBrain, ActionPlanningError
    from .neha_gateway import NehaGateway
except ImportError:
    from action_brain import ActionBrain, ActionPlanningError
    from neha_gateway import NehaGateway


class RequestOrchestrator:
    """Route chat to the conversation gateway or the isolated action planner."""

    def __init__(self, gateway=None, action_brain=None):
        self.gateway = gateway or NehaGateway()
        self.action_brain = action_brain or ActionBrain()

    def handle(self, message, history=None, user_id=None):
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Message must be a non-empty string.")
        if len(message) > 10_000:
            raise ValueError("Message is too long.")
        if history is None:
            history = []
        if not isinstance(history, list) or len(history) > 40:
            raise ValueError("History must be a list of at most 40 messages.")

        safe_history = [
            {"role": item["role"], "content": item["content"]}
            for item in history
            if isinstance(item, dict)
            and item.get("role") in ("user", "assistant")
            and isinstance(item.get("content"), str)
            and item["content"].strip()
            and len(item["content"]) <= 10_000
        ]

        try:
            plan = self.action_brain.plan(message.strip(), history=safe_history)
        except ActionPlanningError:
            # Do not silently reinterpret a failed action-planning request as chat.
            return {
                "route": "planning_error",
                "reply": "I couldn't safely interpret that request. Please rephrase it.",
                "plan": None,
                "steps": [],
            }

        if plan["status"] == "not_action":
            reply = self.gateway.ask(
                message.strip(), history=safe_history, user_id=user_id
            )
            return {
                "route": "conversation",
                "reply": str(reply),
                "plan": None,
                "steps": [],
            }

        if plan["status"] == "unsupported":
            return {
                "route": "unsupported",
                "reply": plan["message"],
                "plan": plan,
                "steps": [],
            }

        if plan["status"] == "clarification":
            return {
                "route": "clarification",
                "reply": plan["message"],
                "plan": plan,
                "steps": [],
            }

        # Planning is deliberately separate from execution. No service, approval,
        # or handler is called here; a later phase owns that transition.
        return {
            "route": "action_plan",
            "reply": plan["message"],
            "plan": plan,
            "steps": plan["steps"],
        }
