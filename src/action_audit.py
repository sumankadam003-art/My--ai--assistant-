"""Append-only local audit sink for Neha's action engine.

Only action metadata is recorded. Arguments, handler output, credentials, and
conversation text are deliberately excluded.
"""
import json
import os
from pathlib import Path
from threading import Lock
import time


class JsonlActionAudit:
    def __init__(self, path="data/action_audit.jsonl"):
        self.path = Path(path)
        self._lock = Lock()

    def __call__(self, event):
        if not isinstance(event, dict):
            raise TypeError("Audit event must be a dictionary.")

        safe_event = {
            "timestamp": event.get("timestamp", time.time()),
            "request_id": str(event.get("request_id", ""))[:80],
            "actor": str(event.get("actor", ""))[:80],
            "action": str(event.get("action", ""))[:120],
            "status": str(event.get("status", ""))[:80],
        }

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            fd = os.open(str(self.path), flags, 0o600)
            try:
                with os.fdopen(fd, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(safe_event, ensure_ascii=True) + "\n")
                    handle.flush()
            except Exception:
                # fdopen owns the descriptor after successful construction.
                raise
