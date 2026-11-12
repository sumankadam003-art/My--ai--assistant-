"""Owner identity and one-time action approval primitives for Neha.

This module does not expose an HTTP endpoint. The API layer must authenticate
the bearer token with Supabase, call OwnerAuthorizer, then issue/consume an
approval through ApprovalStore. Never derive approval from model output.
"""
from dataclasses import dataclass
import hashlib
import json
import secrets
import threading
import time
from typing import Callable, Mapping, Optional


class AuthorizationError(Exception):
    """Raised when an account is not authorized as Neha's owner."""


class OwnerAuthorizer:
    def __init__(
        self,
        owner_user_id: str,
        session_verifier: Callable[[str], Optional[Mapping]],
    ):
        if not isinstance(owner_user_id, str) or not owner_user_id.strip():
            raise ValueError("A configured owner user ID is required.")
        if not callable(session_verifier):
            raise TypeError("A Supabase session verifier is required.")
        self._owner_user_id = owner_user_id.strip()
        self._session_verifier = session_verifier

    def authenticate_owner(self, access_token: str) -> Mapping:
        if not isinstance(access_token, str) or not access_token.strip():
            raise AuthorizationError("A valid login session is required.")
        try:
            user = self._session_verifier(access_token.strip())
        except Exception:
            user = None
        if not isinstance(user, Mapping):
            raise AuthorizationError("The login session is invalid or expired.")
        user_id = user.get("id")
        if not isinstance(user_id, str) or not secrets.compare_digest(
            user_id, self._owner_user_id
        ):
            raise AuthorizationError("This account is not authorized as the owner.")
        return {"id": user_id}


@dataclass(frozen=True)
class ApprovalReceipt:
    action: str
    owner_id: str
    expires_at: float


class ApprovalStore:
    """In-memory, single-use approvals bound to an exact action and arguments.

    Receipts are intentionally volatile: a process restart invalidates all
    pending approvals. This avoids persisting bearer-like approval tokens
    before a durable, protected store is designed.
    """

    def __init__(self, ttl_seconds: int = 120, clock=None):
        if not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 600:
            raise ValueError("Approval lifetime must be between 1 and 600 seconds.")
        self._ttl = ttl_seconds
        self._clock = clock or time.monotonic
        self._pending = {}
        self._lock = threading.Lock()

    @staticmethod
    def _argument_digest(arguments):
        if not isinstance(arguments, Mapping):
            raise TypeError("Action arguments must be an object.")
        try:
            encoded = json.dumps(
                arguments, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise ValueError("Action arguments must be JSON-compatible.")
        return hashlib.sha256(encoded).hexdigest()

    def issue(self, action: str, arguments: Mapping, owner_id: str) -> str:
        if not isinstance(action, str) or not action.strip():
            raise ValueError("A valid action name is required.")
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("A valid owner ID is required.")
        digest = self._argument_digest(arguments)
        token = secrets.token_urlsafe(32)
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            self._pending[token] = (
                action.strip().lower(), digest, owner_id, now + self._ttl
            )
        return token

    def consume(self, token: str, action: str, arguments: Mapping, owner_id: str) -> bool:
        if not all(isinstance(value, str) and value for value in (
            token, action, owner_id
        )):
            return False
        try:
            digest = self._argument_digest(arguments)
        except (TypeError, ValueError):
            return False
        now = self._clock()
        with self._lock:
            receipt = self._pending.pop(token, None)
            self._purge_expired(now)
        if receipt is None:
            return False
        expected_action, expected_digest, expected_owner, expires_at = receipt
        return (
            now <= expires_at
            and secrets.compare_digest(expected_action, action.strip().lower())
            and secrets.compare_digest(expected_digest, digest)
            and secrets.compare_digest(expected_owner, owner_id)
        )

    def _purge_expired(self, now):
        expired = [
            token for token, receipt in self._pending.items()
            if receipt[3] < now
        ]
        for token in expired:
            self._pending.pop(token, None)

    def clear(self):
        with self._lock:
            self._pending.clear()
