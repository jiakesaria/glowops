"""Offline behavioral tests for Jia's components; separate from D's benchmark."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import OpenAI

from checker import CheckerError, InputDataError, check, fake_check, load_inputs
from config import ROOT, ConfigurationError, Settings, create_client, get_config
from contracts.schema import LedgerRecord


class SequenceClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": [dict(x) for x in kwargs["messages"]]})
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=result), finish_reason="stop")])


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "contracts", self.root / "contracts")
        (self.root / "data").mkdir()
        self.settings = Settings(root=self.root, model_id="test-model", api_key="test-key")
        self.fixture = json.loads((self.root / "contracts/sample_verdict.json").read_text())
        self.hypothesis = self.fixture["hypothesis"]

    def response(self, **changes):
        return json.dumps({**self.fixture, **changes})

    def records(self):
        return [LedgerRecord.model_validate_json(line) for line in
                (self.root / "data/ledger.jsonl").read_text().splitlines()]

    def write_lessons(self, rows):
        (self.root / "data/lessons.json").write_text(json.dumps(rows))

    def test_fake_needs_no_key_and_logs_each_call_once(self):
        with patch("checker.create_client", side_effect=AssertionError("No network allowed")):
            for text in ("First hypothesis", "Second hypothesis"):
                verdict = fake_check(text, settings=Settings(root=self.root))
                self.assertEqual(verdict.hypothesis, text)
        records = self.records()
        self.assertEqual(len(records), 2)
        self.assertTrue(all(x.mode == "fake" and x.corpus_is_sample for x in records))
        self.assertTrue(all(not x.applied_lesson_ids for x in records))

    def test_real_call_with_samples_has_sample_flag(self):
        client = SequenceClient([self.response()])
        result = check(self.hypothesis, settings=self.settings, client=client,
                       run_id="run-1", split="learn", test_id="case-1")
        self.assertEqual(result.decision, "proceed")
        record = self.records()[0]
        self.assertEqual(record.run_id, "run-1")
        self.assertEqual(record.test_id, "case-1")
        self.assertTrue(record.corpus_is_sample)
        self.assertEqual(record.mode, "real")
        self.assertEqual(record.applied_lesson_ids, [])

    def test_malformed_json_retries_and_logs_only_final_verdict(self):
        client = SequenceClient(["not JSON", self.response()])
        check(self.hypothesis, settings=self.settings, client=client)
        self.assertEqual(len(client.calls), 2)
        self.assertIn("failed validation", client.calls[1]["messages"][-1]["content"])
        self.assertEqual(len(self.records()), 1)

    def test_invented_paper_variable_dataset_and_years_are_repaired(self):
        for kind in ("paper", "variable", "dataset", "years", "hypothesis"):
            with self.subTest(kind=kind):
                bad = json.loads(self.response())
                if kind == "paper":
                    bad["already_tested"]["citations"][0]["paper_id"] = "invented"
                elif kind == "variable":
                    bad["testable_with_available_data"]["matches"][0]["variable_names"] = ["invented"]
                elif kind == "dataset":
                    bad["testable_with_available_data"]["matches"][0]["dataset_id"] = "invented"
                elif kind == "years":
                    bad["testable_with_available_data"]["required_years"]["start"] = 1800
                else:
                    bad["hypothesis"] = "Changed input"
                client = SequenceClient([json.dumps(bad), self.response()])
                check(self.hypothesis, settings=self.settings, client=client)
                self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(self.records()), 5)

    def test_exhausted_retries_do_not_create_verdict_log(self):
        client = SequenceClient(["", "{}", "not JSON"])
        with self.assertRaises(CheckerError):
            check(self.hypothesis, settings=self.settings, client=client)
        self.assertEqual(len(client.calls), 3)
        self.assertFalse((self.root / "data/ledger.jsonl").exists())

    def test_provider_failure_is_not_faked_or_logged(self):
        client = SequenceClient([RuntimeError("Provider unavailable")])
        with self.assertRaises(RuntimeError):
            check(self.hypothesis, settings=self.settings, client=client)
        self.assertFalse((self.root / "data/ledger.jsonl").exists())

    def test_existing_empty_real_files_do_not_fall_back(self):
        for name in ("papers.json", "cow_vars.txt"):
            (self.root / "data" / name).write_text("[]" if name.endswith(".json") else "")
        self.write_lessons([])
        papers, datasets, lessons, sample = load_inputs(self.settings, round=1)
        self.assertEqual((papers, datasets, lessons, sample), ([], [], [], False))

    def test_malformed_real_file_fails_without_model_call(self):
        (self.root / "data/papers.json").write_text("not JSON")
        client = SequenceClient([])
        with self.assertRaises(InputDataError):
            check(self.hypothesis, settings=self.settings, client=client)
        self.assertEqual(client.calls, [])

    def test_duplicate_ids_fail(self):
        row = json.loads((self.root / "contracts/sample_papers.json").read_text())[0]
        (self.root / "data/papers.json").write_text(json.dumps([row, row]))
        with self.assertRaises(InputDataError):
            load_inputs(self.settings)

    def test_real_files_replace_samples_without_code_changes(self):
        for real, sample in (("papers.json", "sample_papers.json"), ("cow_vars.txt", "sample_cow_vars.txt")):
            text = (self.root / "contracts" / sample).read_text()
            if sample.endswith(".json"):
                rows = json.loads(text)
            else:
                rows = [json.loads(line) for line in text.splitlines()]
            for row in rows:
                row["is_sample"] = False
            output = json.dumps(rows) if real.endswith(".json") else "\n".join(json.dumps(row) for row in rows)
            (self.root / "data" / real).write_text(output)
        # Fictional contents here exercise loading; they do not become real evidence.
        self.assertFalse(load_inputs(self.settings)[3])

    def test_lessons_are_approved_model_scoped_round_scoped_and_capped(self):
        base = json.loads((self.root / "contracts/sample_lessons.json").read_text())[0]
        rows = [{**base, "id": f"lesson-{i:02}", "model": "test-model"} for i in range(12)]
        rows += [{**base, "id": "pending", "model": "test-model", "approved": False},
                 {**base, "id": "other-model", "model": "other-model"},
                 {**base, "id": "future", "model": "test-model", "round": 3}]
        self.write_lessons(rows)
        self.assertEqual(load_inputs(self.settings, round=0)[2], [])
        selected = load_inputs(self.settings, round=1)[2]
        self.assertEqual([x.id for x in selected], [f"lesson-{i:02}" for i in range(10)])
        client = SequenceClient([self.response()])
        check(self.hypothesis, settings=self.settings, client=client, round=1)
        self.assertEqual(self.records()[0].applied_lesson_ids, [x.id for x in selected])

    def test_holdout_lessons_are_rejected(self):
        lesson = json.loads((self.root / "contracts/sample_lessons.json").read_text())[0]
        self.write_lessons([{**lesson, "source_split": "holdout"}])
        with self.assertRaises(InputDataError):
            load_inputs(self.settings, round=1)

    def test_no_gold_labels_or_test_file_in_model_context(self):
        (self.root / "data/tests.json").write_text('{"expected_decision": "SECRET_GOLD_LABEL"}')
        client = SequenceClient([self.response()])
        check(self.hypothesis, settings=self.settings, client=client)
        prompt = json.dumps(client.calls[0]["messages"])
        self.assertNotIn("SECRET_GOLD_LABEL", prompt)
        self.assertNotIn("expected_decision", prompt)

    def test_empty_hypothesis_and_bad_metadata_fail_before_request(self):
        client = SequenceClient([])
        for text, kwargs in ((" ", {}), (self.hypothesis, {"round": -1}),
                             (self.hypothesis, {"split": "holdout"})):
            with self.assertRaises(ValueError):
                check(text, settings=self.settings, client=client, **kwargs)
        self.assertEqual(client.calls, [])

    def test_configuration_environment_precedence_and_no_secret_repr(self):
        (self.root / ".env").write_text("MODEL=deepseek\nDEEPSEEK_API_KEY=file-key\nDEEPSEEK_MODEL=file-model\n")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "environment-secret"}, clear=True):
            settings = get_config(root=self.root)
        self.assertEqual(settings.api_key, "environment-secret")
        self.assertEqual(settings.model_id, "file-model")
        self.assertNotIn("environment-secret", repr(settings))
        with patch.dict(os.environ, {"MODEL": "unknown"}, clear=True):
            with self.assertRaises(ConfigurationError):
                get_config(root=self.root)

    def test_real_client_requires_credentials(self):
        with self.assertRaises(ConfigurationError):
            create_client(Settings(root=self.root))

    def test_openai_sdk_request_flow_for_both_providers_without_network(self):
        for provider in ("deepseek", "qwen"):
            with self.subTest(provider=provider):
                requests = []
                def respond(request):
                    requests.append(json.loads(request.content))
                    return httpx.Response(200, json={
                        "id": "mock-completion", "object": "chat.completion", "created": 1,
                        "model": "test-model", "choices": [{"index": 0, "finish_reason": "stop",
                        "message": {"role": "assistant", "content": self.response()}}]})
                settings = self.settings.model_copy(update={"provider": provider})
                with OpenAI(api_key="test-key", base_url="https://mock.invalid/v1",
                            http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
                    check(self.hypothesis, settings=settings, client=client)
                self.assertEqual(requests[0]["model"], "test-model")
                self.assertEqual(requests[0]["response_format"], {"type": "json_object"})

    def test_ledger_write_error_propagates(self):
        client = SequenceClient([self.response()])
        with self.assertRaises(OSError):
            check(self.hypothesis, settings=self.settings, client=client, ledger_path=self.root / "data")


if __name__ == "__main__":
    unittest.main()
