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
    @patch("cloud_memory.load_cloud_memories", return_value=[], autospec=True)
    @patch("cloud_memory.save_cloud_memory", return_value=True)
    def test_local_sync_calls_cloud_loader_with_user_id_only(
        self, cloud_save, cloud_load, local_read
    ):
        result = memory_sync.sync_all_local_memories(
            "owner-1", "legacy-token"
        )

        self.assertEqual(result, 1)
        cloud_load.assert_called_once_with("owner-1")
        cloud_save.assert_called_once_with("owner-1", "Local memory")

    @patch("memory._read_memories", return_value=["Local memory"])
    @patch("cloud_memory.load_cloud_memories", return_value=[])
    @patch("cloud_memory.save_cloud_memory", return_value=True)
    def test_local_sync_works_without_access_token(
        self, cloud_save, cloud_load, local_read
    ):
        result = memory_sync.sync_all_local_memories(user_id="owner-1")

        self.assertEqual(result, 1)
        cloud_load.assert_called_once_with("owner-1")
        cloud_save.assert_called_once_with("owner-1", "Local memory")

    @patch("memory_sync.remove_pending", return_value=True)
    @patch("memory_sync.load_pending")
    @patch("cloud_memory.save_cloud_memory", return_value=True)
    def test_pending_sync_works_without_access_token(
        self, cloud_save, load_pending, remove_pending
    ):
        load_pending.return_value = [{"memory": "Queued memory"}]

        result = memory_sync.sync_pending_memories(user_id="owner-1")

        self.assertEqual(result, 1)
        cloud_save.assert_called_once_with(
            "owner-1", "Queued memory", category="general"
        )
        remove_pending.assert_called_once_with("Queued memory")

    @patch("memory_sync.remove_pending", return_value=True)
    @patch("memory_sync.load_pending")
    @patch("cloud_memory.save_cloud_memory", return_value=True)
    def test_invalid_pending_category_falls_back_to_general(
        self, cloud_save, load_pending, remove_pending
    ):
        load_pending.return_value = [
            {"memory": "Queued memory", "category": {"unexpected": "object"}}
        ]

        result = memory_sync.sync_pending_memories("owner-1")

        self.assertEqual(result, 1)
        cloud_save.assert_called_once_with(
            "owner-1", "Queued memory", category="general"
        )
        remove_pending.assert_called_once_with("Queued memory")

    @patch("memory_sync.remove_pending")
    @patch("memory_sync.load_pending")
    @patch("cloud_memory.save_cloud_memory", return_value=False)
    def test_failed_cloud_upload_keeps_pending_memory(
        self, cloud_save, load_pending, remove_pending
    ):
        load_pending.return_value = [{"memory": "Retry me"}]

        result = memory_sync.sync_pending_memories("owner-1")

        self.assertEqual(result, 0)
        cloud_save.assert_called_once_with(
            "owner-1", "Retry me", category="general"
        )
        remove_pending.assert_not_called()

    @patch("memory_sync.remove_pending", return_value=False)
    @patch("memory_sync.load_pending")
    @patch("cloud_memory.save_cloud_memory", return_value=True)
    def test_pending_count_only_includes_successful_local_removal(
        self, cloud_save, load_pending, remove_pending
    ):
        load_pending.return_value = [{"memory": "Keep until removed"}]

        result = memory_sync.sync_pending_memories("owner-1")

        self.assertEqual(result, 0)
        remove_pending.assert_called_once_with("Keep until removed")

    @patch("memory.save_memory", return_value=True)
    @patch("cloud_memory.save_cloud_memory", return_value=True)
    def test_owner_id_allows_cloud_save_without_access_token(
        self, cloud_save, local_save
    ):
        result = memory_sync.save_memory_safely(
            "Owner memory", user_id="owner-1"
        )
        self.assertEqual(result, "cloud")
        cloud_save.assert_called_once_with("owner-1", "Owner memory")


if __name__ == "__main__":
    unittest.main()
