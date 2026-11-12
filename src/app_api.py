"""Localhost API for Neha chat, backend cloud memory, and approved actions."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from .neha_gateway import NehaGateway
    from .cloud_memory import (
        NEHA_CLOUD_OWNER_ID, save_cloud_memory, load_cloud_memories,
    )
    from .action_registry import build_default_action_manager
    from .action_service_factory import build_authorized_action_service, ActionServiceConfigurationError
    from .authorized_action_service import AuthorizationError
except ImportError:
    from neha_gateway import NehaGateway
    from cloud_memory import (
        NEHA_CLOUD_OWNER_ID, save_cloud_memory, load_cloud_memories,
    )
    from action_registry import build_default_action_manager
    from action_service_factory import build_authorized_action_service, ActionServiceConfigurationError
    from authorized_action_service import AuthorizationError

# Keep this API on loopback. Do not expose it to a LAN or public interface.
HOST = os.getenv("NEHA_API_HOST", "127.0.0.1")
PORT = 8765
gateway = NehaGateway()
_action_service = None
_action_service_lock = threading.Lock()


def get_action_service():
    global _action_service
    if _action_service is not None:
        return _action_service
    with _action_service_lock:
        if _action_service is None:
            _action_service = build_authorized_action_service(
                build_default_action_manager()
            )
    return _action_service


class NehaAPIHandler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8081")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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

    def do_OPTIONS(self):
        self.send_json(200, {"ok": True})

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {
                "ok": True,
                "service": "Neha API",
                "cloud_memory_configured": bool(NEHA_CLOUD_OWNER_ID),
            })
            return
        if self.path == "/actions":
            try:
                service = get_action_service()
                self.send_json(200, {"success": True, "actions": service.list_actions(None)})
            except (ActionServiceConfigurationError, AuthorizationError):
                self.send_json(503, {"success": False, "error": "Neha action service is not configured"})
            except Exception:
                self.send_json(500, {"success": False, "error": "Could not list actions"})
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        allowed = ("/chat", "/memory/save", "/memory/load", "/actions/approve", "/actions/execute")
        if self.path not in allowed:
            self.send_json(404, {"error": "Not found"})
            return
        try:
            payload = self.read_payload()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Invalid JSON request"})
            return

        if self.path == "/memory/save":
            memory, category = payload.get("memory"), payload.get("category", "general")
            if not isinstance(memory, str) or not memory.strip() or len(memory) > 5000:
                self.send_json(400, {"success": False, "error": "Memory must contain 1–5000 characters"})
                return
            if not isinstance(category, str) or len(category) > 100:
                self.send_json(400, {"success": False, "error": "Invalid category"})
                return
            if not NEHA_CLOUD_OWNER_ID or not save_cloud_memory(NEHA_CLOUD_OWNER_ID, memory, category):
                self.send_json(503, {"success": False, "error": "Neha cloud memory is not configured or save failed"})
                return
            self.send_json(200, {"success": True})
            return

        if self.path == "/memory/load":
            if not NEHA_CLOUD_OWNER_ID:
                self.send_json(503, {"success": False, "error": "Neha cloud memory is not configured"})
                return
            memories = load_cloud_memories(NEHA_CLOUD_OWNER_ID)
            if memories is None:
                self.send_json(503, {"success": False, "error": "Neha cloud memory could not be loaded"})
                return
            self.send_json(200, {"success": True, "memories": memories})
            return

        if self.path in ("/actions/approve", "/actions/execute"):
            try:
                service = get_action_service()
                action, arguments = payload.get("action"), payload.get("arguments", {})
                if self.path == "/actions/approve":
                    if payload.get("owner_confirmed") is not True:
                        self.send_json(403, {"success": False, "error": "Explicit confirmation is required"})
                        return
                    self.send_json(200, service.request_approval(None, action, arguments))
                    return
                result = service.execute(None, action, arguments, payload.get("approval_token"))
                self.send_json(200, result)
            except (ActionServiceConfigurationError, AuthorizationError):
                self.send_json(503, {"success": False, "error": "Neha action service is not configured"})
            except ValueError as exc:
                self.send_json(400, {"success": False, "error": str(exc)})
            except Exception:
                self.send_json(500, {"success": False, "error": "Action request failed safely"})
            return

        message = payload.get("message", "")
        if not isinstance(message, str) or not message.strip():
            self.send_json(400, {"error": "Message is required"})
            return
        if len(message) > 10_000:
            self.send_json(400, {"error": "Message is too long"})
            return
        try:
            reply = gateway.ask(
                message.strip(),
                user_id=NEHA_CLOUD_OWNER_ID or None,
            )
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
