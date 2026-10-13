"""Offline tests for improve.py (lesson proposals, guards, review commands)."""

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import improve  # noqa: E402
from checker import load_inputs  # noqa: E402
from config import Settings  # noqa: E402
from contracts.schema import Lesson  # noqa: E402

MODEL = "test-model"


class FakeClient:
    """Returns queued message bodies, like an OpenAI-compatible chat client."""

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
        reply = next(self.replies)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=reply), finish_reason="stop")])


def ops(*items):
    return json.dumps({"operations": list(items)})


class ImproveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "contracts", self.root / "contracts")
        (self.root / "data").mkdir()
        self.settings = Settings(root=self.root, model_id=MODEL, api_key="k")
        sample = json.loads((self.root / "contracts/sample_failures.json").read_text())
        self.failures = [{**f, "model": MODEL, "round": 1} for f in sample]
        self.ids = [f["test_id"] for f in self.failures]
        self.write_failures(self.failures)

    # helpers
    def write_failures(self, rows):
        (self.root / "data/failures.json").write_text(json.dumps(rows))

    def lessons(self):
        path = self.root / "data/lessons.json"
        return [Lesson.model_validate(x) for x in json.loads(path.read_text())] if path.exists() else []

    def propose(self, client, **kw):
        lines = []
        created = improve.propose(None, round=kw.pop("round", 1), settings=self.settings, client=client,
                                  out=lines.append, **kw)
        return created, lines

    def two_adds(self):
        return ops({"op": "ADD", "failure_ids": [self.ids[0]], "target_id": None, "tag": "prior_research",
                    "text": "Earlier studies do not justify rejection when an extension is feasible."},
                   {"op": "ADD", "failure_ids": [self.ids[1]], "target_id": None, "tag": "falsifiability",
                    "text": "Ask for operational definitions and scope before proceeding."})

    def run_cli(self, argv, **kw):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = improve.main(argv, settings=self.settings, **kw)
        return code, out.getvalue(), err.getvalue()

    # proposals
    def test_add_creates_pending_lessons_with_sources_and_ids(self):
        created, _ = self.propose(FakeClient([self.two_adds()]))
        self.assertEqual([x.id for x in created], ["test-model-r1-01", "test-model-r1-02"])
        saved = self.lessons()
        self.assertTrue(all(not x.approved and x.model == MODEL and x.round == 1 and x.source_split == "learn"
                            for x in saved))
        self.assertEqual(saved[0].source_test_ids, [self.ids[0]])
        log = (self.root / "data/improve_log.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(log[0])["created"], ["test-model-r1-01", "test-model-r1-02"])

    def test_edit_makes_new_pending_lesson_and_keeps_the_old_one(self):
        self.propose(FakeClient([self.two_adds()]))
        improve.set_approval(self.settings, ["test-model-r1-01"], True, out=lambda *_: None)
        self.write_failures([{**self.failures[0], "test_id": "other-1", "round": 2}])
        reply = ops({"op": "EDIT", "failure_ids": ["other-1"], "target_id": "test-model-r1-01", "tag": "decision",
                     "text": "Treat earlier studies as grounds for replication, never as grounds for rejection."})
        created, lines = self.propose(FakeClient([reply]), round=2)
        self.assertEqual(created[0].id, "test-model-r2-01")
        self.assertEqual(created[0].source_test_ids, [self.ids[0], "other-1"])
        old = next(x for x in self.lessons() if x.id == "test-model-r1-01")
        self.assertTrue(old.approved)
        self.assertTrue(any("unapprove test-model-r1-01" in line for line in lines))

    def test_noop_adds_nothing_but_is_reported(self):
        self.propose(FakeClient([self.two_adds()]))
        self.write_failures([{**self.failures[0], "test_id": "other-1", "round": 2}])
        reply = ops({"op": "NOOP", "failure_ids": ["other-1"], "target_id": "test-model-r1-01", "tag": None, "text": None})
        created, lines = self.propose(FakeClient([reply]), round=2)
        self.assertEqual(created, [])
        self.assertEqual(len(self.lessons()), 2)
        self.assertTrue(any(line.startswith("NOOP") for line in lines))

    def test_invalid_reply_is_retried_with_the_error(self):
        bad = ops({"op": "ADD", "failure_ids": [self.ids[0]], "target_id": None, "tag": "decision", "text": "Too short."})
        client = FakeClient([bad, self.two_adds()])
        created, _ = self.propose(client)
        self.assertEqual(len(created), 2)
        self.assertEqual(len(client.calls), 2)
        self.assertIn("exactly once", client.calls[1]["messages"][-1]["content"])

    def test_gives_up_after_the_retry_limit(self):
        with self.assertRaises(improve.ImproveError):
            self.propose(FakeClient(["not json"] * 3))
        self.assertEqual(self.lessons(), [])

    def test_text_that_repeats_a_test_is_rejected(self):
        phrase = " ".join(self.failures[0]["hypothesis"].split()[:6])
        leaky = ops({"op": "ADD", "failure_ids": self.ids, "target_id": None, "tag": "decision", "text": phrase + "."})
        client = FakeClient([leaky, self.two_adds()])
        self.propose(client)
        self.assertIn("repeats wording", client.calls[1]["messages"][-1]["content"])

    def test_text_rules(self):
        failures = improve.load_failures(self.root / "data/failures.json")
        for bad in ("", "Line one.\nLine two.", "Do this. Then do that.", " ".join(["word"] * 31),
                    f"Applies to {self.ids[0]} only"):
            with self.assertRaises(ValueError, msg=bad):
                improve.check_text(bad, failures)
        improve.check_text("Prefer revise over reject when a definition can repair the idea.", failures)

    # guards
    def test_holdout_failures_never_produce_lessons(self):
        self.write_failures([{**self.failures[0], "split": "holdout"}])
        client = FakeClient([])
        with self.assertRaisesRegex(improve.ImproveError, "learning-split"):
            self.propose(client)
        self.assertEqual(client.calls, [])

    def test_wrong_model_or_round_is_refused(self):
        self.write_failures([{**self.failures[0], "model": "someone-else"}])
        with self.assertRaisesRegex(improve.ImproveError, "someone-else"):
            self.propose(FakeClient([]))
        self.write_failures(self.failures)
        with self.assertRaisesRegex(improve.ImproveError, "round"):
            self.propose(FakeClient([]), round=2)

    def test_tests_json_blocks_a_holdout_test_id(self):
        tests = [{"id": tid, "hypothesis": "h", "split": "holdout", "expected_decision": "revise", "rationale": "r"}
                 for tid in self.ids]
        (self.root / "data/tests.json").write_text(json.dumps(tests))
        with self.assertRaisesRegex(improve.ImproveError, "holdout"):
            self.propose(FakeClient([]))

    def test_rerun_is_blocked_without_force(self):
        self.propose(FakeClient([self.two_adds()]))
        with self.assertRaisesRegex(improve.ImproveError, "already processed"):
            self.propose(FakeClient([]))
        created, _ = self.propose(FakeClient([self.two_adds()]), force=True)
        self.assertEqual([x.id for x in created], ["test-model-r1-03", "test-model-r1-04"])

    def test_dry_run_writes_nothing(self):
        self.propose(FakeClient([self.two_adds()]), dry_run=True)
        self.assertFalse((self.root / "data/lessons.json").exists())
        self.assertFalse((self.root / "data/improve_log.jsonl").exists())

    # fake mode
    def test_fake_mode_needs_no_key_or_network(self):
        settings = Settings(root=self.root)  # no model, no key
        lines = []
        created = improve.propose(self.root / "contracts/sample_failures.json", round=0, settings=settings,
                                  fake=True, out=lines.append)
        self.assertEqual(len(created), 2)
        self.assertTrue(all(x.model == "fake" and not x.approved for x in created))
        code, _, _ = self.run_cli(["status", "--round", "0", "--fake"])
        self.assertEqual(code, improve.EXIT_PENDING)

    # review
    def test_review_commands_and_status(self):
        self.propose(FakeClient([self.two_adds()]))
        code, out, _ = self.run_cli(["status", "--round", "1", "--model", "deepseek"])
        self.assertEqual(code, improve.EXIT_PENDING)
        self.assertEqual(self.run_cli(["approve", "test-model-r1-01"])[0], 0)
        self.assertEqual(self.run_cli(["reject", "test-model-r1-01"])[0], 1)  # approved ones are not deleted
        self.assertEqual(self.run_cli(["reject", "test-model-r1-02"])[0], 0)
        self.assertEqual([x.id for x in self.lessons()], ["test-model-r1-01"])
        self.assertEqual(self.run_cli(["status", "--round", "1", "--model", "deepseek"])[0], 0)
        self.assertEqual(self.run_cli(["approve", "missing-id"])[0], 1)
        self.assertEqual(self.run_cli(["unapprove", "test-model-r1-01"])[0], 0)
        self.assertFalse(self.lessons()[0].approved)

    def test_checker_only_sees_approved_lessons_of_its_model(self):
        self.propose(FakeClient([self.two_adds()]))
        self.assertEqual(load_inputs(self.settings, round=1)[2], [])
        improve.set_approval(self.settings, ["test-model-r1-02"], True, out=lambda *_: None)
        seen = load_inputs(self.settings, round=1)[2]
        self.assertEqual([x.id for x in seen], ["test-model-r1-02"])
        other = Settings(root=self.root, model_id="other-model")
        self.assertEqual(load_inputs(other, round=1)[2], [])

    def test_cap_warning(self):
        settings = Settings(root=self.root, model_id=MODEL, api_key="k", max_approved_lessons=1)
        self.settings = settings
        _, lines = self.propose(FakeClient([self.two_adds()]))
        self.assertTrue(any("exceeds the checker's limit" in line for line in lines))

    def test_cli_reports_errors_without_a_traceback(self):
        self.write_failures([{**self.failures[0], "split": "holdout"}])
        code, _, err = self.run_cli([str(self.root / "data/failures.json"), "--round", "1"])
        self.assertEqual(code, 1)
        self.assertIn("improve failed", err)


if __name__ == "__main__":
    unittest.main()
