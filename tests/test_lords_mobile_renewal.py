import unittest
from datetime import datetime, timedelta, timezone

from src.lords_mobile.manager import ShieldTimerManager
from src.lords_mobile.renewal import (
    ActivationAttempt,
    GameShieldState,
    RenewalConfig,
    ShieldItem,
    ShieldRenewalCoordinator,
)


class MemoryStore:
    def __init__(self):
        self.value = None

    def save(self, value):
        self.value = value

    def load(self):
        return self.value


class FakeAdapter:
    def __init__(self, state, after=None, attempt=None):
        self.state = state
        self.after = after
        self.attempt = attempt or ActivationAttempt(True)
        self.activated = []

    def read_state(self):
        if self.after is not None and self.activated:
            return self.after
        return self.state

    def activate_shield(self, item_id):
        self.activated.append(item_id)
        return self.attempt


class ShieldRenewalTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
        self.manager = ShieldTimerManager(MemoryStore())

    def test_not_due_does_not_activate(self):
        state = GameShieldState(
            True, self.now + timedelta(hours=2),
            (ShieldItem("24h", 86400, 2),),
        )
        adapter = FakeAdapter(state)
        result = ShieldRenewalCoordinator(adapter, self.manager).run_once(now=self.now)
        self.assertEqual(result.state, "not_due")
        self.assertEqual(result.next_check_seconds, int((timedelta(hours=2) - timedelta(minutes=3)).total_seconds()))
        self.assertEqual(adapter.activated, [])

    def test_one_second_checks_are_used_inside_three_minute_review_window(self):
        state = GameShieldState(
            True, self.now + timedelta(minutes=2),
            (ShieldItem("8h", 28800, 1),),
        )
        adapter = FakeAdapter(state)
        result = ShieldRenewalCoordinator(adapter, self.manager).run_once(now=self.now)
        self.assertEqual(result.state, "activation_unverified")
        self.assertEqual(result.next_check_seconds, 1)

    def test_renews_inside_lead_window_and_verifies_expiry(self):
        old_expiry = self.now + timedelta(minutes=2)
        new_expiry = old_expiry + timedelta(hours=24)
        before = GameShieldState(True, old_expiry, (
            ShieldItem("3d", 259200, 1),
            ShieldItem("24h", 86400, 2),
        ))
        after = GameShieldState(True, new_expiry, before.inventory)
        adapter = FakeAdapter(before, after)
        result = ShieldRenewalCoordinator(adapter, self.manager).run_once(now=self.now)
        self.assertEqual(result.state, "renewed_verified")
        self.assertEqual(adapter.activated, ["24h"])
        self.assertEqual(self.manager.status(now=self.now).expires_at, new_expiry)

    def test_activates_immediately_when_no_shield_is_active(self):
        before = GameShieldState(False, None, (ShieldItem("8h", 28800, 1),))
        after = GameShieldState(True, self.now + timedelta(hours=8), before.inventory)
        adapter = FakeAdapter(before, after)
        result = ShieldRenewalCoordinator(adapter, self.manager).run_once(now=self.now)
        self.assertEqual(result.state, "renewed_verified")

    def test_no_inventory_does_not_claim_success(self):
        adapter = FakeAdapter(GameShieldState(False, None, ()))
        result = ShieldRenewalCoordinator(adapter, self.manager).run_once(now=self.now)
        self.assertEqual(result.state, "no_shield_item_available")
        self.assertIsNone(self.manager.status(now=self.now))

    def test_rejected_activation_is_not_verified(self):
        state = GameShieldState(False, None, (ShieldItem("8h", 28800, 1),))
        adapter = FakeAdapter(state, attempt=ActivationAttempt(False, "button unavailable"))
        result = ShieldRenewalCoordinator(adapter, self.manager).run_once(now=self.now)
        self.assertEqual(result.state, "activation_rejected")
        self.assertIsNone(self.manager.status(now=self.now))

    def test_unchanged_expiry_is_unverified_and_not_retried(self):
        old_expiry = self.now + timedelta(minutes=5)
        state = GameShieldState(True, old_expiry, (ShieldItem("8h", 28800, 1),))
        adapter = FakeAdapter(state, state)
        result = ShieldRenewalCoordinator(adapter, self.manager).run_once(now=self.now)
        self.assertEqual(result.state, "activation_unverified")
        self.assertEqual(len(adapter.activated), 1)

    def test_game_read_failure_fails_closed(self):
        class BrokenAdapter:
            def read_state(self):
                raise RuntimeError("unavailable")
            def activate_shield(self, item_id):
                raise AssertionError("must not activate")
        result = ShieldRenewalCoordinator(BrokenAdapter(), self.manager).run_once(now=self.now)
        self.assertEqual(result.state, "game_state_unavailable")

    def test_timezone_naive_now_is_rejected(self):
        adapter = FakeAdapter(GameShieldState(False, None, ()))
        with self.assertRaises(ValueError):
            ShieldRenewalCoordinator(adapter, self.manager).run_once(now=datetime(2026, 11, 24))

    def test_config_rejects_unsafe_values(self):
        with self.assertRaises(ValueError):
            RenewalConfig(lead_time_seconds=1)
        with self.assertRaises(ValueError):
            RenewalConfig(poll_interval_seconds=0)


if __name__ == "__main__":
    unittest.main()
