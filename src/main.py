import json
import os
from pathlib import Path
from local_owner_auth import LocalOwnerAuth, OwnerAccountError
from intent_interpreter import interpret_request
from actions import run_action
from plugin_manager import ActionPluginManager
from memory_sync import save_memory_safely
from neha_gateway import NehaGateway
from web_search import web_search
from voice import listen, speak
from memory_brain import suggest_memories
from memory import load_memories, save_memory, delete_memory
from chat_history import load_history, save_history

class BrainManager:
    def __init__(self):
        self.brains = {}

    def register(self, name, brain):
        self.brains[name] = brain

    def ask(self, prompt, history=None):
        if not self.brains:
            return "No AI brain configured yet. Add a provider first."
        for name, brain in self.brains.items():
            try:
                if name == "Neha-Groq":
                    return f"[{name}] {brain(prompt, history)}"
                return f"[{name}] {brain(prompt)}"
            except Exception as e:
                print(f"{name} failed: {e}")
        return "All configured AI brains failed."

def approve_action(description):
    print(f"Neha: Sir, should I {description} to help you?")
    answer = input("Approve? (yes/no): ").strip().lower()
    return answer in ("yes", "y")




def execute_plugin(plugin_manager, name, description):
    if not approve_action(description):
        print("Neha: Okay, sir. Cancelled.")
        return
    result = plugin_manager.execute(name, approved=True)
    print("Neha:", result["message"])


def _termux_login():
    auth = LocalOwnerAuth(session_ttl_seconds=None)
    session_path = Path("data/termux_session.json")
    session_path.parent.mkdir(parents=True, exist_ok=True)
    token = None
    try:
        saved = json.loads(session_path.read_text(encoding="utf-8"))
        token = saved.get("access_token") if isinstance(saved, dict) else None
    except (OSError, ValueError):
        token = None
    if token and auth.verify_session(token):
        return auth, token
    session_path.unlink(missing_ok=True)
    challenge = auth.create_challenge()
    print("Neha owner challenge:", challenge["challenge"])
    answer = input("Login response: ").strip()
    result = auth.login_challenge(challenge["challenge_id"], answer)
    if not result:
        raise SystemExit("Login failed or challenge expired. Restart Neha for a new challenge.")
    token = result["access_token"]
    temp = session_path.with_suffix(".tmp")
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"access_token": token}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, session_path)
    os.chmod(session_path, 0o600)
    return auth, token


def main():
    auth, session_token = _termux_login()
    manager = NehaGateway()
    action_manager = ActionPluginManager()
    builtins = {
        "battery": ("battery", "device.battery"),
        "volume up": ("volume up", "device.volume"),
        "volume down": ("volume down", "device.volume"),
        "mute music": ("mute music", "device.volume"),
        "camera": ("open camera", "device.camera"),
        "open youtube": ("open youtube", "app.youtube"),
        "open google": ("open google", "app.google"),
        "open gmail": ("open gmail", "app.gmail"),
        "open maps": ("open maps", "app.maps"),
        "open instagram": ("open instagram", "app.instagram"),
        "toast": ("toast", "device.notification"),
        "speak": ("speak", "device.speech"),
    }
    for name, (command, permission) in builtins.items():
        action_manager.register(
            name, name.replace("_", " "), 
            lambda command=command: run_action(command),
            permission, True,
            "device" if permission.startswith("device.") else "apps"
        )
    print("My AI Assistant — Multi-Brain Core")
    print("Type 'exit' to quit.")
    history = load_history()
    messages_since_memory_check = 0
    while True:
        prompt = input("\nYou (or /voice): ").strip()

        if prompt == "/voice":
            try:
                speak("I am listening")
            except Exception as e:
                print(f"Speech output unavailable: {e}")

            prompt = listen()

            if not prompt or not prompt.strip():
                print("I couldn't hear you. Please try again.")
                continue

            prompt = prompt.strip()
            print("You said:", prompt)
        if prompt.lower() in ("exit", "quit"):
            break

        if prompt.lower() == "/logout":
            auth.logout(session_token)
            Path("data/termux_session.json").unlink(missing_ok=True)
            print("Neha: Logged out. A fresh challenge is required next time.")
            break

        if prompt == "/memories":
            for i, fact in enumerate(load_memories(), 1):
                print(f"{i}. {fact}")
            continue

        if prompt == "/remember":
            fact = input("Memory to save: ").strip()
            if fact and input("Save memory? (y/yes/no): ").strip().lower() in ("y", "yes"):
                status = save_memory_safely(fact)
                messages = {
                    "cloud": "Saved to cloud.",
                    "cloud_local_failed": "Saved to cloud, but local backup failed.",
                    "queued": "Saved locally; queued for cloud sync.",
                    "local_only": "Saved locally, but could not queue cloud sync.",
                    "failed": "Save failed; memory was not confirmed saved.",
                }
                print("Neha:", messages.get(status, "Unknown save status."))
            continue

        if prompt == "/forget":
            memories = load_memories()
            for i, fact in enumerate(memories, 1):
                print(f"{i}. {fact}")
            try:
                index = int(input("Number to forget: ")) - 1
                if 0 <= index < len(memories):
                    print(f"Selected memory: {memories[index]}")
                    confirm = input("Permanently delete this memory? (yes/no): ").strip().lower()
                    if confirm in ("yes", "y"):
                        print("Deleted." if delete_memory(index) else "Deletion failed.")
                    else:
                        print("Deletion cancelled.")
                else:
                    print("Invalid number.")
            except ValueError:
                print("Enter a valid number.")
            continue

        natural = prompt.lower().strip().rstrip("?!.")

        search_prefixes = (
            "/search ",
            "search the web for ",
            "search online for ",
            "search the internet for ",
            "look up ",
            "find online ",
            "look for ",
            "search for ",
            "find the latest ",
            "latest news about ",
        )

        matched_prefix = next(
            (prefix for prefix in search_prefixes
             if prompt.lower().startswith(prefix)),
            None
        )

        if matched_prefix:
            query = prompt[len(matched_prefix):].strip()
            print("Neha:", web_search(query))
            continue

        if prompt.lower() == "/search":
            print("Neha: Please provide a search query.")
            continue

        if any(word in natural for word in (
            "battery", "how much charge", "power level"
        )):
            execute_plugin(action_manager, "battery", "check your battery level")
            continue

        if natural.startswith(("open ", "launch ", "start ")):
            app = natural.split(maxsplit=1)[1].strip().rstrip("?.!,")
            for suffix in (" for me", " please", " now", " the app"):
                if app.endswith(suffix):
                    app = app[:-len(suffix)].strip()
            name = "camera" if app == "camera" else "open " + app
            if action_manager.get_action(name):
                execute_plugin(action_manager, name, natural)
            else:
                print("Neha: That app isn't registered yet.")
            continue

        if prompt.lower() in ("/battery", "/toast", "/speak"):
            action = prompt.lower().replace("/", "")
            execute_plugin(action_manager, action, action)
            continue

        action_verbs = (
            "open", "launch", "start", "increase", "decrease",
            "raise", "lower", "mute", "take", "click", "capture",
            "turn on", "turn off",
        )
        action_targets = (
            "battery", "charge", "power level", "volume", "music",
            "camera", "youtube", "google", "gmail", "maps",
            "instagram", "photo", "picture",
        )
        needs_action_interpretation = (
            bool(prompt)
            and any(word in natural for word in action_verbs)
            and any(word in natural for word in action_targets)
        )
        interpreted = (
            interpret_request(prompt)
            if needs_action_interpretation
            else {"type": "chat"}
        )
        if interpreted.get("type") == "action":
            action = interpreted["action"]
            action_commands = {
                "battery": ("battery", "check your battery level"),
                "volume up": ("volume up", "increase the volume"),
                "volume down": ("volume down", "decrease the volume"),
                "mute music": ("mute music", "mute the music"),
                "camera": ("open camera", "open the camera"),
                "open youtube": ("open youtube", "open YouTube"),
                "open google": ("open google", "open Google"),
                "open gmail": ("open gmail", "open Gmail"),
                "open maps": ("open maps", "open Maps"),
                "open instagram": ("open instagram", "open Instagram"),
            }
            if action not in action_commands:
                print("Neha: Sorry, I don't support that action yet.")
                continue

            command, description = action_commands[action]
            name = "camera" if action == "camera" else action
            execute_plugin(action_manager, name, description)
            continue

        if prompt:
            try:
                answer = manager.ask(prompt, history)
            except Exception as e:
                print(f"Neha: I couldn't get an AI response. Please try again. ({e})")
                continue

            print("Assistant:", answer)
            try:
                speak(answer)
            except Exception as e:
                print(f"Speech output unavailable: {e}")

            history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer}
            ])
            history = history[-40:]
            if not save_history(history):
                print("Neha: Warning: conversation history could not be saved.")

            messages_since_memory_check += 2
            if messages_since_memory_check >= 6:
                messages_since_memory_check = 0
                conversation = "\n".join(
                    f"{m['role']}: {m['content']}"
                    for m in history[-6:]
                )
                try:
                    suggested_facts = suggest_memories(conversation)
                except Exception as e:
                    print(f"Neha: Memory suggestions unavailable: {e}")
                    suggested_facts = []

                for fact in suggested_facts:
                    if fact not in load_memories():
                        print(f"Neha suggests saving: {fact}")
                        if input("Save this memory? (y/n): ").strip().lower() in ("y", "yes"):
                            status = save_memory_safely(fact)
                            messages = {
                                "cloud": "Saved to cloud and locally.",
                                "cloud_local_failed": "Saved to cloud, but local backup failed.",
                                "queued": "Saved locally; queued for cloud sync.",
                                "local_only": "Saved locally, but could not queue cloud sync.",
                                "failed": "Save failed; memory was not confirmed saved.",
                            }
                            print("Neha:", messages.get(status, "Memory save status unknown."))


if __name__ == "__main__":
    main()
