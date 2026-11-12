import subprocess


def listen():
    try:
        result = subprocess.run(
            ["termux-speech-to-text"],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print("Neha: Voice recognition failed. Please try again.")
            return ""

        text = result.stdout.strip()
        if not text:
            print("Neha: I didn't catch that. Please speak again.")
            return ""

        return text

    except FileNotFoundError:
        print("Neha: Voice input is unavailable. Check Termux:API.")
    except subprocess.TimeoutExpired:
        print("Neha: Listening timed out. Please try again.")
    except Exception:
        print("Neha: An unexpected voice input error occurred.")

    return ""


def speak(text):
    if not isinstance(text, str) or not text.strip():
        return False

    try:
        result = subprocess.run(
            ["termux-tts-speak", text],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print("Neha: Speech output failed. Check your TTS settings.")
            return False

        return True

    except FileNotFoundError:
        print("Neha: Speech output is unavailable. Check Termux:API.")
    except subprocess.TimeoutExpired:
        print("Neha: Speech output timed out.")
    except Exception:
        print("Neha: An unexpected speech output error occurred.")

    return False
