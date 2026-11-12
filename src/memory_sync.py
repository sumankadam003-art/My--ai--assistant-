import json
import os
import fcntl
import tempfile
from contextlib import contextmanager
from pathlib import Path

PENDING_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "pending_memories.json"
)


@contextmanager
def _pending_lock():
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(PENDING_FILE.parent, 0o700)
    if PENDING_FILE.exists():
        os.chmod(PENDING_FILE, 0o600)
    lock_path = PENDING_FILE.with_suffix(".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def load_pending():
    try:
        data = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError, TypeError):
        print("Neha: Pending memory queue is unreadable; preserving it.")
        return None

    if not isinstance(data, list):
        print("Neha: Pending memory queue has an invalid format; preserving it.")
        return None

    if not all(
        isinstance(item, dict)
        and isinstance(item.get("memory"), str)
        and item["memory"].strip()
        for item in data
    ):
        print("Neha: Pending memory queue contains invalid entries; preserving it.")
        return None

    return data


def _write_pending(items):
    temp_path = None
    try:
        PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=PENDING_FILE.name + ".",
            suffix=".tmp",
            dir=PENDING_FILE.parent,
        )
        temp_path = Path(temp_name)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            json.dump(items, temp_file, indent=2, ensure_ascii=False)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, PENDING_FILE)
        os.chmod(PENDING_FILE, 0o600)
        return True
    except (OSError, TypeError, ValueError):
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def queue_memory(memory):
    if not isinstance(memory, str):
        return False

    memory = memory.strip()
    if not memory:
        return False

    try:
        with _pending_lock():
            items = load_pending()
            if items is None:
                return False
            if any(item.get("memory") == memory for item in items):
                return True

            items.append({"memory": memory, "category": "general"})
            return _write_pending(items)
    except OSError:
        return False


def remove_pending(memory):
    try:
        with _pending_lock():
            items = load_pending()
            if items is None:
                return False
            updated = [
                item for item in items
                if item.get("memory") != memory
            ]
            if len(updated) == len(items):
                return True
            return _write_pending(updated)
    except OSError:
        return False


def save_memory_safely(memory, user_id=None, access_token=None):
    from memory import save_memory

    memory = memory.strip() if isinstance(memory, str) else ""
    if not memory:
        return "failed"

    cloud_saved = False

    if user_id and access_token:
        try:
            from cloud_memory import save_cloud_memory
            cloud_saved = save_cloud_memory(
                user_id, memory, access_token
            )
        except Exception:
            cloud_saved = False

    local_saved = save_memory(memory)

    if cloud_saved:
        return "cloud" if local_saved else "cloud_local_failed"

    if not local_saved:
        return "failed"

    return "queued" if queue_memory(memory) else "local_only"


def sync_pending_memories(user_id, access_token):
    """Upload queued memories; keep local copies after syncing."""
    if not user_id or not access_token:
        return 0

    from cloud_memory import save_cloud_memory

    synced = 0
    pending = load_pending()
    if pending is None:
        return 0

    for item in pending:
        memory = item["memory"]

        try:
            success = save_cloud_memory(
                user_id,
                memory,
                access_token,
                category=item.get("category", "general"),
            )
        except Exception:
            success = False

        if success and remove_pending(memory):
            synced += 1

    return synced

def sync_all_local_memories(user_id, access_token):
    """Upload missing local memories after successfully reading cloud memories."""
    if not user_id or not access_token:
        return 0

    try:
        from memory import _read_memories
        from cloud_memory import load_cloud_memories, save_cloud_memory
    except Exception as error:
        print(f"Neha: Cloud sync unavailable; synchronization skipped ({type(error).__name__}).")
        return 0

    # Never upload if local memory status is unknown.
    try:
        local_memories = _read_memories()
    except Exception as error:
        print(f"Neha: Local memory read failed; cloud sync skipped ({type(error).__name__}).")
        return 0
    if local_memories is None:
        print("Neha: Local memory file is unreadable; cloud sync skipped.")
        return 0

    try:
        cloud_records = load_cloud_memories(user_id, access_token)
    except Exception as error:
        print(f"Neha: Cloud memory read failed; sync skipped ({type(error).__name__}).")
        return 0

    # Never upload if cloud status is unknown.
    if cloud_records is None:
        print("Neha: Cloud memories could not be loaded; sync skipped.")
        return 0

    cloud_texts = {
        item.get("memory").strip()
        for item in cloud_records
        if isinstance(item, dict)
        and isinstance(item.get("memory"), str)
        and item["memory"].strip()
    }

    synced = 0
    for memory in local_memories:
        if not isinstance(memory, str) or not memory.strip():
            continue
        memory = memory.strip()
        if memory in cloud_texts:
            continue
        try:
            success = save_cloud_memory(user_id, memory, access_token)
        except Exception:
            success = False

        if success:
            cloud_texts.add(memory)
            synced += 1

    return synced

