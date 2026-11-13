"""Manual smoke test for the local Neha challenge-login API.

Run with: python test_login.py
"""
import json
import urllib.request
import urllib.error


def main():
    base = "http://127.0.0.1:8765"
    challenge_request = urllib.request.Request(
        base + "/auth/challenge", data=b"{}", headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(challenge_request, timeout=5) as response:
            challenge = json.loads(response.read())
    except urllib.error.HTTPError as error:
        print("Challenge failed:", error.code, error.read().decode())
        return
    print("Login challenge:", challenge.get("challenge"))
    answer = input("Login response: ").strip()
    payload = json.dumps({
        "challenge_id": challenge.get("challenge_id"),
        "answer": answer,
    }).encode()
    request = urllib.request.Request(
        base + "/auth/login", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        result = json.loads(error.read())
    print("Login successful:", result.get("success", False))
    print("Access token received:", bool(result.get("access_token")))
    if result.get("error"):
        print("Error:", result["error"])


if __name__ == "__main__":
    main()
