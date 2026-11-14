from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass(frozen=True)
class ActionPlugin:
    name: str
    description: str
    handler: Callable[[], str]
    permission: str
    requires_approval: bool = True
    category: str = "general"


class ActionPluginManager:
    """
    Controlled registry for Neha's built-in actions and approved plugins.

    This manager does not load or execute arbitrary plugin files.
    """

    def __init__(self):
        self._actions: Dict[str, ActionPlugin] = {}
        self._disabled = set()

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[[], str],
        permission: str,
        requires_approval: bool = True,
        category: str = "general",
    ) -> bool:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Action name must be a non-empty string.")

        name = name.strip().lower()

        if name in self._actions:
            raise ValueError(f"Action '{name}' is already registered.")

        if not callable(handler):
            raise TypeError("Action handler must be callable.")

        if not isinstance(description, str) or not description.strip():
            raise ValueError("Action description is required.")

        if not isinstance(permission, str) or not permission.strip():
            raise ValueError("A permission declaration is required.")

        if not isinstance(requires_approval, bool):
            raise TypeError("requires_approval must be True or False.")

        self._actions[name] = ActionPlugin(
            name=name,
            description=description.strip(),
            handler=handler,
            permission=permission.strip(),
            requires_approval=requires_approval,
            category=str(category).strip() or "general",
        )

        return True

    def list_actions(self):
        return [
            {
                "name": action.name,
                "description": action.description,
                "permission": action.permission,
                "requires_approval": action.requires_approval,
                "category": action.category,
                "enabled": action.name not in self._disabled,
            }
            for action in self._actions.values()
        ]

    def get_action(self, name: str) -> Optional[ActionPlugin]:
        if not isinstance(name, str):
            return None
        return self._actions.get(name.strip().lower())

    def disable(self, name: str) -> bool:
        action = self.get_action(name)
        if action is None:
            return False
        self._disabled.add(action.name)
        return True

    def enable(self, name: str) -> bool:
        action = self.get_action(name)
        if action is None:
            return False
        self._disabled.discard(action.name)
        return True

    def execute(self, name: str, approved: bool = False) -> dict:
        action = self.get_action(name)

        if action is None:
            return {
                "ok": False,
                "status": "not_found",
                "message": "This action is not registered.",
            }

        if action.name in self._disabled:
            return {
                "ok": False,
                "status": "disabled",
                "message": "This action is currently disabled.",
            }

        if action.requires_approval and approved is not True:
            return {
                "ok": False,
                "status": "approval_required",
                "message": f"Approval required: {action.description}",
            }

        try:
            result = action.handler()
            return {
                "ok": True,
                "status": "returned",
                "message": str(result),
            }
        except Exception:
            return {
                "ok": False,
                "status": "failed",
                "message": "Action execution failed.",
            }
