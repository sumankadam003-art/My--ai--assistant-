import unittest
from unittest.mock import patch

from src.neha_gateway import NehaGateway


class NehaGatewayTests(unittest.TestCase):
    def test_common_words_do_not_make_unrelated_cloud_memory_relevant(self):
        gateway = NehaGateway()
        records = [
            {"memory": "I am a doctor"},
            {"memory": "Astronomy is my favorite subject"},
        ]
        with patch("src.neha_gateway.select_relevant_memories", return_value=[]), patch(
            "src.neha_gateway.load_cloud_memories", return_value=records
        ):
            memories = gateway._get_memories(
                "Tell me about astronomy", user_id="owner-1"
            )

        self.assertEqual(memories, ["Astronomy is my favorite subject"])

    def test_stopword_only_prompt_does_not_pull_arbitrary_cloud_memories(self):
        gateway = NehaGateway()
        with patch("src.neha_gateway.select_relevant_memories", return_value=[]), patch(
            "src.neha_gateway.load_cloud_memories",
            return_value=[{"memory": "I am a doctor"}],
        ):
            memories = gateway._get_memories("about it", user_id="owner-1")

        self.assertEqual(memories, [])

    def test_cloud_failure_preserves_local_memories(self):
        gateway = NehaGateway()
        with patch(
            "src.neha_gateway.select_relevant_memories",
            return_value=["Local astronomy fact"],
        ), patch("src.neha_gateway.load_cloud_memories", return_value=None):
            memories = gateway._get_memories("astronomy", user_id="owner-1")

        self.assertEqual(memories, ["Local astronomy fact"])


if __name__ == "__main__":
    unittest.main()
