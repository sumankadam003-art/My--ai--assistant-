"""Shield countdown tracking and reminder decisions."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .timer import parse_duration_text


@dataclass(frozen=True)
class ShieldStatus:
    expires_at: datetime
    seconds_remaining: int
    state: str
    reminder_due: bool


class ShieldTimerManager:
    """Track an observed shield expiry; never assumes an activation succeeded."""

    def __init__(self, store, warning_minutes: int = 30):
        if not isinstance(warning_minutes, int) or not 1 <= warning_minutes <= 1440:
            raise ValueError("warning_minutes must be between 1 and 1440.")
        self.store = store
        self.warning = timedelta(minutes=warning_minutes)

    @staticmethod
    def _now(now=None):
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware.")
        return current.astimezone(timezone.utc)

    def record_observation(self, timer_text: str, *, observed_at=None, source="manual") -> datetime:
        """Record a countdown read from the game screen or entered by the owner."""
        seconds = parse_duration_text(timer_text)
        now = self._now(observed_at)
        expiry = now + timedelta(seconds=seconds)
        self.store.save({
            "version": 1,
            "observed_at": now.isoformat(),
            "expires_at": expiry.isoformat(),
            "source": str(source)[:40],
            "duration_seconds": seconds,
        })
        return expiry

    def status(self, *, now=None) -> Optional[ShieldStatus]:
        saved = self.store.load()
        if saved is None:
            return None
        try:
            expiry = datetime.fromisoformat(saved["expires_at"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Saved shield expiry is invalid.") from exc
        if expiry.tzinfo is None:
            raise ValueError("Saved shield expiry must include a timezone.")
        current = self._now(now)
        remaining = max(0, int((expiry.astimezone(timezone.utc) - current).total_seconds()))
        if remaining == 0:
            state = "expired"
        elif remaining <= self.warning.total_seconds():
            state = "expiring"
        else:
            state = "active"
        return ShieldStatus(
            expires_at=expiry.astimezone(timezone.utc),
            seconds_remaining=remaining,
            state=state,
            reminder_due=state in {"expiring", "expired"},
        )
