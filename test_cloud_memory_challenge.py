"""Interactive end-to-end test for Neha's local challenge-authenticated cloud API.

Run from the repository root:
    PYTHONPATH=src python test_cloud_memory_challenge.py

The private NEHA_LOGIN_OFFSET is read locally from the environment or .env;
it is never printed or sent to the API.
"""
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8765"


def post(path, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read())
        except (ValueError, UnicodeDecodeError):
            return error.code, {}


def read_login_offset():
    raw = os.environ.get("NEHA_LOGIN_OFFSET")
    if raw is None:
        env_path = Path(".env")
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("NEHA_LOGIN_OFFSET="):
                    raw = line.split("=", 1)[1].strip().strip("\"'")
                    break
        except OSError:
            pass
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise RuntimeError(
            "NEHA_LOGIN_OFFSET is not configured in the environment or .env"
        )


def require(condition, message):
    print(f"{message}: {'PASS' if condition else 'FAIL'}")
    return bool(condition)


def main():
    offset = read_login_offset()

    status, challenge = post("/auth/challenge", {})
    if not require(
        status == 200 and challenge.get("success") is True
        and isinstance(challenge.get("challenge_id"), str)
        and isinstance(challenge.get("challenge"), int),
        "Challenge request",
    ):
        print("Server response:", challenge.get("error", "Unexpected response"))
        return 1

    answer = str(challenge["challenge"] + offset)
    status, login = post("/auth/login", {
        "challenge_id": challenge["challenge_id"],
        "answer": answer,
    })
    token = login.get("access_token") if isinstance(login, dict) else None
    if not require(status == 200 and bool(token), "Owner challenge login"):
        print("Login failed:", login.get("error", "Unexpected response"))
        return 1

    test_memory = "Neha cloud connection test " + str(uuid.uuid4())
    status, saved = post("/memory/save", {
        "memory": test_memory,
        "category": "connection_test",
    }, token)
    if not require(
        status == 200 and saved.get("success") is True,
        "Cloud memory save",
    ):
        print("Save response:", saved.get("error", "Unexpected response"))
        return 1

    status, loaded = post("/memory/load", {}, token)
    memories = loaded.get("memories", []) if isinstance(loaded, dict) else []
    retrieved = any(
        isinstance(item, dict) and item.get("memory") == test_memory
        for item in memories
    )
    if not require(
        status == 200 and loaded.get("success") is True and retrieved,
        "Cloud memory load and retrieval",
    ):
        print("Load response:", loaded.get("error", "Unexpected response"))
        return 1

    print("\n--- Authenticated AI memory recall test ---")
    recall_fact = "The secret test colour is violet " + str(uuid.uuid4())
    status, saved = post("/memory/save", {
        "memory": recall_fact,
        "category": "recall_test",
    }, token)
    if not require(
        status == 200 and saved.get("success") is True,
        "Recall fact save",
    ):
        print("Recall save response:", saved.get("error", "Unexpected response"))
        return 1

    status, chat = post("/chat", {
        "message": "According to my saved memories, what is the secret test colour? "
                   "Answer using the exact colour if you know it."
    }, token)
    reply = chat.get("reply", "") if isinstance(chat, dict) else ""
    if not require(status == 200 and bool(reply), "Authenticated AI response"):
        print("Chat response:", chat.get("error", "Unexpected response"))
        return 1
    if not require("violet" in reply.lower(), "AI recalls cloud memory"):
        print("AI reply did not contain the expected test colour.")
        return 1

    print("\nCloud integration test completed successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(error)
        raise SystemExit(2)
