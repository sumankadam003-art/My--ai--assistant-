import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

MEMORY_FILE = Path(__file__).resolve().parent.parent / "data" / "memory.json"

_THREAD_LOCK = threading.RLock()


@contextmanager
def _memory_lock():
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = MEMORY_FILE.with_suffix(".lock")

    with _THREAD_LOCK:
        with lock_path.open("a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_memories():
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            return None
        return data
    except FileNotFoundError:
        return []
    except (OSError, ValueError, TypeError):
        return None


def _write_memories(memories):
    temp_path = None
    try:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=MEMORY_FILE.parent,
            prefix=MEMORY_FILE.name + ".",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(memories, temp_file, indent=2, ensure_ascii=False)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, MEMORY_FILE)
        temp_path = None
        return True

    except (OSError, TypeError, ValueError):
        return False

    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def load_memories():
    result = _read_memories()
    return result if result is not None else []


def save_memory(fact):
    if not isinstance(fact, str):
        return False

    fact = fact.strip()
    if not fact:
        return False

    try:
        with _memory_lock():
            memories = _read_memories()
            if memories is None:
                return False
            if fact in memories:
                return True

            memories.append(fact)
            return _write_memories(memories)
    except OSError:
        return False


def delete_memory(index):
    if isinstance(index, bool) or not isinstance(index, int):
        return None

    try:
        with _memory_lock():
            memories = _read_memories()
            if memories is None or not 0 <= index < len(memories):
                return None

            removed = memories[index]
            updated = memories.copy()
            updated.pop(index)

            return removed if _write_memories(updated) else None
    except OSError:
        return None
