import json
import os
import tempfile
import unittest
from pathlib import Path

from src.action_audit import JsonlActionAudit


class JsonlActionAuditTests(unittest.TestCase):
    def test_writes_only_allowlisted_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "logs" / "actions.jsonl"
            audit = JsonlActionAudit(path)
            audit({
                "timestamp": 123.5,
                "request_id": "request-1",
                "actor": "owner",
                "action": "camera.open",
                "status": "executed_unverified",
                "password": "must-not-be-written",
                "arguments": {"secret": "must-not-be-written"},
            })

            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(row["request_id"], "request-1")
            self.assertNotIn("password", row)
            self.assertNotIn("arguments", row)
            self.assertNotIn("must-not-be-written", path.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions required")
    def test_creates_log_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "actions.jsonl"
            JsonlActionAudit(path)({"action": "test", "status": "denied"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_rejects_non_dictionary_event(self):
        with tempfile.TemporaryDirectory() as folder:
            audit = JsonlActionAudit(Path(folder) / "actions.jsonl")
            with self.assertRaises(TypeError):
                audit("not-an-event")


if __name__ == "__main__":
    unittest.main()
