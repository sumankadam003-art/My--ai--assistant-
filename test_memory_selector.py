import unittest
from unittest.mock import patch

from memory_selector import select_relevant_memories


class MemorySelectorTests(unittest.TestCase):
    @patch("memory_selector.load_memories", return_value=[
        "I am a doctor", "I love astronomy"
    ])
    def test_common_words_do_not_outscore_topic_match(self, _load):
        self.assertEqual(
            select_relevant_memories("I am asking about astronomy"),
            ["I love astronomy"],
        )

    @patch("memory_selector.load_memories", return_value=[
        "I love astronomy", "I enjoy cooking"
    ])
    def test_relevant_memory_is_selected(self, _load):
        self.assertEqual(
            select_relevant_memories("Tell me about astronomy"),
            ["I love astronomy"],
        )


