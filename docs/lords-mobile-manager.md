# Neha — Lords Mobile Manager

## First milestone: shield timer foundation

This isolated package adds a local shield countdown tracker. It is deliberately
separate from Neha's chat, action registry, authentication, memory, and mobile UI.

### Included
- Strict parsing of durations such as `2d 4h 15m` and `04:15:09`.
- Local expiry calculation using timezone-aware timestamps.
- Active / expiring / expired status and a configurable reminder threshold.
- Atomic JSON persistence with restrictive file permissions where supported.
- Unit tests using only Python's standard library.

### Not included yet
- Live screen capture or OCR.
- Android notification scheduling.
- Game taps, macros, or automatic shield activation.
- Game account credentials or network/API access.

The timer must be based on a confirmed observation. Neha must not claim a shield
was renewed merely because an action was attempted. Future Android integration
must separately verify the resulting in-game shield state.

### Run tests from the repository root

```bash
python -m unittest tests.test_lords_mobile_shield -v
```

### Example use

```python
from pathlib import Path
from datetime import datetime, timezone
from src.lords_mobile import ShieldStore, ShieldTimerManager

manager = ShieldTimerManager(
    ShieldStore(Path("data/lords_mobile/shield_state.json")),
    warning_minutes=30,
)
manager.record_observation("8h 00m", observed_at=datetime.now(timezone.utc))
print(manager.status())
```
