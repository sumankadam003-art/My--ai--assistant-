import subprocess
import json
import re

def run_action(action):
    action = action.lower().strip()
    if "volume" in action or "mute music" in action:
        try:
            result = subprocess.run(
                ["termux-volume"],
                capture_output=True, text=True, timeout=10
            )
            streams = json.loads(result.stdout)
            music = next(x for x in streams if x["stream"] == "music")
            current = music["volume"]
            maximum = music["max_volume"]

            if "mute" in action:
                target = 0
            elif any(w in action for w in ("up", "increase", "raise")):
                target = min(current + 2, maximum)
            elif any(w in action for w in ("down", "decrease", "lower")):
                target = max(current - 2, 0)
            else:
                return f"Music volume: {current}/{maximum}"

            subprocess.run(
                ["termux-volume", "music", str(target)],
                check=True, timeout=10
            )
            return f"Music volume set to {target}/{maximum}"
        except FileNotFoundError:
            return "Volume control unavailable. Check Termux:API installation."
        except subprocess.TimeoutExpired:
            return "Volume control timed out. Please try again."
        except (json.JSONDecodeError, StopIteration, KeyError, TypeError, ValueError):
            return "Could not read volume information. Check Termux:API."
        except Exception:
            return "Volume control failed unexpectedly."

    if "camera" in action and any(
        word in action for word in ("open", "launch", "start")
    ):
        try:
            result = subprocess.run(
                ["am", "start", "-a", "android.media.action.IMAGE_CAPTURE"],
                capture_output=True, text=True, timeout=15
            )
            return "Camera opened." if result.returncode == 0 else (
                result.stderr.strip() or "Could not open camera."
            )
        except FileNotFoundError:
            return "Camera unavailable: Android activity command not found."
        except subprocess.TimeoutExpired:
            return "Camera launch timed out. Please try again."
        except Exception:
            return "Could not open the camera."


    if any(word in action for word in ("battery", "charge", "power level")):
        command = ["termux-battery-status"]
    elif "toast" in action or "popup" in action:
        command = ["termux-toast", "Hello! Neha is here."]
    elif "speak" in action or "talk" in action:
        command = ["termux-tts-speak", "Hello! I am Neha."]
    else:
        match = re.search(r"\b(?:open|launch|start)\s+(.+)", action)
        if not match:
            return "I don't know that action yet."

        app = match.group(1).strip()
        app = re.sub(r"\s+(for me|please|now|the app)$", "", app).strip()
        app = app.rstrip("?.!,").strip()
        app = re.sub(r"\s+(for me|please|now|the app)$", "", app).strip()
        apps = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "gmail": "https://mail.google.com",
            "maps": "https://maps.google.com",
            "instagram": "https://www.instagram.com",
        }

        if app not in apps:
            return f"App '{app}' isn't configured yet."

        command = ["termux-open-url", apps[app]]

    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return result.stderr.strip() or "Action failed."

        if command[0] == "termux-battery-status":
            data = json.loads(result.stdout)
            return f"Battery is at {data.get('percentage', 'unknown')} percent."

        return "Done."
    except FileNotFoundError:
        return f"Required command '{command[0]}' was not found. Check Termux:API."
    except subprocess.TimeoutExpired:
        return "Action timed out. Please try again."
    except json.JSONDecodeError:
        return "Received invalid data from the Android service."
    except Exception:
        return "Action failed unexpectedly. Please try again."
