import unittest
from unittest.mock import patch

import memory_sync


class MemorySyncTests(unittest.TestCase):

    @patch("memory.save_memory", return_value=True)
    @patch("cloud_memory.save_cloud_memory", return_value=True)
    def test_immediate_save_does_not_pass_token_as_category(
        self, cloud_save, local_save
    ):
        result = memory_sync.save_memory_safely(
            "Test memory", "owner-1", "secret-token"
        )

        self.assertEqual(result, "cloud")
        cloud_save.assert_called_once_with("owner-1", "Test memory")

    @patch("memory_sync.remove_pending", return_value=True)
    @patch("memory_sync.load_pending")
    @patch("cloud_memory.save_cloud_memory", return_value=True)
    def test_pending_sync_preserves_category(
        self, cloud_save, load_pending, remove_pending
    ):
        load_pending.return_value = [
            {"memory": "Test memory", "category": "personal"}
        ]

        result = memory_sync.sync_pending_memories(
            "owner-1", "secret-token"
        )

        self.assertEqual(result, 1)
        cloud_save.assert_called_once_with(
            "owner-1", "Test memory", category="personal"
        )
        remove_pending.assert_called_once_with("Test memory")

    @patch("memory._read_memories", return_value=["Local memory"])
    @patch("cloud_memory.load_cloud_memories", return_value=[])
    @patch("cloud_memory.save_cloud_memory", return_value=True)
    def test_local_sync_does_not_pass_token_as_category(
        self, cloud_save, cloud_load, local_read
    ):
        result = memory_sync.sync_all_local_memories(
            "owner-1", "secret-token"
        )

        self.assertEqual(result, 1)
        cloud_save.assert_called_once_with("owner-1", "Local memory")


if __name__ == "__main__":
    unittest.main()
