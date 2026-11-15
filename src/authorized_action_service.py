"""Authenticated, approval-bound execution workflow for Neha actions.

The API/UI must display action details and obtain explicit owner consent before
request_approval is called. Model output is never an approval signal.
"""
from typing import Mapping
import re
try:
    from .action_authorization import ApprovalStore, AuthorizationError, OwnerAuthorizer
    from .capability_registry import (
        DEFAULT_CAPABILITY_REGISTRY, UnknownCapabilityError,
    )
except ImportError:
    from action_authorization import ApprovalStore, AuthorizationError, OwnerAuthorizer
    from capability_registry import (
        DEFAULT_CAPABILITY_REGISTRY, UnknownCapabilityError,
    )


class AuthorizedActionService:
    def __init__(self, bridge, *, owner_authorizer: OwnerAuthorizer, approval_store: ApprovalStore):
        if bridge is None:
            raise ValueError("An action engine bridge is required.")
        if not isinstance(owner_authorizer, OwnerAuthorizer):
            raise TypeError("A valid owner authorizer is required.")
        if not isinstance(approval_store, ApprovalStore):
            raise TypeError("A valid approval store is required.")
        self._bridge, self._owner_authorizer, self._approval_store = bridge, owner_authorizer, approval_store

    def list_actions(self, access_token):
        self._owner_authorizer.authenticate_owner(access_token)
        return self._bridge.list_actions()

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

    @staticmethod
    def _validate_arguments(action, arguments):
        """Validate the only currently supported parameterized action."""
        if not isinstance(arguments, Mapping):
            raise ValueError("Action arguments must be an object.")

        try:
            capability = DEFAULT_CAPABILITY_REGISTRY.get_by_legacy_action(action)
        except UnknownCapabilityError:
            # A registered handler is not executable through this service until
            # trusted capability metadata and an input schema exist for it.
            raise ValueError("This action has no trusted capability schema.")

        DEFAULT_CAPABILITY_REGISTRY.validate_arguments(
            capability.tool_id, arguments
        )
        if capability.legacy_action != "send_sms":
            return dict(arguments)

        if set(arguments) != {"recipient", "message"}:
            raise ValueError("SMS requires exactly recipient and message.")
        recipient = arguments.get("recipient")
        message = arguments.get("message")
        if not isinstance(recipient, str):
            raise ValueError("SMS recipient must be a phone number.")
        normalized = re.sub(r"[\s()\-]", "", recipient)
        if not re.fullmatch(r"\+?[1-9][0-9]{6,14}", normalized):
            raise ValueError("SMS recipient must contain 7–15 digits, with an optional leading +.")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("SMS message cannot be empty.")
        if len(message) > 1600:
            raise ValueError("SMS message cannot exceed 1600 characters.")
        if any(ord(char) < 32 and char not in "\n\t" for char in message):
            raise ValueError("SMS message contains unsupported control characters.")
        return {"recipient": normalized, "message": message}

    def request_approval(self, access_token, action, arguments=None):
        owner = self._owner_authorizer.authenticate_owner(access_token)
        item = self._find_action(action)
        if arguments is None:
            arguments = {}
        arguments = self._validate_arguments(item["name"], arguments)
        token = self._approval_store.issue(item["name"], arguments, owner["id"])
        return {"success": True, "approval_token": token,
                "expires_in_seconds": self._approval_store.ttl_seconds,
                "action": item["name"], "description": item["description"]}

    def execute(self, access_token, action, arguments=None, approval_token=None):
        owner = self._owner_authorizer.authenticate_owner(access_token)
        if arguments is None:
            arguments = {}
        try:
            arguments = self._validate_arguments(action, arguments)
        except ValueError as exc:
            return {"success": False, "status": "invalid_arguments", "message": str(exc)}
        if not isinstance(approval_token, str) or not approval_token:
            return {"success": False, "status": "approval_required",
                    "message": "A valid owner approval is required."}
        try:
            item = self._find_action(action)
        except ValueError as exc:
            return {"success": False, "status": "action_unavailable", "message": str(exc)}
        if not self._approval_store.consume(approval_token, item["name"], arguments, owner["id"]):
            return {"success": False, "status": "approval_invalid",
                    "message": "Approval is invalid, expired, or already used."}
        result = self._bridge.execute(
            item["name"], arguments=arguments, actor=owner["id"], approved=True
        )
        return result.to_dict() if hasattr(result, "to_dict") else result
