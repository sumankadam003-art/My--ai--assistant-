import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from neha_gateway import NehaGateway
from cloud_auth import sign_up, sign_in, get_authenticated_user
from cloud_memory import save_cloud_memory, load_cloud_memories

HOST = os.getenv("NEHA_API_HOST", "127.0.0.1")
PORT = 8765
gateway = NehaGateway()


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
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 100_000:
            raise ValueError("Invalid request size")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid request body")
        return payload

    def do_OPTIONS(self):
        self.send_json(200, {"ok": True})

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True, "service": "Neha API"})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path not in ("/chat", "/auth/signup", "/auth/login", "/memory/save", "/memory/load"):
            self.send_json(404, {"error": "Not found"})
            return

        try:
            payload = self.read_payload()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Invalid JSON request"})
            return

        if self.path in ("/auth/signup", "/auth/login"):
            email = payload.get("email")
            password = payload.get("password")

            if not isinstance(email, str) or not isinstance(password, str):
                self.send_json(400, {"error": "Email and password are required"})
                return

            email = email.strip()
            if (
                not email
                or len(email) > 254
                or len(password) < 1
                or len(password) > 1024
            ):
                self.send_json(400, {"error": "Invalid email or password length"})
                return

            result = (
                sign_up(email, password)
                if self.path == "/auth/signup"
                else sign_in(email, password)
            )

            if not result.get("success"):
                self.send_json(400, {
                    "success": False,
                    "error": result.get("error", "Authentication failed"),
                })
                return

            response = {
                "success": True,
                "user_id": result.get("user_id"),
                "email_confirmation_required": result.get(
                    "email_confirmation_required", False
                ),
            }

            # Return the session token only after successful authentication.
            if result.get("access_token"):
                response["access_token"] = result["access_token"]

            self.send_json(200, response)
            return

        if self.path in ("/memory/save", "/memory/load"):
            token = self.headers.get("Authorization", "")
            if not token.startswith("Bearer "):
                self.send_json(401, {"success": False, "error": "Authentication required"})
                return

            access_token = token[7:].strip()
            if not access_token:
                self.send_json(401, {"success": False, "error": "Invalid authentication token"})
                return

            authenticated_user = get_authenticated_user(access_token)
            if not authenticated_user:
                self.send_json(401, {"success": False, "error": "Invalid or expired session"})
                return

            user_id = authenticated_user["id"]
            requested_user_id = payload.get("user_id")
            if requested_user_id is not None and requested_user_id != user_id:
                self.send_json(403, {"success": False, "error": "User ID does not match authenticated account"})
                return

            if self.path == "/memory/save":
                memory = payload.get("memory")
                category = payload.get("category", "general")
                if not isinstance(memory, str) or not memory.strip() or len(memory) > 5000:
                    self.send_json(400, {"success": False, "error": "Memory must contain 1–5000 characters"})
                    return
                if not isinstance(category, str) or len(category) > 100:
                    self.send_json(400, {"success": False, "error": "Invalid category"})
                    return

                saved = save_cloud_memory(user_id, memory, access_token, category)
                if not saved:
                    self.send_json(403, {"success": False, "error": "Memory save failed; check authentication and permissions"})
                    return
                self.send_json(200, {"success": True})
                return

            memories = load_cloud_memories(user_id, access_token)
            self.send_json(200, {"success": True, "memories": memories})
            return

        message = payload.get("message", "")
        if not isinstance(message, str) or not message.strip():
            self.send_json(400, {"error": "Message is required"})
            return
        if len(message) > 10_000:
            self.send_json(400, {"error": "Message is too long"})
            return

        # Chat is private: every request must carry a valid Supabase access token.
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            self.send_json(401, {"error": "Authentication required"})
            return

        access_token = auth_header[7:].strip()
        if not access_token:
            self.send_json(401, {"error": "Authentication required"})
            return

        authenticated_user = get_authenticated_user(access_token)
        if not authenticated_user:
            self.send_json(401, {"error": "Invalid or expired session"})
            return

        user_id = authenticated_user["id"]

        try:
            reply = gateway.ask(
                message.strip(),
                user_id=user_id,
                access_token=access_token,
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
