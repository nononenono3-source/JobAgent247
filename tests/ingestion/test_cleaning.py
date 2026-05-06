import unittest

from jobagent247.ingestion.cleaning import (
    categorize_job,
    detect_remote,
    estimate_years_experience,
    is_entry_level,
    is_senior_level,
)


class TestIngestionCleaning(unittest.TestCase):
    def test_estimate_years_experience(self):
        self.assertEqual(estimate_years_experience("Requires 3+ years of experience"), 3)
        self.assertEqual(estimate_years_experience("5 years of Python"), 5)
        self.assertEqual(estimate_years_experience("minimum 2 yrs"), 2)
        self.assertIsNone(estimate_years_experience("No experience required"))

    def test_is_entry_level(self):
        self.assertTrue(is_entry_level("Junior Software Engineer", ""))
        self.assertTrue(is_entry_level("Fresher Opening", ""))
        self.assertFalse(is_entry_level("Senior Developer", ""))

    def test_is_senior_level(self):
        self.assertTrue(is_senior_level("Senior Software Engineer", ""))
        self.assertTrue(is_senior_level("Lead Developer", ""))
        self.assertFalse(is_senior_level("Junior Developer", ""))

    def test_detect_remote(self):
        self.assertTrue(detect_remote("Remote", ""))
        self.assertTrue(detect_remote("Work from home", ""))
        self.assertFalse(detect_remote("Office-based", ""))

    def test_categorize_job(self):
        self.assertEqual(
            categorize_job(title="Junior Developer", description="0-1 years experience"),
            "fresher",
        )
        self.assertEqual(
            categorize_job(title="Senior Engineer", description="5+ years experience"),
            "pro",
        )
        self.assertEqual(
            categorize_job(title="Software Engineer", description=""),
            "uncategorized",
        )


if __name__ == "__main__":
    unittest.main()
