import json
import os
import unittest
from unittest.mock import mock_open, patch

from jobagent247.state.db import save_jobs, load_jobs
from jobagent247.state.models import Job


class TestStateDb(unittest.TestCase):
    def test_save_and_load_jobs(self):
        jobs = [
            Job(
                category="pro",
                title="Software Engineer",
                company="Google",
                location="Mountain View, CA",
                is_remote=False,
                salary_min=100000,
                salary_max=200000,
                salary_currency="USD",
                url="https://google.com/careers",
                description="A job at Google.",
                source="google",
                country="us",
            )
        ]
        path = "test_jobs.json"

        save_jobs(jobs=jobs, path=path)

        self.assertTrue(os.path.exists(path))

        loaded_jobs = load_jobs(path=path)
        self.assertEqual(len(loaded_jobs), 1)
        self.assertEqual(loaded_jobs[0].title, "Software Engineer")

        os.remove(path)


if __name__ == "__main__":
    unittest.main()
