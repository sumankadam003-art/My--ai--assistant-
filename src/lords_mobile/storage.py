"""Atomic local persistence for the shield timer (standard library only)."""
import json
import os
import tempfile
from pathlib import Path
from typing import Optional


class ShieldStoreError(RuntimeError):
    """Raised when shield state cannot be safely read or written."""


class ShieldStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self) -> Optional[dict]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ShieldStoreError("Saved shield state is unreadable.") from exc
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ShieldStoreError("Saved shield state has an unsupported format.")
        expiry = data.get("expires_at")
        if not isinstance(expiry, str) or not expiry:
            raise ShieldStoreError("Saved shield state has no valid expiry.")
        return data

    def save(self, state: dict) -> None:
        if not isinstance(state, dict) or state.get("version") != 1:
            raise ShieldStoreError("Refusing to save invalid shield state.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".shield-", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass
            os.replace(temp_name, self.path)
        except OSError as exc:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise ShieldStoreError("Could not safely save shield state.") from exc
