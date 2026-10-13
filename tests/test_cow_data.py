"""Offline checks that the CoW catalog, manifest and committed 5-row samples agree."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cow_data  # noqa: E402
from contracts.schema import Dataset  # noqa: E402


class CowCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datasets, cls.manifest = cow_data.load_catalog()

    def test_every_entry_is_a_valid_real_dataset(self):
        for dataset_id, row in self.datasets.items():
            parsed = Dataset.model_validate(row)
            self.assertFalse(parsed.is_sample, dataset_id)
            names = [v.name for v in parsed.variables]
            self.assertEqual(len(names), len(set(names)), dataset_id)

    def test_manifest_points_at_the_cow_site(self):
        for dataset_id, info in self.manifest.items():
            self.assertTrue(info["url"].startswith("https://correlatesofwar.org/wp-content/uploads/"), dataset_id)
            self.assertIn(info["delimiter"], {",", "\t"}, dataset_id)

    def test_samples_match_declared_variables(self):
        for dataset_id, row in self.datasets.items():
            problems = cow_data.verify_sample(
                row, cow_data.sample_path_for(dataset_id), self.manifest[dataset_id]["delimiter"])
            self.assertEqual(problems, [], dataset_id)

    def test_broken_sample_is_reported(self):
        row = dict(next(iter(self.datasets.values())))
        row = {**row, "variables": row["variables"] + [{"name": "not_a_column", "description": "x"}]}
        first = next(iter(self.datasets))
        problems = cow_data.verify_sample(row, cow_data.sample_path_for(first), self.manifest[first]["delimiter"])
        self.assertTrue(any("not_a_column" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
