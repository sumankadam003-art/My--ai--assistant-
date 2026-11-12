import json
import http.client
import ssl
import urllib.request
import urllib.error
from pathlib import Path

KEY_FILE = Path.home() / ".config/neha-assistant/.env"
MAX_RESPONSE_BYTES = 1_048_576
MAX_PROMPT_CHARS = 20_000
MAX_HISTORY_MESSAGE_CHARS = 10_000
MAX_HISTORY_TOTAL_CHARS = 100_000


def ask_groq(prompt, history=None):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt must be a non-empty string.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError("Prompt exceeds the 20,000-character limit.")

    if history is None:
        history = []
    elif not isinstance(history, list):
        raise ValueError("History must be a list.")

    safe_history = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            safe_history.append({"role": role, "content": content})

    safe_history = safe_history[-40:]
    total_history_chars = 0
    for item in safe_history:
        content = item["content"]
        if len(content) > MAX_HISTORY_MESSAGE_CHARS:
            raise ValueError("A history message exceeds the 10,000-character limit.")
        total_history_chars += len(content)
        if total_history_chars > MAX_HISTORY_TOTAL_CHARS:
            raise ValueError("Conversation history exceeds the 100,000-character limit.")

    env = {}
    try:
        env_content = KEY_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError("Neha configuration file was not found.") from None
    except PermissionError:
        raise RuntimeError("Cannot read the Neha configuration file: permission denied.") from None
    except UnicodeDecodeError:
        raise RuntimeError("Neha configuration file contains invalid text encoding.") from None

    for line in env_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            env[name.strip()] = value

    key = env.get("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing from the .env file.")

    data = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {
                "role": "system",
                "content": "You are Neha, a friendly and trustworthy personal AI assistant. Be warm, respectful, emotionally supportive, clear, and concise. Keep a consistent identity across conversations. Never invent personal memories, places, events, conversations, or experiences. Never present guesses as facts. If you do not know something, say so honestly. Use saved personal context only when relevant."
            },
            *safe_history,
            {"role": "user", "content": prompt.strip()}
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }

    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(response_body) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Groq response exceeded the 1 MB size limit.")
            result = json.loads(response_body.decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Groq API returned HTTP status {error.code}.") from None
    except urllib.error.URLError:
        raise RuntimeError("Could not connect to the Groq API.") from None
    except TimeoutError:
        raise RuntimeError("Groq API request timed out.") from None
    except (ssl.SSLError, http.client.IncompleteRead):
        raise RuntimeError("Groq returned an interrupted or invalid connection response.") from None
    except OSError:
        raise RuntimeError("A network error occurred while reading the Groq response.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Groq API returned invalid JSON.") from None

    if not isinstance(result, dict):
        raise RuntimeError("Groq returned an invalid response.")

    choices = result.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise RuntimeError("Groq returned no valid choices.")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Groq returned an invalid message.")

    answer = message.get("content")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Groq returned empty or invalid text.")

    return answer.strip()


if __name__ == "__main__":
    try:
        print("Neha:", ask_groq("Introduce yourself in one sentence."))
    except Exception as error:
        print("Connection failed:", error)
