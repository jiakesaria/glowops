"""Amitej's evaluation runner, integrated with the team's shared contracts."""
import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from config import ROOT, get_config
from contracts.schema import Failure, TestCase, Verdict

DECISIONS = ("proceed", "revise", "reject")


class CheckerExecutionError(RuntimeError):
    def __init__(self, error_type):
        self.error_type = error_type
        super().__init__(error_type)


def input_hashes():
    names = ("data/papers.json", "data/cow_vars.json", "data/tests.json", "checker.py",
             "screening.py", "jev.py", "improve.py", "contracts/schema.py")
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in names if (ROOT / name).exists()}


def load_cases(path):
    rows = [TestCase.model_validate(row) for row in read_json(path)]
    if not rows or len({row.id for row in rows}) != len(rows):
        raise ValueError("Tests must be nonempty and have unique IDs.")
    return rows


def worker(payload):
    # Only the hypothesis and logging metadata reach the checker, never gold labels.
    from checker import check, fake_check
    function = fake_check if payload.pop("fake") else check
    if payload.pop("with_jev") and function is check:
        from screening import check_with_jev
        function = check_with_jev
    try:
        result = function(**payload)
        return {"ok": True, "response": result.model_dump(mode="json")}
    except Exception as exc:
        # Provider errors may embed credentials or request bodies; save only the type.
        return {"ok": False, "error": type(exc).__name__}


def call_checker(case, *, fake, with_jev, round_number, run_id, timeout):
    payload = {"hypothesis": case.hypothesis, "fake": fake, "with_jev": with_jev,
               "round": round_number, "run_id": run_id, "split": case.split, "test_id": case.id}
    process = subprocess.run([sys.executable, str(ROOT / "run_tests.py"), "--worker"],
                             input=json.dumps(payload), text=True, capture_output=True,
                             cwd=ROOT, timeout=timeout)
    if process.returncode:
        raise RuntimeError("Checker process failed; consult safe API telemetry.")
    value = json.loads(process.stdout)
    if not value["ok"]:
        raise CheckerExecutionError(value["error"])
    return Verdict.model_validate(value["response"])


def evaluate_case(case, call):
    row = {"id": case.id, "hypothesis": case.hypothesis, "split": case.split,
           "expected_decision": case.expected_decision, "rationale": case.rationale,
           "actual_decision": None, "status": "error", "response": None, "error": None}
    try:
        verdict = Verdict.model_validate(call(case))
        if verdict.hypothesis != case.hypothesis:
            raise ValueError("Checker returned a different hypothesis")
        row.update(response=verdict.model_dump(mode="json"), actual_decision=verdict.decision,
                   status="match" if verdict.decision == case.expected_decision else "mismatch")
    except Exception as exc:
        row["error"] = getattr(exc, "error_type", type(exc).__name__)
    return row


def format_failures(rows, *, round_number, model):
    # Service errors have no Verdict and cannot become research lessons.
    return [Failure(test_id=r["id"], split="learn", round=round_number, model=model,
                    hypothesis=r["hypothesis"], expected_decision=r["expected_decision"],
                    rationale=r["rationale"], actual_verdict=r["response"]).model_dump(mode="json")
            for r in rows if r["split"] == "learn" and r["status"] == "mismatch"]


def run_evaluation(cases, output, *, fake=False, with_jev=False, round_number=0,
                   timeout=150, failure_output=None, call=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    run_id = output.name
    settings = get_config()
    model = "fake" if fake else settings.model_id
    write_json(output / "tests_snapshot.json", [c.model_dump() for c in cases])
    write_json(output / "manifest.json", {"mode": "fake" if fake else "real", "model": model,
        "with_jev": with_jev, "round": round_number, "run_id": run_id,
        "request_limits": {"provider_timeout_seconds": settings.timeout_seconds,
            "case_timeout_seconds": timeout, "max_json_retries": settings.max_json_retries,
            "max_output_tokens": settings.max_tokens},
        "input_sha256": input_hashes(),
        "lesson_file_sha256": hashlib.sha256((ROOT / "data/lessons.json").read_bytes()).hexdigest()
            if (ROOT / "data/lessons.json").exists() else None,
        "benchmark_status": "draft answer key; needs team review"})
    if call is None:
        call = lambda case: call_checker(case, fake=fake, with_jev=with_jev,
            round_number=round_number, run_id=run_id, timeout=timeout)
    rows = []
    with (output / "results.jsonl").open("w", encoding="utf-8") as stream:
        for case in cases:
            row = evaluate_case(case, call)
            rows.append(row)
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            print(f"{case.id}: {row['actual_decision'] or 'ERROR'} (expected {case.expected_decision})", flush=True)
    summary = summarize(rows)
    summary.update(mode="fake" if fake else "real", model=model, with_jev=with_jev,
                   round=round_number, benchmark_status="draft")
    write_json(output / "summary.json", summary)
    if any(c.split == "learn" for c in cases):
        failures = format_failures(rows, round_number=round_number, model=model)
        write_json(output / "failures.json", failures)
        if failure_output is not None:
            write_json(failure_output, failures)
    return summary

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)

def summarize(results):
    """Count matches, mistakes and errors, then calculate overall/category scores."""
    counts = Counter(r["status"] for r in results)
    categories = {}
    confusion = {d: {p: 0 for p in (*DECISIONS, "error")} for d in DECISIONS}
    for r in results:
        confusion[r["expected_decision"]][r["actual_decision"] or "error"] += 1
    for decision in DECISIONS:
        rows = [r for r in results if r["expected_decision"] == decision]
        matches = sum(r["status"] == "match" for r in rows)
        categories[decision] = {"assigned": len(rows), "matched": matches,
                                "accuracy": matches / len(rows) if rows else None}
    return {"assigned": len(results), "matched": counts["match"],
            "mismatched": counts["mismatch"], "errors": counts["error"],
            "accuracy": counts["match"] / len(results) if results else None,
            "by_expected_category": categories, "confusion_matrix": confusion,
            "scope": "Decision agreement only; citation and explanation correctness need separate review."}

def print_summary(summary):
    print(f"Decision agreement: {summary['matched']}/{summary['assigned']} ({summary['accuracy']:.1%})")
    print(f"Mismatches: {summary['mismatched']}; errors: {summary['errors']}")
    for category, item in summary["by_expected_category"].items():
        score = f"{item['accuracy']:.1%}" if item["accuracy"] is not None else "not represented"
        print(f"  {category}: {item['matched']}/{item['assigned']} ({score})")

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fake', action='store_true')
    parser.add_argument('--with-jev', action='store_true', help='Include Jev in the evaluated final decision')
    parser.add_argument('--split', choices=['all', 'learn', 'holdout'], default='all')
    parser.add_argument('--tests', type=Path, default=ROOT / 'data/tests.json')
    parser.add_argument('--round', type=int, default=0)
    parser.add_argument('--limit', type=int, help='Small smoke evaluation; select first N cases')
    parser.add_argument('--timeout', type=float, default=150)
    parser.add_argument('--strict', action='store_true')
    parser.add_argument('--retry-errors-from', type=Path, help='Retry only execution errors from a saved run; preserve its score and learning handoff')
    args = parser.parse_args(argv)
    if args.round < 0 or args.timeout <= 0 or (args.limit is not None and args.limit < 1):
        parser.error('Round must be nonnegative; timeout and limit must be positive.')
    path = args.tests
    if path == ROOT / 'data/tests.json' and not path.exists():
        path = ROOT / 'contracts/sample_tests.json'
    cases = [c for c in load_cases(path) if args.split == 'all' or c.split == args.split]
    if args.retry_errors_from:
        prior = args.retry_errors_from
        manifest = read_json(prior / 'manifest.json')
        if manifest['mode'] != ('fake' if args.fake else 'real') or manifest['with_jev'] != args.with_jev:
            parser.error('Retry mode must match the original --fake and --with-jev settings.')
        if manifest['model'] != ('fake' if args.fake else get_config().model_id):
            parser.error('Model changed; start a new benchmark rather than an error retry.')
        if manifest['input_sha256'] != input_hashes():
            parser.error('Benchmark, corpus or screening code changed; start a new benchmark.')
        rows = [json.loads(line) for line in (prior / 'results.jsonl').read_text().splitlines()]
        errors = {r['id'] for r in rows if r['status'] == 'error'}
        cases = [c for c in load_cases(prior / 'tests_snapshot.json') if c.id in errors]
        args.round = manifest['round']
        if not cases:
            print('No execution errors to retry.')
            return 0
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        parser.error('No cases selected.')
    output = ROOT / 'results' / ('tests_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    summary = run_evaluation(cases, output, fake=args.fake, with_jev=args.with_jev,
                            round_number=args.round, timeout=args.timeout,
                            failure_output=None if args.retry_errors_from else ROOT / 'data/failures.json')
    if args.retry_errors_from:
        summary['retry_of'] = str(args.retry_errors_from.resolve())
        write_json(output / 'summary.json', summary)
    else:
        write_json(ROOT / 'results/single_run_summary.json', summary)
    print_summary(summary)
    print('Draft answer key. Scores measure decision agreement, not scientific truth.')
    if args.fake:
        print('FAKE MODE: fixed team fixture; these scores do not measure AI performance.')
    print(f'Results: {output}')
    return int(bool(summary['errors'] or (args.strict and summary['mismatched'])))


if __name__ == '__main__':
    if sys.argv[1:] == ['--worker']:
        print(json.dumps(worker(json.loads(sys.stdin.read()))))
    else:
        raise SystemExit(main())
