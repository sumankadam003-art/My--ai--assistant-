import getpass
import json
import urllib.request
import urllib.error

email = input("Supabase email: ").strip()
password = getpass.getpass("Supabase password (hidden): ")

payload = json.dumps({"email": email, "password": password}).encode()
request = urllib.request.Request(
    "http://127.0.0.1:8765/auth/login",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read())
except urllib.error.HTTPError as error:
    result = json.loads(error.read())

print("Login successful:", result.get("success", False))
print("User ID received:", bool(result.get("user_id")))
print("Access token received:", bool(result.get("access_token")))
print("Email confirmation required:", result.get("email_confirmation_required", False))
if result.get("error"):
    print("Error:", result["error"])
