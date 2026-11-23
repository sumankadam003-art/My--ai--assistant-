"""Verified, recurring shield-renewal coordinator.

This module contains the policy engine only. A real Android/game adapter must
read the live game state, select an inventory item, and operate the UI.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class ShieldItem:
    item_id: str
    duration_seconds: int
    quantity: int

    def __post_init__(self):
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise ValueError("Shield item ID must be a non-empty string.")
        if not isinstance(self.duration_seconds, int) or self.duration_seconds <= 0:
            raise ValueError("Shield item duration must be a positive integer.")
        if not isinstance(self.quantity, int) or self.quantity < 0:
            raise ValueError("Shield item quantity cannot be negative.")


@dataclass(frozen=True)
class GameShieldState:
    shield_active: bool
    expires_at: Optional[datetime]
    inventory: Sequence[ShieldItem]


@dataclass(frozen=True)
class ActivationAttempt:
    accepted: bool
    detail: str = ""


class ShieldGameAdapter(Protocol):
    """Platform adapter contract; implementations must not fake verification."""

    def read_state(self) -> GameShieldState:
        """Read shield status, expiry, and available shield items from the game."""
        ...

    def activate_shield(self, item_id: str) -> ActivationAttempt:
        """Attempt one activation. Never report success without an actual UI result."""
        ...


@dataclass(frozen=True)
class RenewalConfig:
    lead_time_seconds: int = 3 * 60
    poll_interval_seconds: int = 1
    minimum_extension_seconds: int = 60

    def __post_init__(self):
        if not isinstance(self.lead_time_seconds, int) or not 60 <= self.lead_time_seconds <= 24 * 60 * 60:
            raise ValueError("lead_time_seconds must be between 60 and 86400.")
        if not isinstance(self.poll_interval_seconds, int) or not 1 <= self.poll_interval_seconds <= 3600:
            raise ValueError("poll_interval_seconds must be between 5 and 3600.")
        if not isinstance(self.minimum_extension_seconds, int) or self.minimum_extension_seconds < 1:
            raise ValueError("minimum_extension_seconds must be positive.")


@dataclass(frozen=True)
class RenewalResult:
    state: str
    seconds_remaining: Optional[int] = None
    selected_item_id: Optional[str] = None
    next_check_seconds: int = 1
    detail: str = ""


class ShieldRenewalCoordinator:
    """Renew before expiry, then verify by reading the game state again.

    The coordinator chooses the shortest available shield item, minimizing
    unnecessary duration use. It makes at most one activation attempt per
    check and never retries an unverified activation automatically.
    """

    def __init__(self, adapter: ShieldGameAdapter, timer_manager, config=None):
        self.adapter = adapter
        self.timer_manager = timer_manager
        self.config = config or RenewalConfig()

    @staticmethod
    def _now(value=None):
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware.")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _validate_snapshot(snapshot):
        if not isinstance(snapshot, GameShieldState):
            raise ValueError("Game adapter returned an invalid state.")
        if not isinstance(snapshot.shield_active, bool):
            raise ValueError("Game adapter returned an invalid shield status.")
        if snapshot.shield_active:
            if not isinstance(snapshot.expires_at, datetime) or snapshot.expires_at.tzinfo is None:
                raise ValueError("Active shield must include a timezone-aware expiry.")
        if not isinstance(snapshot.inventory, (list, tuple)):
            raise ValueError("Game adapter returned invalid shield inventory.")
        for item in snapshot.inventory:
            if not isinstance(item, ShieldItem):
                raise ValueError("Game adapter returned an invalid inventory item.")
        return snapshot

    @staticmethod
    def _select_item(items):
        available = [item for item in items if item.quantity > 0]
        if not available:
            return None
        # Prefer the shortest-duration item to reduce unnecessary item use.
        return min(available, key=lambda item: (item.duration_seconds, item.item_id))

    def run_once(self, *, now=None) -> RenewalResult:
        current = self._now(now)
        try:
            before = self._validate_snapshot(self.adapter.read_state())
        except Exception:
            return RenewalResult("game_state_unavailable", next_check_seconds=self.config.poll_interval_seconds)

        old_expiry = before.expires_at.astimezone(timezone.utc) if before.shield_active else None
        remaining = max(0, int((old_expiry - current).total_seconds())) if old_expiry else 0
        if before.shield_active and remaining > self.config.lead_time_seconds:
            until_due = remaining - self.config.lead_time_seconds
            return RenewalResult(
                "not_due",
                seconds_remaining=remaining,
                next_check_seconds=max(1, until_due),
            )

        item = self._select_item(before.inventory)
        if item is None:
            return RenewalResult(
                "no_shield_item_available",
                seconds_remaining=remaining,
                next_check_seconds=self.config.poll_interval_seconds,
                detail="No usable shield item was found in the observed inventory.",
            )

        try:
            attempt = self.adapter.activate_shield(item.item_id)
        except Exception:
            return RenewalResult(
                "activation_unverified",
                seconds_remaining=remaining,
                selected_item_id=item.item_id,
                next_check_seconds=self.config.poll_interval_seconds,
                detail="The activation call failed; game state must be checked before another attempt.",
            )
        if not isinstance(attempt, ActivationAttempt) or not attempt.accepted:
            return RenewalResult(
                "activation_rejected",
                seconds_remaining=remaining,
                selected_item_id=item.item_id,
                next_check_seconds=self.config.poll_interval_seconds,
                detail=(attempt.detail if isinstance(attempt, ActivationAttempt) else "Invalid activation response."),
            )

        # One fresh observation is mandatory. Never equate a tap with success.
        try:
            after = self._validate_snapshot(self.adapter.read_state())
        except Exception:
            return RenewalResult(
                "activation_unverified",
                seconds_remaining=remaining,
                selected_item_id=item.item_id,
                next_check_seconds=self.config.poll_interval_seconds,
                detail="Activation was attempted, but the resulting game state could not be read.",
            )

        new_expiry = after.expires_at.astimezone(timezone.utc) if after.shield_active else None
        minimum_expiry = (old_expiry or current) + timedelta(seconds=self.config.minimum_extension_seconds)
        if new_expiry is None or new_expiry < minimum_expiry:
            return RenewalResult(
                "activation_unverified",
                seconds_remaining=remaining,
                selected_item_id=item.item_id,
                next_check_seconds=self.config.poll_interval_seconds,
                detail="The game did not confirm a sufficiently extended active shield. No retry was attempted.",
            )

        self.timer_manager.record_expiry(new_expiry, observed_at=current, source="game_verified")
        new_remaining = max(0, int((new_expiry - current).total_seconds()))
        return RenewalResult(
            "renewed_verified",
            seconds_remaining=new_remaining,
            selected_item_id=item.item_id,
            next_check_seconds=self.config.poll_interval_seconds,
            detail="The new shield expiry was read back from the game and verified.",
        )

    def run_forever(self, stop_event: Event, *, on_result=None):
        """Poll until stopped. The host OS must keep this process/service alive."""
        if not isinstance(stop_event, Event):
            raise TypeError("stop_event must be a threading.Event.")
        while not stop_event.is_set():
            result = self.run_once()
            if on_result is not None:
                on_result(result)
            stop_event.wait(max(1, result.next_check_seconds))
