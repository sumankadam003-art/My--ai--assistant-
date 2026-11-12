"""Authenticated, approval-bound execution workflow for Neha actions.

This service is framework-independent. It is not an HTTP endpoint and does not
make owner decisions from AI output. The caller must invoke request_approval
only after the owner has explicitly confirmed the displayed action details.
"""
from typing import Mapping

try:
    from .action_authorization import (
        ApprovalStore,
        AuthorizationError,
        OwnerAuthorizer,
    )
except ImportError:
    from action_authorization import (
        ApprovalStore,
        AuthorizationError,
        OwnerAuthorizer,
    )


class AuthorizedActionService:
    def __init__(
        self,
        bridge,
        *,
        owner_authorizer: OwnerAuthorizer,
        approval_store: ApprovalStore,
    ):
        if bridge is None:
            raise ValueError("An action engine bridge is required.")
        if not isinstance(owner_authorizer, OwnerAuthorizer):
            raise TypeError("A valid owner authorizer is required.")
        if not isinstance(approval_store, ApprovalStore):
            raise TypeError("A valid approval store is required.")
        self._bridge = bridge
        self._owner_authorizer = owner_authorizer
        self._approval_store = approval_store

    def _find_action(self, name):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A valid action name is required.")
        normalized = name.strip().lower()
        for item in self._bridge.list_actions():
            if item.get("name") == normalized:
                if not item.get("enabled", False):
                    raise ValueError("This action is disabled.")
                return item
        raise ValueError("This action is not registered.")

    def request_approval(self, access_token, action, arguments=None):
        """Issue a receipt after the caller has collected explicit owner consent.

        The UI/API must show the action description and exact arguments before
        calling this method. This method itself does not display a prompt.
        """
        owner = self._owner_authorizer.authenticate_owner(access_token)
        self._find_action(action)
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            raise ValueError("Action arguments must be an object.")
        if arguments:
            raise ValueError("Existing plugin actions do not accept arguments yet.")
        token = self._approval_store.issue(action, arguments, owner["id"])
        return {
            "success": True,
            "approval_token": token,
            "expires_in_seconds": self._approval_store.ttl_seconds,
            "action": action.strip().lower(),
        }

    def execute(self, access_token, action, arguments=None, approval_token=None):
        """Re-authenticate, consume the exact approval, then invoke the engine."""
        owner = self._owner_authorizer.authenticate_owner(access_token)
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping) or arguments:
            return {
                "success": False,
                "status": "invalid_arguments",
                "message": "Existing plugin actions currently accept no arguments.",
            }
        if not isinstance(approval_token, str) or not approval_token:
            return {
                "success": False,
                "status": "approval_required",
                "message": "A valid owner approval is required.",
            }
        try:
            self._find_action(action)
        except ValueError as exc:
            return {
                "success": False,
                "status": "action_unavailable",
                "message": str(exc),
            }

        consumed = self._approval_store.consume(
            approval_token, action, arguments, owner["id"]
        )
        if not consumed:
            return {
                "success": False,
                "status": "approval_invalid",
                "message": "Approval is invalid, expired, or already used.",
            }

        result = self._bridge.execute(
            action,
            actor=owner["id"],
            approved=True,
        )
        return result.to_dict() if hasattr(result, "to_dict") else result
