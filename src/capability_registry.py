"""Typed, application-owned metadata for Neha's trusted capabilities.

This registry describes existing actions; it does not load plugins or execute
handlers. The authorized action service remains the execution and approval
boundary. Model output may select a tool ID, but never grant permission.
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


class CapabilityError(ValueError):
    """Base error for capability lookup and argument validation."""


class UnknownCapabilityError(CapabilityError):
    """Raised when a requested capability is not registered."""


class InvalidCapabilityArguments(CapabilityError):
    """Raised when arguments do not match a registered input schema."""


@dataclass(frozen=True)
class Capability:
    tool_id: str
    legacy_action: str
    description: str
    platforms: tuple
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    permission: str
    risk: str
    requires_approval: bool
    read_only: bool
    reversible: bool
    idempotent: bool
    timeout_seconds: int


_EMPTY_INPUT = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}
_TEXT_OUTPUT = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": True,
}


def _capability(
    tool_id, legacy_action, description, permission, *,
    platforms=("android", "termux"),
    input_schema=None, read_only=False, reversible=False,
    idempotent=False, timeout_seconds=15,
):
    return Capability(
        tool_id=tool_id,
        legacy_action=legacy_action,
        description=description,
        platforms=tuple(platforms),
        input_schema=deepcopy(input_schema or _EMPTY_INPUT),
        output_schema=deepcopy(_TEXT_OUTPUT),
        permission=permission,
        risk="medium",
        requires_approval=True,
        read_only=read_only,
        reversible=reversible,
        idempotent=idempotent,
        timeout_seconds=timeout_seconds,
    )


_SMS_INPUT = {
    "type": "object",
    "properties": {
        "recipient": {"type": "string", "minLength": 7, "maxLength": 16},
        "message": {"type": "string", "minLength": 1, "maxLength": 1600},
    },
    "required": ["recipient", "message"],
    "additionalProperties": False,
}


_BUILTIN_CAPABILITIES = (
    _capability(
        "device.battery", "battery", "Read the device battery level.",
        "device.battery", read_only=True, idempotent=True,
    ),
    _capability(
        "device.volume_up", "volume up", "Increase music volume.",
        "device.volume", reversible=True,
    ),
    _capability(
        "device.volume_down", "volume down", "Decrease music volume.",
        "device.volume", reversible=True,
    ),
    _capability(
        "device.mute_music", "mute music", "Mute music volume.",
        "device.volume", reversible=True,
    ),
    _capability(
        "device.camera.open", "camera", "Open the device camera.",
        "device.camera", idempotent=True,
    ),
    _capability(
        "app.youtube.open", "open youtube", "Open YouTube.",
        "app.youtube", idempotent=True,
    ),
    _capability(
        "app.google.open", "open google", "Open Google.",
        "app.google", idempotent=True,
    ),
    _capability(
        "app.gmail.open", "open gmail", "Open Gmail.",
        "app.gmail", idempotent=True,
    ),
    _capability(
        "app.maps.open", "open maps", "Open Google Maps.",
        "app.maps", idempotent=True,
    ),
    _capability(
        "app.instagram.open", "open instagram", "Open Instagram.",
        "app.instagram", idempotent=True,
    ),
    _capability(
        "device.toast", "toast", "Display a device notification.",
        "device.notification",
    ),
    _capability(
        "device.speak", "speak", "Speak a short message using device text-to-speech.",
        "device.speech",
    ),
    _capability(
        "messaging.sms.compose", "send_sms",
        "Prepare an SMS in the Android composer for owner review.",
        "device.sms", platforms=("android",), input_schema=_SMS_INPUT,
        timeout_seconds=15,
    ),
)


class CapabilityRegistry:
    """Read-only catalogue and strict argument validator for trusted tools."""

    def __init__(self, capabilities: Optional[tuple] = None):
        items = _BUILTIN_CAPABILITIES if capabilities is None else capabilities
        self._capabilities: Dict[str, Capability] = {}
        for item in items:
            if not isinstance(item, Capability):
                raise TypeError("Every capability must be a Capability.")
            if not item.tool_id or item.tool_id in self._capabilities:
                raise ValueError("Capability tool IDs must be unique and non-empty.")
            self._capabilities[item.tool_id] = item

    def get(self, tool_id: str) -> Capability:
        if not isinstance(tool_id, str) or tool_id not in self._capabilities:
            raise UnknownCapabilityError("This capability is not registered.")
        return self._capabilities[tool_id]

    def get_by_legacy_action(self, action: str) -> Capability:
        """Resolve an existing action-service name to its stable tool metadata."""
        if isinstance(action, str):
            normalized = action.strip().lower()
            for item in self._capabilities.values():
                if item.legacy_action == normalized:
                    return item
        raise UnknownCapabilityError("This capability is not registered.")

    def list_capabilities(self):
        """Return serializable metadata without exposing executable handlers."""
        return [
            {
                "tool_id": item.tool_id,
                "legacy_action": item.legacy_action,
                "description": item.description,
                "platforms": list(item.platforms),
                "input_schema": deepcopy(item.input_schema),
                "output_schema": deepcopy(item.output_schema),
                "permission": item.permission,
                "risk": item.risk,
                "requires_approval": item.requires_approval,
                "read_only": item.read_only,
                "reversible": item.reversible,
                "idempotent": item.idempotent,
                "timeout_seconds": item.timeout_seconds,
            }
            for item in self._capabilities.values()
        ]

    def validate_arguments(self, tool_id: str, arguments: Mapping[str, Any]):
        """Validate the deliberately small JSON-schema subset used by this registry."""
        capability = self.get(tool_id)
        schema = capability.input_schema
        if not isinstance(arguments, Mapping):
            raise InvalidCapabilityArguments("Arguments must be a JSON object.")

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if schema.get("additionalProperties") is False:
            extras = set(arguments) - set(properties)
            if extras:
                raise InvalidCapabilityArguments("Unexpected argument field.")

        missing = [key for key in required if key not in arguments]
        if missing:
            raise InvalidCapabilityArguments("A required argument is missing.")

        for key, value in arguments.items():
            definition = properties.get(key)
            if definition is None:
                continue
            expected = definition.get("type")
            if expected == "string" and not isinstance(value, str):
                raise InvalidCapabilityArguments(key + " must be a string.")
            if expected == "string":
                if len(value) < definition.get("minLength", 0):
                    raise InvalidCapabilityArguments(key + " is too short.")
                if len(value) > definition.get("maxLength", 1000000):
                    raise InvalidCapabilityArguments(key + " is too long.")
        return True


DEFAULT_CAPABILITY_REGISTRY = CapabilityRegistry()
