import json
try:
    from .groq_brain import ask_groq, MAX_PROMPT_CHARS
except ImportError:
    from groq_brain import ask_groq, MAX_PROMPT_CHARS

ALLOWED_ACTIONS = {
    "battery",
    "volume up",
    "volume down",
    "mute music",
    "camera",
    "open youtube",
    "open google",
    "open gmail",
    "open maps",
    "open instagram",
}

def interpret_request(prompt):
    if not isinstance(prompt, str) or not prompt.strip():
        return {"type": "chat"}

    instruction = """
You classify requests for Neha, an Android assistant.
Return ONLY valid JSON with this structure:
{"type":"chat"}
or
{"type":"action","action":"ACTION_NAME"}

Allowed actions:
battery, volume up, volume down, mute music, camera,
open youtube, open google, open gmail, open maps, open instagram.

Map a request to an allowed action only when its intent is clear.
If no allowed action matches, return {"type":"chat"}.
Never invent actions or commands.
User request:
""" + prompt

    if len(instruction) > MAX_PROMPT_CHARS:
        return {
            "type": "error",
            "message": "Action request is too long to interpret."
        }

    try:
        result = ask_groq(instruction)
        if not isinstance(result, str):
            return {"type": "chat"}

        data = json.loads(result)
        if not isinstance(data, dict):
            return {"type": "chat"}

        if (
            data.get("type") == "action"
            and isinstance(data.get("action"), str)
            and data.get("action") in ALLOWED_ACTIONS
        ):
            return {"type": "action", "action": data["action"]}

        return {"type": "chat"}
    except (ValueError, TypeError, KeyError):
        return {"type": "chat"}
    except Exception:
        return {"type": "chat"}
