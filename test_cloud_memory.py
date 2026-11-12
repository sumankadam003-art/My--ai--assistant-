import getpass
import json
import urllib.request
import urllib.error
import uuid

BASE = "http://127.0.0.1:8765"

def post(path, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read())
        except Exception:
            return error.code, {}

email = input("Supabase email: ").strip()
password = getpass.getpass("Supabase password (hidden): ")

status, login = post("/auth/login", {
    "email": email,
    "password": password,
})

if status != 200 or not login.get("access_token") or not login.get("user_id"):
    print("Login failed:", login.get("error", "Unexpected response"))
    raise SystemExit(1)

token = login["access_token"]
user_id = login["user_id"]
test_memory = "Neha cloud connection test " + str(uuid.uuid4())

status, saved = post("/memory/save", {
    "user_id": user_id,
    "memory": test_memory,
    "category": "connection_test",
}, token)

print("Memory save accepted:", status == 200 and saved.get("success") is True)

status, loaded = post("/memory/load", {"user_id": user_id}, token)
print("Memory load HTTP status:", status)
print("Memory load succeeded:", status == 200 and loaded.get("success") is True)
memories = loaded.get("memories", [])
print("Saved test memory retrieved:", any(m.get("memory") == test_memory for m in memories))

print("\n--- Authenticated AI memory recall test ---")
recall_fact = "The secret test colour is violet " + str(uuid.uuid4())

status, saved = post("/memory/save", {
    "user_id": user_id,
    "memory": recall_fact,
    "category": "recall_test",
}, token)

print("Recall fact saved:", status == 200 and saved.get("success") is True)

if status == 200 and saved.get("success") is True:
    status, chat = post("/chat", {
        "message": "According to my saved memories, what is the secret test colour? "
                   "Answer using the exact colour if you know it."
    }, token)

    reply = chat.get("reply", "") if isinstance(chat, dict) else ""
    print("Authenticated chat HTTP status:", status)
    print("AI reply received:", bool(reply))
    print("Cloud memory used in reply:", "violet" in reply.lower())
else:
    print("Recall test skipped because saving the fact failed.")
