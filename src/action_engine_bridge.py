"""Bridge existing Neha action plugins into the central ActionEngine.

This adapter does not execute anything during registration. A caller must
supply a real permission checker and must obtain owner approval separately.
"""
from typing import Callable, Optional

try:
    from .action_engine import ActionEngine, RiskLevel
except ImportError:  # Supports the project's existing src-on-PYTHONPATH layout.
    from action_engine import ActionEngine, RiskLevel


class ActionEngineBridge:
    def __init__(
        self,
        plugin_manager,
        *,
        permission_checker: Callable[[str, str], bool],
        audit_sink=None,
    ):
        if plugin_manager is None:
            raise ValueError("An existing action plugin manager is required.")
        if not callable(permission_checker):
            raise TypeError("A permission checker is required.")

        self.plugin_manager = plugin_manager
        self.engine = ActionEngine(
            permission_checker=permission_checker,
            audit_sink=audit_sink,
        )
        self._register_existing_plugins()

    def _register_existing_plugins(self):
        # list_actions supplies stable public metadata; get_action supplies the
        # already-registered trusted Python handler. No files or model code load.
        for metadata in self.plugin_manager.list_actions():
            name = metadata["name"]
            plugin = self.plugin_manager.get_action(name)
            if plugin is None:
                raise RuntimeError(
                    "Plugin metadata changed during bridge registration: " + name
                )

            def invoke(plugin=plugin):
                return plugin.handler()

            self.engine.register(
                name=name,
                description=plugin.description,
                handler=invoke,
                risk=RiskLevel.MEDIUM,
                required_permissions=(plugin.permission,),
                requires_approval=plugin.requires_approval,
            )

            if not metadata.get("enabled", True):
                # Initial registration preserves a disabled plugin state.
                self.engine.set_enabled(
                    name, False, owner_authorized=True
                )

    def execute(
        self,
        name: str,
        *,
        actor: str,
        approved: bool = False,
    ):
        """Execute a registered plugin only after policy and approval checks.

        The caller is responsible for authenticating actor and deriving
        approved from a genuine owner confirmation, never from model output.
        """
        return self.engine.execute(
            name,
            actor=actor,
            approved=approved,
        )

    def list_actions(self):
        return self.engine.list_actions()
