"""Register Neha's existing trusted Android actions for the central engine."""
try:
    from .actions import run_action
    from .plugin_manager import ActionPluginManager
except ImportError:
    from actions import run_action
    from plugin_manager import ActionPluginManager


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
}


def build_default_action_manager(*, mobile_url_launch=False):
    """Build trusted actions for Termux or the authenticated mobile API."""
    if not isinstance(mobile_url_launch, bool):
        raise TypeError("mobile_url_launch must be a boolean.")

    manager = ActionPluginManager()
    for name, (command, permission) in BUILTIN_ACTIONS.items():
        if mobile_url_launch and name in MOBILE_ACTION_URLS:
            handler = lambda: "Mobile launch authorized."
        else:
            handler = lambda command=command: run_action(command)

        manager.register(
            name=name,
            description=name.replace("_", " "),
            handler=handler,
            permission=permission,
            requires_approval=True,
            category="device" if permission.startswith("device.") else "apps",
        )
    return manager
