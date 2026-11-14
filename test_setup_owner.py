import unittest
from unittest.mock import Mock, patch

from src import setup_owner
from src.local_owner_auth import OwnerAccountError


class SetupOwnerTests(unittest.TestCase):
    def test_corrupt_existing_owner_record_is_reported_and_preserved(self):
        auth = Mock()
        auth.is_configured.return_value = True
        auth._read_record.side_effect = OwnerAccountError(
            "Owner account is missing or unreadable."
        )

        with patch.object(setup_owner, "LocalOwnerAuth", return_value=auth), patch(
            "builtins.print"
        ) as printed, patch("builtins.input") as input_prompt:
            result = setup_owner.main()

        self.assertEqual(result, 1)
        input_prompt.assert_not_called()
        auth.setup.assert_not_called()
        self.assertIn(
            "unreadable",
            " ".join(str(call) for call in printed.call_args_list).lower(),
        )

    def test_valid_existing_owner_record_is_not_overwritten(self):
        auth = Mock()
        auth.is_configured.return_value = True
        auth._read_record.return_value = {"username": "owner"}

        with patch.object(setup_owner, "LocalOwnerAuth", return_value=auth), patch(
            "builtins.print"
        ), patch("builtins.input") as input_prompt:
            result = setup_owner.main()

        self.assertEqual(result, 1)
        input_prompt.assert_not_called()
        auth.setup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
