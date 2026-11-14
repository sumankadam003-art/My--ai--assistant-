import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from neha_gateway import NehaGateway
from memory_sync import save_memory_safely
from cloud_memory import NEHA_CLOUD_OWNER_ID
from memory_brain import suggest_memories


logger = logging.getLogger(__name__)

gateway = NehaGateway()

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = Path.home() / ".config/neha-assistant/.env"
HISTORY_DIR = BASE_DIR / "data" / "telegram_history"
PENDING_MEMORY_TTL_SECONDS = 15 * 60
MAX_PENDING_MEMORIES = 20


def load_config(path=CONFIG_FILE):
    try:
        raw_config = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise RuntimeError(
            f"Telegram configuration file was not found: {path}"
        ) from error
    except OSError as error:
        raise RuntimeError(
            f"Telegram configuration file cannot be read: {path}"
        ) from error

    config = {}
    for line in raw_config.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    return config


def load_user_history(user_id):
    path = HISTORY_DIR / f"{user_id}.json"

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        return None

    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None

    if not isinstance(data, list):
        return None

    # Refuse to silently discard malformed records: handle_message must not
    # overwrite the original history until the owner has repaired it.
    if any(
        not isinstance(item, dict)
        or item.get("role") not in ("user", "assistant")
        or not isinstance(item.get("content"), str)
        or not item["content"].strip()
        for item in data
    ):
        return None

    return data[-40:]


def prune_pending_memories(pending, now=None):
    """Remove malformed and expired suggestions from Telegram user state."""
    if not isinstance(pending, dict):
        return {}
    current_time = time.time() if now is None else now
    for memory_id, entry in list(pending.items()):
        if not isinstance(entry, dict):
            pending.pop(memory_id, None)
            continue
        created_at = entry.get("created_at")
        if (
            isinstance(created_at, bool)
            or not isinstance(created_at, (int, float))
            or created_at > current_time
            or current_time - created_at > PENDING_MEMORY_TTL_SECONDS
            or not isinstance(entry.get("fact"), str)
            or not entry["fact"].strip()
        ):
            pending.pop(memory_id, None)
    return pending


def add_pending_memory(pending, memory_id, fact, now=None):
    """Add a suggestion while enforcing expiry and a strict per-user cap."""
    current_time = time.time() if now is None else now
    pending = prune_pending_memories(pending, current_time)
    if len(pending) >= MAX_PENDING_MEMORIES:
        oldest_id = min(
            pending,
            key=lambda key: pending[key]["created_at"],
        )
        pending.pop(oldest_id, None)
    pending[memory_id] = {
        "fact": fact,
        "created_at": current_time,
    }
    return pending


def save_user_history(user_id, history):
    HISTORY_DIR.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )
    os.chmod(HISTORY_DIR, 0o700)

    path = HISTORY_DIR / f"{user_id}.json"
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=HISTORY_DIR,
            prefix=f".{user_id}.",
            suffix=".tmp",
            delete=False,
        ) as temp:
            json.dump(
                history[-40:],
                temp,
                ensure_ascii=False,
                indent=2,
            )
            temp.flush()
            os.fsync(temp.fileno())
            temp_path = Path(temp.name)

        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
        os.chmod(path, 0o600)

    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def get_user_lock(context, user_id):
    locks = context.application.bot_data.setdefault(
        "_telegram_user_locks", {}
    )

    user_key = str(user_id)

    if user_key not in locks:
        locks[user_key] = asyncio.Lock()

    return locks[user_key]


async def safe_reply(message, text, **kwargs):
    try:
        await message.reply_text(text, **kwargs)
        return True

    except TelegramError as error:
        logger.warning(
            "Telegram message delivery failed (%s).",
            type(error).__name__,
        )
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (
        update.message is None
        or update.effective_user is None
        or update.effective_chat is None
        or update.effective_chat.type != "private"
    ):
        return

    await safe_reply(
        update.message,
        f"Hi! I'm Neha. Your Telegram ID is: "
        f"{update.effective_user.id}\n\n"
        "Keep this ID private. The owner must configure it before "
        "I can access private memories."
    )


async def handle_memory_decision(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    user = update.effective_user
    message = query.message

    if user is None or message is None:
        await query.answer("Invalid request.")
        return

    if message.chat.type != "private":
        await query.answer("Private chat required.", show_alert=True)
        return

    allowed_id = context.application.bot_data.get("allowed_id")

    if not allowed_id or str(user.id) != str(allowed_id):
        await query.answer("Access denied.", show_alert=True)
        return

    parts = (query.data or "").split(":", 1)

    if len(parts) != 2:
        await query.answer("Invalid request.")
        return

    action, memory_id = parts
    pending = context.user_data.get("pending_memories")
    if not isinstance(pending, dict):
        pending = {}
    context.user_data["pending_memories"] = prune_pending_memories(pending)
    pending = context.user_data["pending_memories"]
    entry = pending.get(memory_id)
    fact = entry.get("fact") if isinstance(entry, dict) else None

    if not fact:
        await query.answer("This suggestion has expired.")
        return

    if action == "mem_save":
        try:
            save_status = save_memory_safely(
                fact,
                user_id=NEHA_CLOUD_OWNER_ID or None,
            )
            saved = save_status != "failed"
        except Exception as error:
            logger.warning(
                "Memory save failed (%s).",
                type(error).__name__,
            )
            saved = False

        if not saved:
            await query.answer("Could not save this memory.")
            return

        pending.pop(memory_id, None)
        response = "Saved to Neha's memory."

    elif action == "mem_reject":
        pending.pop(memory_id, None)
        response = "Memory suggestion rejected."

    else:
        await query.answer("Invalid action.")
        return

    await query.answer(response)

    try:
        await query.edit_message_text(response)
    except TelegramError as error:
        logger.warning(
            "Memory decision message update failed (%s).",
            type(error).__name__,
        )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        update is None
        or update.message is None
        or update.effective_user is None
        or update.effective_chat is None
    ):
        return

    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id
    allowed_id = context.application.bot_data.get("allowed_id")

    if not allowed_id or str(user_id) != str(allowed_id):
        await safe_reply(
            update.message,
            "Access isn't configured for this account yet.",
        )
        return

    prompt = (update.message.text or "").strip()

    if not prompt:
        return

    # Serialize the entire conversation operation for this user.
    lock = get_user_lock(context, user_id)

    async with lock:
        history = load_user_history(user_id)
        if history is None:
            await safe_reply(
                update.message,
                "Your saved conversation history is unreadable. "
                "I have preserved the file and will not overwrite it.",
            )
            return

        try:
            answer = gateway.ask(
                prompt,
                history,
                user_id=NEHA_CLOUD_OWNER_ID or None,
            )

            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Invalid AI response.")

            answer = answer.strip()

        except Exception as error:
            logger.warning(
                "Neha AI request failed (%s).",
                type(error).__name__,
            )
            await safe_reply(
                update.message,
                "I'm having trouble connecting to my AI brain. "
                "Please try again.",
            )
            return

        history.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer},
        ])

        try:
            save_user_history(user_id, history)
        except (OSError, TypeError, ValueError) as error:
            logger.warning(
                "Telegram history save failed (%s).",
                type(error).__name__,
            )

        delivered = await safe_reply(
            update.message,
            answer[:4000],
        )

        if not delivered:
            return

        # Generate suggestions, but never save without approval.
        try:
            conversation = f"User: {prompt}\nNeha: {answer}"
            suggestions = suggest_memories(conversation)
        except Exception as error:
            logger.warning(
                "Memory suggestion generation failed (%s).",
                type(error).__name__,
            )
            return

        if not isinstance(suggestions, list):
            return

        for fact in suggestions:
            if not isinstance(fact, str) or not fact.strip():
                continue

            fact = fact.strip()
            memory_id = uuid.uuid4().hex[:12]

            pending = context.user_data.get("pending_memories")
            if not isinstance(pending, dict):
                pending = {}
            context.user_data["pending_memories"] = add_pending_memory(
                pending, memory_id, fact
            )

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "Save",
                        callback_data=f"mem_save:{memory_id}",
                    ),
                    InlineKeyboardButton(
                        "Reject",
                        callback_data=f"mem_reject:{memory_id}",
                    ),
                ]
            ])

            sent = await safe_reply(
                update.message,
                f"Should I remember this?\n\n{fact}",
                reply_markup=keyboard,
            )

            if not sent:
                context.user_data["pending_memories"].pop(
                    memory_id, None
                )


def main():
    config = load_config()
    token = config.get("TELEGRAM_BOT_TOKEN", "")
    allowed_id = config.get("TELEGRAM_ALLOWED_USER_ID", "")

    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing from .env"
        )

    app = Application.builder().token(token).build()
    app.bot_data["allowed_id"] = allowed_id

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        CallbackQueryHandler(
            handle_memory_decision,
            pattern=r"^mem_(?:save|reject):[0-9a-f]{12}$",
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    print("Neha Telegram bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
