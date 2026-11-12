"""Local Neha owner account with PBKDF2 hashing and biometric recovery support."""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from pathlib import Path


class OwnerAccountError(ValueError):
    pass


class LocalOwnerAuth:
    ITERATIONS = 310_000
    RECOVERY_TTL_SECONDS = 300

    def __init__(self, path="data/owner_auth.json", session_ttl_seconds=3600):
        if not isinstance(session_ttl_seconds, int) or not 60 <= session_ttl_seconds <= 86400:
            raise ValueError("Session lifetime must be between 60 and 86400 seconds.")
        self.path = Path(path)
        self.session_ttl_seconds = session_ttl_seconds
        self._sessions = {}
        self._pending_recovery = {}
        self._lock = threading.RLock()

    @staticmethod
    def _validate_username(username):
        if not isinstance(username, str):
            raise OwnerAccountError("Username must be text.")
        username = username.strip()
        if not 3 <= len(username) <= 64 or any(ord(ch) < 33 or ord(ch) > 126 for ch in username):
            raise OwnerAccountError("Username must contain 3–64 printable non-space ASCII characters.")
        return username

    @staticmethod
    def _derive(password, salt, iterations):
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)

    @staticmethod
    def _recovery_digest(secret):
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def is_configured(self):
        return self.path.is_file()

    @property
    def owner_id(self):
        return self._read_record()["owner_id"]

    def _write_record(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        except Exception:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def setup(self, username, password):
        username = self._validate_username(username)
        if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
            raise OwnerAccountError("Password must contain 12 to 1024 characters.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self.path.exists():
                raise OwnerAccountError("An owner account already exists; refusing to overwrite it.")
            salt = secrets.token_bytes(16)
            record = {
                "version": 1, "owner_id": str(uuid.uuid4()), "username": username,
                "algorithm": "pbkdf2_sha256", "iterations": self.ITERATIONS,
                "salt": salt.hex(),
                "password_hash": self._derive(password, salt, self.ITERATIONS).hex(),
            }
            self._write_record(record)
        return {"owner_id": record["owner_id"], "username": username}

    def _read_record(self):
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("version") != 1 or record.get("algorithm") != "pbkdf2_sha256":
                raise ValueError
            if not isinstance(record.get("owner_id"), str) or not isinstance(record.get("username"), str):
                raise ValueError
            return record
        except (OSError, ValueError, TypeError):
            raise OwnerAccountError("Owner account is missing or unreadable.")

    def login(self, username, password):
        if (
            not isinstance(username, str)
            or not isinstance(password, str)
            or len(username) > 64
            or not 1 <= len(password) <= 1024
        ):
            return None
        record = self._read_record()
        try:
            salt, expected = bytes.fromhex(record["salt"]), bytes.fromhex(record["password_hash"])
            iterations = int(record["iterations"])
            if not 100_000 <= iterations <= 2_000_000 or len(salt) != 16 or len(expected) != 32:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise OwnerAccountError("Owner account credential record is invalid.")
        candidate = self._derive(password, salt, iterations)
        username_ok = hmac.compare_digest(username.strip(), record["username"])
        password_ok = hmac.compare_digest(candidate, expected)
        if not (username_ok and password_ok):
            return None
        token = secrets.token_urlsafe(32)
        with self._lock:
            now = time.monotonic()
            self._sessions[token] = (record["owner_id"], now + self.session_ttl_seconds)
            self._purge(now)
        return {"access_token": token, "token_type": "Bearer", "expires_in": self.session_ttl_seconds}

    def verify_session(self, token):
        if not isinstance(token, str) or not token:
            return None
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            session = self._sessions.get(token)
        if session is None:
            return None
        record = self._read_record()
        return {"id": session[0]} if hmac.compare_digest(session[0], record["owner_id"]) else None

    def begin_recovery_enrollment(self, session_token):
        session = self.verify_session(session_token)
        if not session:
            raise OwnerAccountError("A valid owner session is required.")
        secret = secrets.token_urlsafe(32)
        digest = self._recovery_digest(secret)
        with self._lock:
            record = self._read_record()
            if record.get("recovery_secret_hash"):
                raise OwnerAccountError("Biometric password recovery is already enrolled.")
            self._pending_recovery[session["id"]] = (digest, time.monotonic() + self.RECOVERY_TTL_SECONDS)
        return secret

    def activate_recovery_enrollment(self, session_token, secret):
        session = self.verify_session(session_token)
        if not session or not isinstance(secret, str) or not 32 <= len(secret) <= 128:
            raise OwnerAccountError("Invalid recovery enrollment.")
        digest = self._recovery_digest(secret)
        with self._lock:
            pending = self._pending_recovery.get(session["id"])
            if not pending or pending[1] <= time.monotonic() or not hmac.compare_digest(pending[0], digest):
                raise OwnerAccountError("Recovery enrollment expired or invalid.")
            record = self._read_record()
            if record.get("recovery_secret_hash"):
                self._pending_recovery.pop(session["id"], None)
                raise OwnerAccountError("Biometric password recovery is already enrolled.")
            record["recovery_secret_hash"] = digest
            self._write_record(record)
            self._pending_recovery.pop(session["id"], None)
        return True

    def reset_password_with_recovery(self, secret, new_password):
        if not isinstance(secret, str) or not 32 <= len(secret) <= 128:
            return False
        if not isinstance(new_password, str) or not 12 <= len(new_password) <= 1024:
            raise OwnerAccountError("Password must contain 12 to 1024 characters.")
        digest = self._recovery_digest(secret)
        with self._lock:
            record = self._read_record()
            stored = record.get("recovery_secret_hash")
            if not isinstance(stored, str) or not hmac.compare_digest(stored, digest):
                return False
            salt = secrets.token_bytes(16)
            record["salt"] = salt.hex()
            record["iterations"] = self.ITERATIONS
            record["password_hash"] = self._derive(new_password, salt, self.ITERATIONS).hex()
            # Recovery credentials are single-use: invalidate before reporting success.
            record.pop("recovery_secret_hash", None)
            self._write_record(record)
            self._sessions.clear()
            self._pending_recovery.clear()
        return True

    def logout(self, token):
        if not isinstance(token, str):
            return False
        with self._lock:
            return self._sessions.pop(token, None) is not None

    def _purge(self, now):
        for token in [key for key, (_, expiry) in self._sessions.items() if expiry <= now]:
            self._sessions.pop(token, None)
