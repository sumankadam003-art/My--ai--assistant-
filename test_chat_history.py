import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import chat_history


class ChatHistoryTests(unittest.TestCase):
    def test_save_history_returns_false_when_parent_directory_creation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not-a-directory"
            blocker.write_text("block", encoding="utf-8")
            history_file = blocker / "conversation_history.json"

            with patch.object(chat_history, "HISTORY_FILE", history_file):
                result = chat_history.save_history([{"role": "user", "content": "hello"}])

            self.assertFalse(result)

    def test_save_history_writes_valid_history(self):
        with tempfile.TemporaryDirectory() as directory:
            history_file = Path(directory) / "conversation_history.json"

            with patch.object(chat_history, "HISTORY_FILE", history_file):
                result = chat_history.save_history([{"role": "user", "content": "hello"}])

            self.assertTrue(result)
            self.assertEqual(
                chat_history.load_history() if history_file == chat_history.HISTORY_FILE else
                __import__("json").loads(history_file.read_text(encoding="utf-8")),
                [{"role": "user", "content": "hello"}],
            )


if __name__ == "__main__":
    unittest.main()
