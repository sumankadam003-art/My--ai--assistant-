"""Localhost API for Neha chat, backend cloud memory, and approved actions."""
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from .neha_gateway import NehaGateway
    from .request_orchestrator import RequestOrchestrator
    from .cloud_memory import (
        NEHA_CLOUD_OWNER_ID, save_cloud_memory, load_cloud_memories,
    )
    from .action_registry import build_default_action_manager, MOBILE_ACTION_URLS
    from .action_service_factory import build_authorized_action_service, ActionServiceConfigurationError
    from .authorized_action_service import AuthorizationError
    from .local_owner_auth import LocalOwnerAuth, OwnerAccountError
except ImportError:
    from neha_gateway import NehaGateway
    from request_orchestrator import RequestOrchestrator
    from cloud_memory import (
        NEHA_CLOUD_OWNER_ID, save_cloud_memory, load_cloud_memories,
    )
    from action_registry import build_default_action_manager, MOBILE_ACTION_URLS
    from action_service_factory import build_authorized_action_service, ActionServiceConfigurationError
    from authorized_action_service import AuthorizationError
    from local_owner_auth import LocalOwnerAuth, OwnerAccountError

# Keep this API on loopback. Do not expose it to a LAN or public interface.
HOST = os.getenv("NEHA_API_HOST", "127.0.0.1")
PORT = 8765
gateway = NehaGateway()
request_orchestrator = RequestOrchestrator(gateway=gateway)
owner_auth = LocalOwnerAuth(session_ttl_seconds=None)
_action_service = None
_action_service_lock = threading.Lock()
_pending_chat_plans = {}
_pending_chat_plans_lock = threading.Lock()
_PENDING_CHAT_PLAN_TTL_SECONDS = 120


def _is_confirmation(message):
    return message.strip().lower().rstrip(".!?") in {
        "yes", "yes please", "yeah", "yep", "confirm", "confirmed",
        "go ahead", "do it", "proceed", "okay", "ok", "sure",
    }


def _is_cancellation(message):
    return message.strip().lower().rstrip(".!?") in {
        "no", "no thanks", "cancel", "stop", "don't", "do not",
    }


def _validate_chat_plan(service, steps):
    """Validate every proposed step before any step is executed."""
    if not isinstance(steps, list) or not 1 <= len(steps) <= 8:
        raise ValueError("The proposed action plan is invalid.")
    validated = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("The proposed action plan is invalid.")
        action = step.get("legacy_action", step.get("action"))
        arguments = step.get("arguments", {})
        service._find_action(action)
        clean_arguments = service._validate_arguments(action, arguments)
        validated.append({"action": action, "arguments": clean_arguments})
    if len(validated) > 1 and any(item["action"] == "send_sms" for item in validated):
        raise ValueError("SMS composer handoff must be a separate, single-step request.")
    return validated


def get_action_service():
    global _action_service
    if _action_service is not None:
        return _action_service
    with _action_service_lock:
        if _action_service is None:
            _action_service = build_authorized_action_service(
                build_default_action_manager(mobile_url_launch=True), owner_auth=owner_auth
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def access_token(self):
        header = self.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        return token.strip() if scheme.lower() == "bearer" and token.strip() else None

    def require_owner(self):
        return owner_auth.verify_session(self.access_token())

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
                token = self.access_token()
                if not owner_auth.verify_session(token):
                    self.send_json(401, {"success": False, "error": "Login required"})
                    return
                service = get_action_service()
                self.send_json(200, {"success": True, "actions": service.list_actions(token)})
            except AuthorizationError:
                self.send_json(401, {"success": False, "error": "Login required"})
            except (ActionServiceConfigurationError, OwnerAccountError):
                self.send_json(503, {"success": False, "error": "Neha action service is not configured"})
            except Exception:
                self.send_json(500, {"success": False, "error": "Could not list actions"})
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/auth/challenge":
            try:
                self.send_json(200, {"success": True, **owner_auth.create_challenge()})
            except OwnerAccountError:
                self.send_json(503, {"success": False, "error": "Owner login is not configured"})
            return
        if self.path == "/auth/login":
            try:
                payload = self.read_payload()
                result = owner_auth.login_challenge(payload.get("challenge_id"), payload.get("answer"))
                if not result:
                    self.send_json(401, {"success": False, "error": "Invalid or expired challenge"})
                    return
                self.send_json(200, {"success": True, **result})
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self.send_json(400, {"success": False, "error": "Invalid login request"})
            except OwnerAccountError:
                self.send_json(503, {"success": False, "error": "Owner login is not configured"})
            return
        if self.path == "/auth/logout":
            token = self.access_token()
            revoked = owner_auth.logout(token)
            self.send_json(200 if revoked else 401, {"success": bool(revoked)})
            return
        allowed = ("/chat", "/chat/approve", "/chat/cancel", "/memory/save", "/memory/load", "/actions/approve", "/actions/execute")
        if self.path not in allowed:
            self.send_json(404, {"error": "Not found"})
            return
        token = self.access_token()
        if not owner_auth.verify_session(token):
            self.send_json(401, {"success": False, "error": "Login required"})
            return
        try:
            payload = self.read_payload()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Invalid JSON request"})
            return

        if self.path == "/chat/approve":
            plan_id = payload.get("plan_id")
            if payload.get("owner_confirmed") is not True or not isinstance(plan_id, str):
                self.send_json(403, {"success": False, "error": "Explicit owner confirmation is required"})
                return
            owner = owner_auth.verify_session(token)
            owner_id = owner["id"]
            with _pending_chat_plans_lock:
                stored = _pending_chat_plans.get(owner_id)
                if not stored or stored.get("plan_id") != plan_id or stored["expires_at"] <= time.monotonic():
                    _pending_chat_plans.pop(owner_id, None)
                    self.send_json(409, {"success": False, "error": "This action plan expired or is no longer pending"})
                    return
                pending_plan = _pending_chat_plans.pop(owner_id)
            try:
                service = get_action_service()
                steps = _validate_chat_plan(service, pending_plan["steps"])
                results = []
                for step in steps:
                    try:
                        approval = service.request_approval(token, step["action"], step["arguments"])
                        result = service.execute(token, step["action"], step["arguments"], approval["approval_token"])
                        if not isinstance(result, dict):
                            result = {"status": "execution_failed", "message": "Action returned an invalid result"}
                    except AuthorizationError:
                        result = {"status": "authorization_failed", "message": "Owner authorization expired during the plan"}
                    except Exception:
                        result = {"status": "execution_failed", "message": "This step failed safely"}
                    if result.get("status") == "executed_unverified":
                        if step["action"] in MOBILE_ACTION_URLS:
                            result["launch_url"] = MOBILE_ACTION_URLS[step["action"]]
                        if step["action"] == "send_sms":
                            result["sms_payload"] = step["arguments"]
                    results.append(result)
                    if result.get("status") != "executed_unverified":
                        break
                completed = sum(1 for item in results if item.get("status") == "executed_unverified")
                response = {
                    "success": completed == len(steps),
                    "action_results": results,
                    "completed_steps": completed,
                    "total_steps": len(steps),
                }
                if len(results) == 1 and results[0].get("sms_payload"):
                    response["sms_payload"] = results[0]["sms_payload"]
                    response["reply"] = "The SMS details are ready. Review them in Android's SMS composer and press Send yourself."
                elif completed == len(steps):
                    response["reply"] = "The approved action plan finished. Android could not independently verify every physical result."
                else:
                    response["reply"] = "The plan stopped after a step failed. Earlier completed steps may not be reversible."
                response["launch_urls"] = [item["launch_url"] for item in results if item.get("launch_url")]
                self.send_json(200, response)
            except AuthorizationError:
                self.send_json(401, {"success": False, "error": "Login required"})
            except (ActionServiceConfigurationError, OwnerAccountError):
                self.send_json(503, {"success": False, "error": "Neha action service is not configured"})
            except ValueError as exc:
                self.send_json(400, {"success": False, "error": str(exc)})
            except Exception:
                self.send_json(500, {"success": False, "error": "Approved action plan failed safely"})
            return

        if self.path == "/chat/cancel":
            plan_id = payload.get("plan_id")
            owner = owner_auth.verify_session(token)
            owner_id = owner["id"]
            with _pending_chat_plans_lock:
                stored = _pending_chat_plans.get(owner_id)
                if stored and stored.get("plan_id") == plan_id:
                    _pending_chat_plans.pop(owner_id, None)
            self.send_json(200, {"success": True, "cancelled": True})
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
                    self.send_json(200, service.request_approval(token, action, arguments))
                    return
                sms_payload = (
                    service._validate_arguments("send_sms", arguments)
                    if action == "send_sms" else None
                )
                result = service.execute(token, action, arguments, payload.get("approval_token"))
                if (
                    isinstance(result, dict)
                    and result.get("status") == "executed_unverified"
                    and result.get("action") in MOBILE_ACTION_URLS
                ):
                    result["launch_url"] = MOBILE_ACTION_URLS[result["action"]]
                if (
                    isinstance(result, dict)
                    and result.get("status") == "executed_unverified"
                    and result.get("action") == "send_sms"
                    and sms_payload is not None
                ):
                    result["sms_payload"] = sms_payload
                self.send_json(200, result)
            except AuthorizationError:
                self.send_json(401, {"success": False, "error": "Login required"})
            except ActionServiceConfigurationError:
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
        history = payload.get("history", [])
        if not isinstance(history, list) or len(history) > 40:
            self.send_json(400, {"error": "Conversation history must be a list of at most 40 messages"})
            return
        safe_history = []
        for item in history:
            if (
                isinstance(item, dict)
                and item.get("role") in ("user", "assistant")
                and isinstance(item.get("content"), str)
                and item["content"].strip()
                and len(item["content"]) <= 10_000
            ):
                safe_history.append({"role": item["role"], "content": item["content"]})
        owner = owner_auth.verify_session(token)
        owner_id = owner["id"]

        try:
            with _pending_chat_plans_lock:
                # A fresh request invalidates any older, unconfirmed plan.
                _pending_chat_plans.pop(owner_id, None)

            routed = request_orchestrator.handle(
                message.strip(),
                history=safe_history,
                user_id=NEHA_CLOUD_OWNER_ID or None,
            )
            route = routed.get("route")
            response_data = {"reply": str(routed.get("reply", "")), "route": route}

            if route == "action_plan":
                service = get_action_service()
                available = {
                    item.get("name"): item
                    for item in service.list_actions(token)
                    if isinstance(item, dict) and item.get("enabled") is True
                }
                validated = _validate_chat_plan(service, routed.get("steps", []))
                if any(step["action"] not in available for step in validated):
                    self.send_json(400, {"reply": "That action is not currently enabled.", "route": "planning_error"})
                    return
                plan_id = secrets.token_urlsafe(24)
                with _pending_chat_plans_lock:
                    _pending_chat_plans[owner_id] = {
                        "plan_id": plan_id,
                        "steps": validated,
                        "expires_at": time.monotonic() + _PENDING_CHAT_PLAN_TTL_SECONDS,
                    }
                response_data["pending_plan"] = {
                    "plan_id": plan_id,
                    "expires_in_seconds": _PENDING_CHAT_PLAN_TTL_SECONDS,
                    "steps": [
                        {"action": step["action"], "arguments": step["arguments"]}
                        for step in validated
                    ],
                }
            self.send_json(200, response_data)
        except AuthorizationError:
            self.send_json(401, {"success": False, "error": "Login required"})
        except (ActionServiceConfigurationError, OwnerAccountError):
            self.send_json(503, {"reply": "Neha's action service is not configured yet."})
        except ValueError as exc:
            self.send_json(400, {"reply": str(exc), "route": "planning_error"})
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
