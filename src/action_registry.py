"""Register Neha's existing trusted Android actions for the central engine."""
try:
    from .actions import run_action
    from .plugin_manager import ActionPluginManager
except ImportError:
    from actions import run_action
    from plugin_manager import ActionPluginManager


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


def build_default_action_manager():
    """Build the fixed built-in action registry; no action runs during setup."""
    manager = ActionPluginManager()
    for name, (command, permission) in BUILTIN_ACTIONS.items():
        manager.register(
            name=name,
            description=name.replace("_", " "),
            handler=lambda command=command: run_action(command),
            permission=permission,
            requires_approval=True,
            category="device" if permission.startswith("device.") else "apps",
        )
    return manager
