"""Safe construction of Neha's authenticated action service.

Permissions are opt-in: NEHA_ACTION_PERMISSIONS is an exact comma-separated
allowlist. An empty or missing value denies every action permission.
"""
import os
import re
from typing import Callable, Mapping, Optional

try:
    from .action_audit import JsonlActionAudit
    from .action_authorization import ApprovalStore, OwnerAuthorizer
    from .action_engine_bridge import ActionEngineBridge
    from .authorized_action_service import AuthorizedActionService
    from .cloud_auth import get_authenticated_user
except ImportError:  # Supports the project's src-on-PYTHONPATH layout.
    from action_audit import JsonlActionAudit
    from action_authorization import ApprovalStore, OwnerAuthorizer
    from action_engine_bridge import ActionEngineBridge
    from authorized_action_service import AuthorizedActionService
    from cloud_auth import get_authenticated_user


_PERMISSION_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*)+$"
)


class ActionServiceConfigurationError(ValueError):
    """Raised when required owner configuration is missing or malformed."""


class PermissionPolicy:
    """Exact owner-and-permission allowlist; never grants wildcard access."""

    def __init__(self, owner_user_id: str, allowed_permissions=()):
        if not isinstance(owner_user_id, str) or not owner_user_id.strip():
            raise ValueError("A configured owner user ID is required.")
        if isinstance(allowed_permissions, (str, bytes)):
            raise TypeError("Permissions must be a collection, not a string.")

        normalized = set()
        for permission in allowed_permissions:
            if not isinstance(permission, str):
                raise ValueError("Permission names must be strings.")
            value = permission.strip()
            if not _PERMISSION_PATTERN.fullmatch(value):
                raise ValueError("Invalid permission name in allowlist.")
            normalized.add(value)

        self._owner_user_id = owner_user_id.strip()
        self._allowed_permissions = frozenset(normalized)

    @classmethod
    def from_environment(cls, owner_user_id: str, environ: Mapping[str, str]):
        raw = environ.get("NEHA_ACTION_PERMISSIONS", "")
        if not isinstance(raw, str):
            raise ActionServiceConfigurationError(
                "NEHA_ACTION_PERMISSIONS must be a comma-separated string."
            )
        entries = [item.strip() for item in raw.split(",") if item.strip()]
        try:
            return cls(owner_user_id, entries)
        except (TypeError, ValueError) as exc:
            raise ActionServiceConfigurationError(
                "NEHA_ACTION_PERMISSIONS contains an invalid permission."
            ) from exc

    @property
    def allowed_permissions(self):
        return self._allowed_permissions

    def allows(self, actor: str, permission: str) -> bool:
        return (
            isinstance(actor, str)
            and isinstance(permission, str)
            and actor == self._owner_user_id
            and permission in self._allowed_permissions
        )


def build_authorized_action_service(
    plugin_manager,
    *,
    environ: Optional[Mapping[str, str]] = None,
    session_verifier: Optional[Callable] = None,
    audit_path: str = "data/action_audit.jsonl",
    approval_ttl_seconds: int = 120,
):
    """Build the service using configured owner identity and explicit grants.

    The caller must still collect explicit owner consent in its UI before
    calling request_approval. This factory does not expose HTTP endpoints.
    """
    config = os.environ if environ is None else environ
    owner_user_id = config.get("NEHA_OWNER_USER_ID", "")
    if not isinstance(owner_user_id, str) or not owner_user_id.strip():
        raise ActionServiceConfigurationError(
            "NEHA_OWNER_USER_ID is missing; action service is disabled."
        )

    policy = PermissionPolicy.from_environment(owner_user_id, config)
    verifier = session_verifier or get_authenticated_user
    owner_authorizer = OwnerAuthorizer(owner_user_id, verifier)
    audit_sink = JsonlActionAudit(audit_path)
    bridge = ActionEngineBridge(
        plugin_manager,
        permission_checker=policy.allows,
        audit_sink=audit_sink,
    )
    approval_store = ApprovalStore(ttl_seconds=approval_ttl_seconds)
    return AuthorizedActionService(
        bridge,
        owner_authorizer=owner_authorizer,
        approval_store=approval_store,
    )
