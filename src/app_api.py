"""Localhost API for Neha chat, cloud memory, and owner-approved device actions."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from .neha_gateway import NehaGateway
    from .cloud_auth import sign_up, sign_in, get_authenticated_user
    from .cloud_memory import save_cloud_memory, load_cloud_memories
    from .local_owner_auth import LocalOwnerAuth, OwnerAccountError
    from .action_registry import build_default_action_manager
    from .action_service_factory import build_authorized_action_service, ActionServiceConfigurationError
    from .authorized_action_service import AuthorizationError
except ImportError:
    from neha_gateway import NehaGateway
    from cloud_auth import sign_up, sign_in, get_authenticated_user
    from cloud_memory import save_cloud_memory, load_cloud_memories
    from local_owner_auth import LocalOwnerAuth, OwnerAccountError
    from action_registry import build_default_action_manager
    from action_service_factory import build_authorized_action_service, ActionServiceConfigurationError
    from authorized_action_service import AuthorizationError

HOST = os.getenv("NEHA_API_HOST", "127.0.0.1")
PORT = 8765
gateway = NehaGateway()
owner_auth = LocalOwnerAuth()
_action_service = None
_action_service_lock = threading.Lock()


def get_action_service():
    global _action_service
    if _action_service is not None:
        return _action_service
    with _action_service_lock:
        if _action_service is None:
            _action_service = build_authorized_action_service(
                build_default_action_manager(), owner_auth=owner_auth
            )
    return _action_service


class LoginRateLimiter:
    def __init__(self, limit=5, window_seconds=300):
        self.limit, self.window_seconds = limit, window_seconds
        self._attempts, self._lock = {}, threading.Lock()

    def allowed(self, key):
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._attempts.get(key, []) if now-t < self.window_seconds]
            self._attempts[key] = recent
            return len(recent) < self.limit

    def record_failure(self, key):
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._attempts.get(key, []) if now-t < self.window_seconds]
            recent.append(now)
            self._attempts[key] = recent

    def clear(self, key):
        with self._lock:
            self._attempts.pop(key, None)


owner_login_limiter = LoginRateLimiter()
owner_recovery_limiter = LoginRateLimiter()


class NehaAPIHandler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8081")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def read_payload(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            raise ValueError("Invalid request size")
        if not 0 < length <= 100_000:
            raise ValueError("Invalid request size")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid request body")
        return payload

    def bearer_token(self):
        header = self.headers.get("Authorization", "")
        token = header[7:].strip() if header.startswith("Bearer ") else ""
        return token or None

    def owner_service(self):
        token = self.bearer_token()
        if not token:
            self.send_json(401, {"success": False, "error": "Owner login required"})
            return None, None
        try:
            service = get_action_service()
            if not owner_auth.verify_session(token):
                self.send_json(401, {"success": False, "error": "Invalid or expired owner session"})
                return None, None
            return service, token
        except (OwnerAccountError, ActionServiceConfigurationError):
            self.send_json(503, {"success": False, "error": "Local owner account is not configured"})
        except Exception:
            self.send_json(401, {"success": False, "error": "Invalid or expired owner session"})
        return None, None

    def do_OPTIONS(self):
        self.send_json(200, {"ok": True})

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True, "service": "Neha API"})
            return
        if self.path == "/actions":
            service, token = self.owner_service()
            if service is None:
                return
            try:
                self.send_json(200, {"success": True, "actions": service.list_actions(token)})
            except AuthorizationError:
                self.send_json(401, {"success": False, "error": "Invalid owner session"})
            except Exception:
                self.send_json(500, {"success": False, "error": "Could not list actions"})
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        allowed = (
            "/chat", "/auth/signup", "/auth/login", "/memory/save", "/memory/load",
            "/owner/login", "/owner/logout", "/owner/recovery/enroll",
            "/owner/recovery/activate", "/owner/recovery/confirm", "/owner/password/reset",
            "/actions/approve", "/actions/execute",
        )
        if self.path not in allowed:
            self.send_json(404, {"error": "Not found"})
            return
        try:
            payload = self.read_payload()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Invalid JSON request"})
            return

        if self.path == "/owner/login":
            username, password = payload.get("username"), payload.get("password")
            if not isinstance(username, str) or not isinstance(password, str):
                self.send_json(400, {"success": False, "error": "Username and password are required"})
                return
            key = self.client_address[0]
            if not owner_login_limiter.allowed(key):
                self.send_json(429, {"success": False, "error": "Too many login attempts. Try again later."})
                return
            try:
                result = owner_auth.login(username, password)
            except OwnerAccountError:
                result = None
            if not result:
                owner_login_limiter.record_failure(key)
                self.send_json(401, {"success": False, "error": "Invalid username or password"})
                return
            owner_login_limiter.clear(key)
            self.send_json(200, {"success": True, **result})
            return

        if self.path in ("/owner/recovery/enroll", "/owner/recovery/activate"):
            token = self.bearer_token()
            if not token or not owner_auth.verify_session(token):
                self.send_json(401, {"success": False, "error": "Valid owner login is required"})
                return
            try:
                if self.path == "/owner/recovery/enroll":
                    secret = owner_auth.begin_recovery_enrollment(token)
                    self.send_json(200, {"success": True, "recovery_secret": secret})
                else:
                    if owner_auth.activate_recovery_enrollment(token, payload.get("recovery_secret")):
                        self.send_json(200, {"success": True})
                    else:
                        self.send_json(400, {"success": False, "error": "Recovery enrollment failed"})
            except OwnerAccountError as exc:
                self.send_json(400, {"success": False, "error": str(exc)})
            except Exception:
                self.send_json(500, {"success": False, "error": "Recovery enrollment failed safely"})
            return

        if self.path == "/owner/recovery/confirm":
            secret = payload.get("recovery_secret")
            try:
                if owner_auth.confirm_recovery_rotation(secret):
                    self.send_json(200, {"success": True, "message": "Recovery credential rotation confirmed."})
                else:
                    self.send_json(401, {"success": False, "error": "Recovery rotation confirmation failed"})
            except Exception:
                self.send_json(500, {"success": False, "error": "Recovery rotation confirmation failed safely"})
            return

        if self.path == "/owner/password/reset":
            key = self.client_address[0]
            if not owner_recovery_limiter.allowed(key):
                self.send_json(429, {"success": False, "error": "Too many recovery attempts. Try again later."})
                return
            secret, new_password = payload.get("recovery_secret"), payload.get("new_password")
            try:
                replacement_secret = owner_auth.reset_password_with_recovery(secret, new_password)
                if replacement_secret:
                    owner_recovery_limiter.clear(key)
                    self.send_json(200, {
                        "success": True,
                        "message": "Owner password updated. Biometric recovery remains enabled.",
                        "recovery_secret": replacement_secret,
                    })
                else:
                    owner_recovery_limiter.record_failure(key)
                    self.send_json(401, {"success": False, "error": "Biometric recovery verification failed"})
            except OwnerAccountError as exc:
                self.send_json(400, {"success": False, "error": str(exc)})
            except Exception:
                self.send_json(500, {"success": False, "error": "Password reset failed safely"})
            return

        if self.path == "/owner/logout":
            token = self.bearer_token()
            if not token or not owner_auth.logout(token):
                self.send_json(401, {"success": False, "error": "Invalid or expired owner session"})
            else:
                self.send_json(200, {"success": True})
            return

        if self.path in ("/actions/approve", "/actions/execute"):
            service, token = self.owner_service()
            if service is None:
                return
            action, arguments = payload.get("action"), payload.get("arguments", {})
            if self.path == "/actions/approve":
                if payload.get("owner_confirmed") is not True:
                    self.send_json(403, {"success": False, "error": "Explicit owner confirmation is required"})
                    return
                try:
                    self.send_json(200, service.request_approval(token, action, arguments))
                except AuthorizationError:
                    self.send_json(401, {"success": False, "error": "Invalid or expired owner session"})
                except ValueError as exc:
                    self.send_json(400, {"success": False, "error": str(exc)})
                except Exception:
                    self.send_json(500, {"success": False, "error": "Approval could not be issued"})
                return
            try:
                result = service.execute(token, action, arguments, payload.get("approval_token"))
                self.send_json(200, result)
            except AuthorizationError:
                self.send_json(401, {"success": False, "error": "Invalid owner session"})
            except Exception:
                self.send_json(500, {"success": False, "error": "Action execution failed safely"})
            return

        if self.path in ("/auth/signup", "/auth/login"):
            email, password = payload.get("email"), payload.get("password")
            if not isinstance(email, str) or not isinstance(password, str):
                self.send_json(400, {"error": "Email and password are required"})
                return
            email = email.strip()
            if not email or len(email) > 254 or not 1 <= len(password) <= 1024:
                self.send_json(400, {"error": "Invalid email or password length"})
                return
            result = sign_up(email, password) if self.path == "/auth/signup" else sign_in(email, password)
            if not result.get("success"):
                self.send_json(400, {"success": False, "error": result.get("error", "Authentication failed")})
                return
            response = {"success": True, "user_id": result.get("user_id"),
                        "email_confirmation_required": result.get("email_confirmation_required", False)}
            if result.get("access_token"):
                response["access_token"] = result["access_token"]
            self.send_json(200, response)
            return

        if self.path in ("/memory/save", "/memory/load"):
            access_token = self.bearer_token()
            if not access_token:
                self.send_json(401, {"success": False, "error": "Authentication required"})
                return
            user = get_authenticated_user(access_token)
            if not user:
                self.send_json(401, {"success": False, "error": "Invalid or expired session"})
                return
            user_id = user["id"]
            if payload.get("user_id") is not None and payload["user_id"] != user_id:
                self.send_json(403, {"success": False, "error": "User ID does not match authenticated account"})
                return
            if self.path == "/memory/save":
                memory, category = payload.get("memory"), payload.get("category", "general")
                if not isinstance(memory, str) or not memory.strip() or len(memory) > 5000:
                    self.send_json(400, {"success": False, "error": "Memory must contain 1–5000 characters"})
                    return
                if not isinstance(category, str) or len(category) > 100:
                    self.send_json(400, {"success": False, "error": "Invalid category"})
                    return
                if not save_cloud_memory(user_id, memory, access_token, category):
                    self.send_json(403, {"success": False, "error": "Memory save failed; check authentication and permissions"})
                    return
                self.send_json(200, {"success": True})
                return
            self.send_json(200, {"success": True, "memories": load_cloud_memories(user_id, access_token)})
            return

        message = payload.get("message", "")
        if not isinstance(message, str) or not message.strip():
            self.send_json(400, {"error": "Message is required"})
            return
        if len(message) > 10_000:
            self.send_json(400, {"error": "Message is too long"})
            return
        access_token = self.bearer_token()
        if not access_token:
            self.send_json(401, {"error": "Authentication required"})
            return
        user = get_authenticated_user(access_token)
        if not user:
            self.send_json(401, {"error": "Invalid or expired session"})
            return
        try:
            reply = gateway.ask(message.strip(), user_id=user["id"], access_token=access_token)
            self.send_json(200, {"reply": str(reply)})
        except Exception:
            self.send_json(500, {"error": "Neha could not process that message"})

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), NehaAPIHandler)
    print(f"Neha API listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nNeha API stopped.")
    finally:
        server.server_close()
