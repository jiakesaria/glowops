"""The evidence validator's messages must tell a retrying model what it may use instead."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from checker import validate_evidence  # noqa: E402
from contracts.schema import Dataset, Paper, Verdict  # noqa: E402


class ValidatorMessageTests(unittest.TestCase):
    def setUp(self):
        contracts = ROOT / "contracts"
        self.payload = json.loads((contracts / "sample_verdict.json").read_text())
        self.papers = [Paper.model_validate(x) for x in json.loads((contracts / "sample_papers.json").read_text())]
        self.datasets = [Dataset.model_validate(x) for x in json.loads((contracts / "sample_cow_vars.json").read_text())]

    def error(self, mutate):
        mutate(self.payload)
        verdict = Verdict.model_validate(self.payload)
        with self.assertRaises(ValueError) as caught:
            validate_evidence(verdict, verdict.hypothesis, self.papers, self.datasets)
        return str(caught.exception)

    def test_untouched_sample_verdict_passes(self):
        verdict = Verdict.model_validate(self.payload)
        validate_evidence(verdict, verdict.hypothesis, self.papers, self.datasets)

    def test_years_error_states_both_ranges_and_the_options(self):
        message = self.error(lambda p: p["testable_with_available_data"]["required_years"].update(start=1800))
        self.assertIn("sample-dyads-001 covers 1999-2010", message)
        self.assertIn("required_years is 1800-2010", message)
        self.assertIn("status partial", message)

    def test_unknown_paper_lists_valid_ids(self):
        message = self.error(lambda p: p["already_tested"]["citations"][0].update(paper_id="invented"))
        self.assertIn("invented", message)
        self.assertIn("sample-paper-001", message)

    def test_unknown_dataset_lists_valid_ids(self):
        message = self.error(lambda p: p["testable_with_available_data"]["matches"][0].update(dataset_id="invented"))
        self.assertIn("valid IDs", message)
        self.assertIn("sample-dyads-001", message)

    def test_unknown_variable_lists_the_dataset_variables(self):
        message = self.error(lambda p: p["testable_with_available_data"]["matches"][0].update(variable_names=["made_up"]))
        self.assertIn("made_up", message)
        self.assertIn("bilateral_trade", message)


if __name__ == "__main__":
    unittest.main()
