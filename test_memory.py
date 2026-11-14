import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memory


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.memory_path = Path(self.temp.name) / "memory.json"
        self.patch_path = patch.object(memory, "MEMORY_FILE", self.memory_path)
        self.patch_path.start()

    def tearDown(self):
        self.patch_path.stop()
        self.temp.cleanup()

    def test_missing_memory_file_is_a_valid_empty_store(self):
        self.assertEqual(memory.load_memories(), [])

    def test_corrupt_memory_file_raises_instead_of_looking_empty(self):
        self.memory_path.write_text("{broken json", encoding="utf-8")
        with self.assertRaises(memory.MemoryStoreError):
            memory.load_memories()

    def test_invalid_memory_shape_raises_instead_of_looking_empty(self):
        self.memory_path.write_text('{"memory": "not a list"}', encoding="utf-8")
        with self.assertRaises(memory.MemoryStoreError):
            memory.load_memories()


if __name__ == "__main__":
    unittest.main()
