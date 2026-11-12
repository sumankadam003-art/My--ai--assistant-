"""Neha's central, policy-enforcing action execution core.

Only trusted application code may register handlers. AI-generated text is never
treated as executable code or a shell command.
"""
from dataclasses import dataclass, field
from enum import IntEnum
from threading import RLock
from typing import Any, Callable, Dict, Mapping, Optional
import time
import uuid


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    description: str
    handler: Callable[..., Any] = field(repr=False, compare=False)
    risk: RiskLevel = RiskLevel.MEDIUM
    required_permissions: tuple = ()
    requires_approval: bool = True
    enabled: bool = True


@dataclass(frozen=True)
class ActionResult:
    ok: Optional[bool]
    status: str
    message: str
    action: Optional[str] = None
    request_id: Optional[str] = None
    verification: str = "not_performed"

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
            "action": self.action,
            "request_id": self.request_id,
            "verification": self.verification,
        }


class ActionEngine:
    """Central registry and policy gate for Neha's approved action adapters.

    permission_checker(actor, permission) must return True for every required
    permission. If permissions are required but no checker is configured,
    execution is denied (fail closed).

    approved=True is only a trusted caller's assertion. An API must not pass
    it based on an AI response; it must obtain approval from an authenticated
    owner interaction first.
    """

    def __init__(self, permission_checker=None, audit_sink=None):
        self._actions: Dict[str, ActionDefinition] = {}
        self._permission_checker = permission_checker
        self._audit_sink = audit_sink
        self._stopped = False
        self._lock = RLock()

    @property
    def stopped(self) -> bool:
        with self._lock:
            return self._stopped

    def emergency_stop(self) -> None:
        with self._lock:
            self._stopped = True

    def resume(self, *, owner_authorized: bool = False) -> bool:
        if owner_authorized is not True:
            return False
        with self._lock:
            self._stopped = False
        return True

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        *,
        risk: RiskLevel = RiskLevel.MEDIUM,
        required_permissions=(),
        requires_approval: bool = True,
    ) -> bool:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Action name must be a non-empty string.")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Action description is required.")
        if not callable(handler):
            raise TypeError("Action handler must be callable.")
        if not isinstance(risk, RiskLevel):
            raise TypeError("risk must be a RiskLevel.")
        if not isinstance(requires_approval, bool):
            raise TypeError("requires_approval must be boolean.")

        if isinstance(required_permissions, (str, bytes)):
            raise TypeError("required_permissions must be a collection of permission names.")
        permissions = tuple(required_permissions)
        if any(not isinstance(p, str) or not p.strip() for p in permissions):
            raise ValueError("Every permission must be a non-empty string.")

        key = name.strip().lower()
        definition = ActionDefinition(
            name=key,
            description=description.strip(),
            handler=handler,
            risk=risk,
            required_permissions=permissions,
            requires_approval=requires_approval,
        )
        with self._lock:
            if key in self._actions:
                raise ValueError("Action is already registered: " + key)
            self._actions[key] = definition
        return True

    def list_actions(self):
        with self._lock:
            return [
                {
                    "name": item.name,
                    "description": item.description,
                    "risk": item.risk.name.lower(),
                    "required_permissions": list(item.required_permissions),
                    "requires_approval": (
                        item.requires_approval or item.risk >= RiskLevel.MEDIUM
                    ),
                    "enabled": item.enabled,
                }
                for item in self._actions.values()
            ]

    def set_enabled(self, name: str, enabled: bool, *, owner_authorized=False) -> bool:
        if owner_authorized is not True or not isinstance(enabled, bool):
            return False
        key = name.strip().lower() if isinstance(name, str) else ""
        with self._lock:
            item = self._actions.get(key)
            if item is None:
                return False
            self._actions[key] = ActionDefinition(
                name=item.name,
                description=item.description,
                handler=item.handler,
                risk=item.risk,
                required_permissions=item.required_permissions,
                requires_approval=item.requires_approval,
                enabled=enabled,
            )
        return True

    def _audit(self, event: Mapping[str, Any]) -> None:
        if self._audit_sink is None:
            return
        try:
            self._audit_sink(dict(event))
        except Exception:
            pass

    def execute(
        self,
        name: str,
        arguments: Optional[Mapping[str, Any]] = None,
        *,
        actor: str = "unknown",
        approved: bool = False,
        request_id: Optional[str] = None,
    ) -> ActionResult:
        key = name.strip().lower() if isinstance(name, str) else ""
        request_id = request_id or str(uuid.uuid4())
        if arguments is None:
            args = {}
        elif isinstance(arguments, Mapping):
            args = dict(arguments)
        else:
            args = None

        def deny(status, message):
            result = ActionResult(False, status, message, key or None, request_id)
            self._audit({
                "timestamp": time.time(), "request_id": request_id,
                "actor": actor, "action": key, "status": status,
            })
            return result

        if not key:
            return deny("invalid_request", "A valid action name is required.")
        if args is None:
            return deny("invalid_request", "Action arguments must be an object.")
        if not isinstance(actor, str) or not actor.strip():
            return deny("invalid_request", "A valid actor is required.")

        with self._lock:
            if self._stopped:
                return deny("emergency_stopped", "Action execution is stopped.")
            definition = self._actions.get(key)

        if definition is None:
            return deny("not_found", "This action is not registered.")
        if not definition.enabled:
            return deny("disabled", "This action is disabled.")

        for permission in definition.required_permissions:
            if self._permission_checker is None:
                return deny("permission_denied", "Required permission is not authorized.")
            try:
                permitted = self._permission_checker(actor, permission) is True
            except Exception:
                permitted = False
            if not permitted:
                return deny("permission_denied", "Required permission is not authorized.")

        needs_approval = (
            definition.requires_approval or definition.risk >= RiskLevel.MEDIUM
        )
        if needs_approval and approved is not True:
            return deny("approval_required", "Owner approval is required before execution.")

        try:
            output = definition.handler(**args)
        except TypeError:
            return deny("invalid_arguments", "The action arguments were not accepted.")
        except Exception:
            return deny("execution_failed", "The action handler failed.")

        result = ActionResult(
            None, "executed_unverified", str(output), key, request_id,
            verification="not_performed",
        )
        self._audit({
            "timestamp": time.time(), "request_id": request_id,
            "actor": actor, "action": key, "status": result.status,
        })
        return result
