import json
import http.client
import ssl
import urllib.request
import urllib.error
from pathlib import Path

KEY_FILE = Path.home() / ".config/neha-assistant/.env"
MODEL = "gemini-3.5-flash"

MAX_RESPONSE_BYTES = 1_048_576
MAX_PROMPT_CHARS = 20_000
MAX_HISTORY_MESSAGE_CHARS = 10_000
MAX_HISTORY_TOTAL_CHARS = 100_000


def ask_gemini(prompt, history=None):
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
            safe_history.append({
                "role": "user" if role == "user" else "model",
                "parts": [{"text": content}]
            })

    safe_history = safe_history[-40:]
    total_history_chars = 0
    for item in safe_history:
        content = item["parts"][0]["text"]
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
    except OSError:
        raise RuntimeError("Could not read the Neha configuration file.") from None
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

    key = env.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing from .env")

    contents = safe_history
    contents.append({"role": "user", "parts": [{"text": prompt.strip()}]})

    data = {
        "systemInstruction": {
            "parts": [{
                "text": "You are Neha, a friendly and trustworthy personal AI assistant. Be warm, respectful, emotionally supportive, clear, and concise. Keep a consistent identity across conversations. Never invent personal memories, places, events, conversations, or experiences. Never present guesses as facts. If you do not know something, say so honestly. Use saved personal context only when relevant."
            }]
        },
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 500}
    }

    try:
        request_body = json.dumps(data).encode("utf-8")
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            data=request_body,
            headers={
                "x-goog-api-key": key,
                "Content-Type": "application/json"
            },
            method="POST"
        )
    except (TypeError, ValueError, UnicodeError):
        raise RuntimeError("Could not prepare the Gemini API request.") from None

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(response_body) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Gemini response exceeded the 1 MB size limit.")
            result = json.loads(response_body.decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Gemini API returned HTTP status {error.code}.") from None
    except urllib.error.URLError:
        raise RuntimeError("Could not connect to the Gemini API.") from None
    except TimeoutError:
        raise RuntimeError("Gemini API request timed out.") from None
    except (ssl.SSLError, http.client.IncompleteRead):
        raise RuntimeError("Gemini returned an interrupted or invalid connection response.") from None
    except OSError:
        raise RuntimeError("A network error occurred while reading the Gemini response.") from None
    except RuntimeError as error:
        if str(error) == "Gemini response exceeded the 1 MB size limit.":
            raise
        raise RuntimeError("An unexpected error occurred while communicating with Gemini.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Gemini API returned invalid JSON.") from None
    except Exception:
        raise RuntimeError("An unexpected error occurred while communicating with Gemini.") from None

    if not isinstance(result, dict):
        raise RuntimeError("Gemini returned an invalid response.")

    prompt_feedback = result.get("promptFeedback")
    if isinstance(prompt_feedback, dict) and prompt_feedback.get("blockReason"):
        raise RuntimeError("Gemini blocked the prompt under its safety rules.")

    candidates = result.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Gemini returned no valid candidates.")

    answer = ""
    safety_blocked = False
    output_incomplete = False

    safety_reasons = {
        "SAFETY", "RECITATION", "BLOCKLIST",
        "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY"
    }

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        finish_reason = candidate.get("finishReason")
        if finish_reason in safety_reasons:
            safety_blocked = True
            continue
        if finish_reason == "MAX_TOKENS":
            output_incomplete = True
            continue

        content = candidate.get("content")
        if not isinstance(content, dict):
            continue

        parts = content.get("parts")
        if not isinstance(parts, list):
            continue

        candidate_text = "\n".join(
            part["text"] for part in parts
            if isinstance(part, dict)
            and isinstance(part.get("text"), str)
            and part["text"].strip()
        ).strip()

        if candidate_text:
            answer = candidate_text
            break

    if not answer:
        if safety_blocked:
            raise RuntimeError("Gemini blocked the response under its safety rules.")
        if output_incomplete:
            raise RuntimeError("Gemini response was incomplete because it reached the output limit.")
        raise RuntimeError("Gemini returned no usable text in its candidates.")

    return answer


if __name__ == "__main__":
    try:
        print("Neha:", ask_gemini("Introduce yourself in one sentence."))
    except Exception as error:
        print("Connection failed:", error)
