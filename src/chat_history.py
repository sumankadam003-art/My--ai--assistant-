import json
import os
from pathlib import Path

HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "conversation_history.json"
MAX_MESSAGES = 40

def load_history():
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return [
            item for item in data[-MAX_MESSAGES:]
            if isinstance(item, dict)
            and item.get("role") in ("user", "assistant")
            and isinstance(item.get("content"), str)
        ]
    except (OSError, ValueError, TypeError):
        return []

def save_history(history):
    temp = None
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = HISTORY_FILE.with_suffix(".tmp")
        temp.write_text(
            json.dumps(history[-MAX_MESSAGES:], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp, HISTORY_FILE)
        return True
    except (OSError, TypeError, ValueError):
        if temp is not None:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        return False
