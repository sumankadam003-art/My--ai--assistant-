"""Parse human-readable shield countdowns into seconds."""
import re

_DURATION_TOKEN = re.compile(r"(\d+)\s*([dhms])", re.IGNORECASE)
_CLOCK_TOKEN = re.compile(r"^(\d{1,3}):(\d{2}):(\d{2})$")


class TimerParseError(ValueError):
    """Raised when shield timer text cannot be parsed safely."""


def parse_duration_text(text: str) -> int:
    """Parse strings such as '2d 04h 15m' or '04:15:09'.

    Clock format is strictly HH:MM:SS. We reject partial/ambiguous values
    rather than guessing what a game screen meant.
    """
    if not isinstance(text, str) or not text.strip():
        raise TimerParseError("Timer text is empty.")

    value = text.strip().lower()
    clock = _CLOCK_TOKEN.fullmatch(value)
    if clock:
        hours, minutes, seconds = map(int, clock.groups())
        if minutes > 59 or seconds > 59:
            raise TimerParseError("Clock minutes and seconds must be below 60.")
        total = hours * 3600 + minutes * 60 + seconds
    else:
        matches = list(_DURATION_TOKEN.finditer(value))
        if not matches:
            raise TimerParseError("No recognised d/h/m/s duration was found.")
        residue = _DURATION_TOKEN.sub("", value)
        residue = re.sub(r"[\s,;|]+", "", residue)
        if residue:
            raise TimerParseError("Timer contains unrecognised characters.")
        units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        seen = set()
        total = 0
        for match in matches:
            amount = int(match.group(1))
            unit = match.group(2).lower()
            if unit in seen:
                raise TimerParseError("A duration unit was repeated.")
            seen.add(unit)
            total += amount * units[unit]

    if total <= 0 or total > 366 * 86400:
        raise TimerParseError("Timer duration is outside the accepted range.")
    return total
