"""Validate shared fixtures and critical invariants, without model/API access."""

import json
from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError

from contracts.schema import Dataset, Failure, LedgerRecord, Lesson, Paper, TestCase, Verdict

ROOT = Path(__file__).resolve().parent


def read_json(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def read_lines(name, model):
    return [
        model.model_validate_json(line)
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def expect_invalid(model, payload):
    try:
        model.model_validate(payload)
    except ValidationError:
        return
    raise AssertionError(f"{model.__name__} accepted an invalid contract")


def unique_ids(items):
    assert len({item.id for item in items}) == len(items), "duplicate IDs"


def main():
    papers = [Paper.model_validate(x) for x in read_json("sample_papers.json")]
    datasets = [Dataset.model_validate(x) for x in read_json("sample_cow_vars.json")]
    tests = [TestCase.model_validate(x) for x in read_json("sample_tests.json")]
    failures = [Failure.model_validate(x) for x in read_json("sample_failures.json")]
    lessons = [Lesson.model_validate(x) for x in read_json("sample_lessons.json")]
    payload = read_json("sample_verdict.json")
    verdict = Verdict.model_validate(payload)
    for rows in (papers, datasets, tests, lessons):
        unique_ids(rows)
    assert all(x.is_sample for x in papers + datasets)
    assert {x.decision for x in [verdict]} == {"proceed"}
    assert {x.expected_decision for x in tests} == {"proceed", "revise", "reject"}

    paper_ids = {x.id for x in papers}
    variables = {x.id: {v.name for v in x.variables} for x in datasets}
    test_by_id = {x.id: x for x in tests}
    for result in [verdict] + [x.actual_verdict for x in failures]:
        assert all(c.paper_id in paper_ids for c in result.already_tested.citations)
        for match in result.testable_with_available_data.matches:
            assert match.dataset_id in variables
            assert set(match.variable_names) <= variables[match.dataset_id]
    for failure in failures:
        case = test_by_id[failure.test_id]
        assert failure.split == case.split == "learn"
        assert failure.hypothesis == case.hypothesis
        assert failure.expected_decision == case.expected_decision
    for lesson in lessons:
        assert all(test_by_id[t].split == "learn" for t in lesson.source_test_ids)
    assert {x.approved for x in lessons} == {True, False}

    LedgerRecord.model_validate({
        "timestamp_utc": "2026-10-10T18:00:00Z", "run_id": "fixture-validation",
        "model": "fake", "mode": "fake", "round": 0, "split": "learn",
        "test_id": tests[0].id, "corpus_is_sample": True,
        "applied_lesson_ids": [], "verdict": payload,
    })
    assert Verdict.model_validate_json(verdict.model_dump_json()) == verdict

    bad = deepcopy(payload)
    bad["falsifiable"]["status"] = "unknown"
    expect_invalid(Verdict, bad)
    bad = deepcopy(payload)
    bad["testable_with_available_data"]["status"] = "partial"
    bad["testable_with_available_data"]["missing_requirements"] = ["No non-war cases"]
    expect_invalid(Verdict, bad)
    bad = deepcopy(payload)
    bad["already_tested"]["citations"] = []
    expect_invalid(Verdict, bad)
    bad = deepcopy(payload)
    bad["testable_with_available_data"]["missing_requirements"] = ["Outcome missing"]
    expect_invalid(Verdict, bad)
    bad = lessons[0].model_dump()
    bad["source_split"] = "holdout"
    expect_invalid(Lesson, bad)
    bad = failures[0].model_dump()
    bad["actual_verdict"]["decision"] = bad["expected_decision"]
    expect_invalid(Failure, bad)
    bad = deepcopy(payload)
    bad["unexpected_field"] = "typo"
    expect_invalid(Verdict, bad)
    print("PASS: all six sample files, evidence references, ledger format, and seven rejection checks.")


if __name__ == "__main__":
    main()
