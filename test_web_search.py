import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web_search


class WebSearchConfigurationTests(unittest.TestCase):
    def test_missing_env_file_reports_configuration_error(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_file = Path(directory) / ".env"
            with patch.object(web_search, "KEY_FILE", missing_file):
                result = web_search.web_search("test query")

        self.assertIn("Web search configuration error:", result)
        self.assertIn(".env file was not found", result)

    def test_missing_tavily_key_reports_configuration_error(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("OTHER_SETTING=value\\n", encoding="utf-8")
            with patch.object(web_search, "KEY_FILE", env_file):
                result = web_search.web_search("test query")

        self.assertIn("Web search configuration error:", result)
        self.assertIn("TAVILY_API_KEY is missing", result)

    def test_valid_key_returns_search_summary(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps({"answer": "A test summary.", "results": []}).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("TAVILY_API_KEY=test-key\\n", encoding="utf-8")
            with patch.object(web_search, "KEY_FILE", env_file):
                with patch.object(web_search.urllib.request, "urlopen", return_value=FakeResponse()):
                    result = web_search.web_search("test query")

        self.assertEqual(result, "Summary: A test summary.")


if __name__ == "__main__":
    unittest.main()
