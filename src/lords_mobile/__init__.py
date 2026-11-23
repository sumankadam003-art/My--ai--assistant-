"""Lords Mobile companion utilities for Neha.

This package starts with local shield-time tracking. It does not inject into,
modify, or send commands to the game client.
"""
from .manager import ShieldStatus, ShieldTimerManager
from .renewal import (
    ActivationAttempt, GameShieldState, RenewalConfig, RenewalResult,
    ShieldItem, ShieldRenewalCoordinator,
)
from .storage import ShieldStore
from .timer import parse_duration_text

__all__ = ["ActivationAttempt", "GameShieldState", "RenewalConfig", "RenewalResult", "ShieldItem", "ShieldRenewalCoordinator", "ShieldStatus", "ShieldTimerManager", "ShieldStore", "parse_duration_text"]
