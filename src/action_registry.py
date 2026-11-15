"""Register Neha's existing trusted Android actions for the central engine."""
try:
    from .actions import run_action
    from .plugin_manager import ActionPluginManager
except ImportError:
    from actions import run_action
    from plugin_manager import ActionPluginManager


_ACTION_FAILURE_PREFIXES = (
    "Volume control unavailable.",
    "Volume control timed out.",
    "Volume control failed",
    "Could not read volume information.",
    "Camera unavailable:",
    "Could not open camera.",
    "Could not open the camera.",
    "Camera launch timed out.",
    "I don't know that action yet.",
    "App '",
    "Required command '",
    "Action timed out.",
    "Received invalid data from the Android service.",
    "Action failed",
)


def _run_checked_action(command):
    """Turn known legacy failure messages into execution failures.

    The legacy Termux adapters return strings for both success and failure.
    ActionEngine otherwise treats every returned string as a completed handler.
    Until adapters expose typed outcomes, fail closed for their known error
    messages so the API cannot report these actions as completed.
    """
    result = run_action(command)
    if not isinstance(result, str) or not result.strip():
        raise RuntimeError("The device action returned no usable result.")
    lowered = result.strip().lower()
    failure_markers = (
        " failed", "failure", " unavailable", "could not ", "couldn't ",
        "not found", "isn't configured", "timed out", "invalid data",
        "error:", " error ", "don't know that action",
    )
    if result.startswith(_ACTION_FAILURE_PREFIXES) or any(
        marker in lowered for marker in failure_markers
    ):
        raise RuntimeError(result)
    return result


MOBILE_ACTION_URLS = {
    "open youtube": "https://www.youtube.com",
    "open google": "https://www.google.com",
    "open gmail": "https://mail.google.com",
    "open maps": "https://maps.google.com",
    "open instagram": "https://www.instagram.com",
}


BUILTIN_ACTIONS = {
    "battery": ("battery", "device.battery"),
    "volume up": ("volume up", "device.volume"),
    "volume down": ("volume down", "device.volume"),
    "mute music": ("mute music", "device.volume"),
    "camera": ("open camera", "device.camera"),
    "open youtube": ("open youtube", "app.youtube"),
    "open google": ("open google", "app.google"),
    "open gmail": ("open gmail", "app.gmail"),
    "open maps": ("open maps", "app.maps"),
    "open instagram": ("open instagram", "app.instagram"),
    "toast": ("toast", "device.notification"),
    "speak": ("speak", "device.speech"),
    "send_sms": ("send_sms", "device.sms"),
}


def build_default_action_manager(*, mobile_url_launch=False):
    """Build trusted actions for Termux or the authenticated mobile API."""
    if not isinstance(mobile_url_launch, bool):
        raise TypeError("mobile_url_launch must be a boolean.")

    manager = ActionPluginManager()
    for name, (command, permission) in BUILTIN_ACTIONS.items():
        if name == "send_sms":
            def handler(recipient, message):
                return "Owner-approved SMS details are ready for the Android SMS composer."
        elif mobile_url_launch and name in MOBILE_ACTION_URLS:
            handler = lambda: "Mobile launch authorized."
        else:
            handler = lambda command=command: _run_checked_action(command)

        manager.register(
            name=name,
            description=name.replace("_", " "),
            handler=handler,
            permission=permission,
            requires_approval=True,
            category="device" if permission.startswith("device.") else "apps",
        )
        if name == "send_sms" and not mobile_url_launch:
            # Termux has no Android composer. Only the authenticated mobile API
            # may authorize the handoff to the phone's SMS application.
            manager.disable(name)
    return manager
