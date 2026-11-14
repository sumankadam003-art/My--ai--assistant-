import asyncio
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

try:
    import telegram_bot
except ModuleNotFoundError:
    telegram_bot = None


@unittest.skipIf(telegram_bot is None, "python-telegram-bot dependency is not installed")
class TelegramBotTests(unittest.TestCase):
    def test_missing_config_file_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "missing.env"
            with self.assertRaisesRegex(RuntimeError, "was not found"):
                telegram_bot.load_config(missing)

    def test_corrupt_history_is_reported_instead_of_becoming_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            history_dir = Path(folder)
            (history_dir / "123.json").write_text("{broken", encoding="utf-8")
            with patch.object(telegram_bot, "HISTORY_DIR", history_dir):
                self.assertIsNone(telegram_bot.load_user_history(123))

    def test_missing_history_is_a_valid_empty_history(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(telegram_bot, "HISTORY_DIR", Path(folder)):
                self.assertEqual(telegram_bot.load_user_history(123), [])

    def test_pending_suggestions_expire(self):
        now = time.time()
        pending = {
            "old": {"fact": "old fact", "created_at": now - 1000},
            "new": {"fact": "new fact", "created_at": now},
        }

        telegram_bot.prune_pending_memories(pending, now=now)

        self.assertEqual(set(pending), {"new"})

    def test_pending_suggestions_are_capped(self):
        now = time.time()
        pending = {
            str(index): {"fact": f"fact {index}", "created_at": now + index}
            for index in range(telegram_bot.MAX_PENDING_MEMORIES)
        }

        telegram_bot.add_pending_memory(pending, "new", "new fact", now=now + 100)

        self.assertEqual(len(pending), telegram_bot.MAX_PENDING_MEMORIES)
        self.assertIn("new", pending)

    def test_telegram_chat_uses_configured_cloud_owner_identity(self):
        async def run():
            update = SimpleNamespace(
                message=SimpleNamespace(text="hello"),
                effective_user=SimpleNamespace(id=77),
                effective_chat=SimpleNamespace(type="private"),
            )
            context = SimpleNamespace(
                application=SimpleNamespace(bot_data={"allowed_id": "77"}),
                user_data={},
            )
            with patch.object(telegram_bot, "NEHA_CLOUD_OWNER_ID", "cloud-owner"), patch.object(
                telegram_bot, "load_user_history", return_value=[]
            ), patch.object(telegram_bot, "save_user_history", return_value=True), patch.object(
                telegram_bot, "safe_reply", new_callable=AsyncMock, return_value=True
            ), patch.object(
                telegram_bot, "suggest_memories", return_value=[]
            ), patch.object(
                telegram_bot.gateway, "ask", return_value="hello back"
            ) as ask:
                await telegram_bot.handle_message(update, context)

            ask.assert_called_once_with(
                "hello", [], user_id="cloud-owner"
            )

        asyncio.run(run())

    def test_approved_telegram_memory_uses_cloud_aware_save(self):
        async def run():
            memory_id = "a" * 12
            query = SimpleNamespace(
                message=SimpleNamespace(chat=SimpleNamespace(type="private")),
                data=f"mem_save:{memory_id}",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
            )
            update = SimpleNamespace(
                callback_query=query,
                effective_user=SimpleNamespace(id=77),
            )
            context = SimpleNamespace(
                application=SimpleNamespace(bot_data={"allowed_id": "77"}),
                user_data={
                    "pending_memories": {
                        memory_id: {
                            "fact": "A saved fact",
                            "created_at": time.time(),
                        }
                    }
                },
            )
            with patch.object(telegram_bot, "NEHA_CLOUD_OWNER_ID", "cloud-owner"), patch.object(
                telegram_bot, "save_memory_safely", return_value="queued"
            ) as save:
                await telegram_bot.handle_memory_decision(update, context)

            save.assert_called_once_with(
                "A saved fact", user_id="cloud-owner"
            )
            self.assertNotIn(memory_id, context.user_data["pending_memories"])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
