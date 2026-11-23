# Neha — Lords Mobile Manager

## Shield renewal engine milestone

This branch now contains a recurring renewal policy engine in addition to the
local countdown tracker. It is designed to work with a real Android/game adapter,
but no live game adapter has been implemented yet.

### Implemented
- Strict parsing of shield countdowns and timezone-aware expiry tracking.
- Configurable renewal lead time (default: 3 minutes).
- One-second checks during the final 3-minute review window; before that, the engine sleeps until the review window begins.
- Inventory selection that prefers the shortest available shield item.
- A one-attempt activation policy per check; an uncertain attempt is never blindly retried.
- Mandatory read-back verification: renewal is reported only when a fresh game
  observation confirms the shield is active and its expiry has advanced.
- A polling loop that can be hosted by an Android foreground service or another
  process supervisor.
- Atomic local timer persistence with restrictive permissions where supported.

### Still required before this can renew shields in the actual game
- An Android integration capable of reading the real Lords Mobile screen/state.
- An accessibility/UI adapter that can safely select and activate the chosen item.
- A foreground-service/worker host that Android will keep running reliably.
- Device testing for screen layouts, dialogs, loading delays, game updates, and
  background restrictions.

**This is not yet end-to-end automatic renewal.** The coordinator is the policy
and verification layer. It cannot control Lords Mobile until a real adapter is
connected. Do not rely on it for castle protection yet.

### Safety behavior
- If game state cannot be read, no activation is attempted.
- If no usable shield item is visible, no activation is attempted.
- Only one activation attempt is made per polling cycle.
- A tap or UI response is not treated as proof of renewal.
- If read-back verification fails, the result is `activation_unverified`; the
  engine does not immediately tap again and risk consuming another item.
- The engine does not access game credentials, private APIs, or modify game files.

### Configuration
The default lead time is 3 minutes and the polling interval inside that window is 1 second.
Before the review window, the coordinator schedules its next check for the exact
start of the window rather than polling continuously. Both values are configurable
through `RenewalConfig`. The engine selects the shortest
available item with a positive quantity; actual item recognition and mapping
must be supplied by the game adapter.

### Tests

```bash
python -m unittest tests.test_lords_mobile_shield tests.test_lords_mobile_renewal -v
```
