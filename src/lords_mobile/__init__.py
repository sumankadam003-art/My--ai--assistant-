"""Lords Mobile shield tracking and verified-renewal policy for Neha.

The package defines a platform-neutral coordinator. It requires a separately
implemented Android/game adapter before it can interact with Lords Mobile.
"""
from .manager import ShieldStatus, ShieldTimerManager
from .renewal import (
    ActivationAttempt, GameShieldState, RenewalConfig, RenewalResult,
    ShieldItem, ShieldRenewalCoordinator,
)
from .storage import ShieldStore
from .timer import parse_duration_text

__all__ = ["ActivationAttempt", "GameShieldState", "RenewalConfig", "RenewalResult", "ShieldItem", "ShieldRenewalCoordinator", "ShieldStatus", "ShieldTimerManager", "ShieldStore", "parse_duration_text"]
