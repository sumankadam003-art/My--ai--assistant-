import unittest
from unittest.mock import patch

import memory_brain


class MemoryBrainSafetyTests(unittest.TestCase):
    def test_rejects_added_negation(self):
        self.assertFalse(memory_brain._is_grounded_suggestion(
            "I am not available", "I am available"
        ))

    def test_rejects_removed_negation(self):
        self.assertFalse(memory_brain._is_grounded_suggestion(
            "I am available", "I am not available"
        ))

    def test_accepts_matching_positive_statement(self):
        self.assertTrue(memory_brain._is_grounded_suggestion(
            "I enjoy astronomy", "I enjoy astronomy and reading"
        ))

    def test_accepts_matching_negative_statement(self):
        self.assertTrue(memory_brain._is_grounded_suggestion(
            "I do not enjoy astronomy", "I do not enjoy astronomy"
        ))

    def test_rejects_allergy_information(self):
        self.assertTrue(memory_brain._contains_obvious_secret(
            "I have severe allergies to peanuts"
        ))

    def test_rejects_medical_condition_and_medication_information(self):
        self.assertTrue(memory_brain._contains_obvious_secret(
            "I take medication for hypertension"
        ))

    def test_rejects_pregnancy_information(self):
        self.assertTrue(memory_brain._contains_obvious_secret(
            "I am pregnant"
        ))


if __name__ == "__main__":
    unittest.main()
