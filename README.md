# Hypothesis Validity Checker

Capstone prototype: evaluate an international-relations hypothesis against a
local paper corpus and dataset inventory, return a structured JSON verdict, and
record the result. Prototype due **Tuesday, October 13, 2026**; demo
**Wednesday, October 14, 2026**.

## Current milestone

Shared contracts and sample files are ready for team development. The checker,
model access, evaluation runner, and improvement loop are the next milestone;
they are not implemented in this starter commit.

The sample papers and dataset are **fictional format fixtures**. They are not
research evidence or actual CoW data. Fake-mode scores demonstrate plumbing,
not hypothesis-checking accuracy.

## Setup

Use Python 3.11 or newer, then run from the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m contracts.validate_samples
```

The validation command works without an API key. For later real-model runs,
copy `.env.example` to `.env` and enter your own credentials and provider model
identifiers. `config.py` will read these settings in the next milestone.
Never commit `.env` or keys.

## Decision rubric, version 1.0

The checker assesses research readiness. It does not establish that a
hypothesis is true or demonstrate a causal relationship.

| Decision | Rule |
| --- | --- |
| `proceed` | The claim is falsifiable and the available data covers the required concepts, unit, years, outcomes, and comparison observations. Explain whether this is replication or an extension when prior research is found. |
| `revise` | The core idea is repairable but needs definitions, scope, data, or clarification. Explain the missing requirements and suggest wording when appropriate. Unknown evidence normally calls for revision or clarification. |
| `reject` | The central premise cannot be empirically evaluated without replacing it, is incoherent, or falls outside the project's agreed research scope with no useful repair. State the specific reason. |

An implausible hypothesis is not automatically unfalsifiable. A vague but
repairable hypothesis normally receives `revise`. Prior study alone does not
justify `reject`; replication can proceed. Data unavailable in this prototype
normally warrants `revise`, with the missing requirements listed.

`already_tested.status` refers **only to the supplied corpus**:

- `found`: a directly relevant study was found; cite its corpus paper ID and
  explain how closely it matches the hypothesis.
- `not_found`: no relevant study was found in the supplied corpus; this does
  not mean the hypothesis has never been studied.
- `unknown`: the evidence is inadequate or the comparison is ambiguous.

Falsifiability allows `yes`, `no`, and `unknown`. Data coverage allows
`available`, `partial`, `unavailable`, and `unknown`. Pydantic validates the
shape and basic consistency of an answer; factual evidence still requires
verification against the corpus and codebooks.

CoW is a collection of datasets, not just war cases. Record each dataset's
coverage separately. Event-only war data needs a suitable observation universe
to analyze war versus no-war outcomes. See the
[official CoW dataset catalog](https://correlatesofwar.org/data-sets/).

## File structure and ownership

Files marked "planned" are intentionally absent so they cannot hide the sample
fallbacks or suggest that unfinished scripts work.

```text
.
├── README.md                       A / Jia
├── requirements.txt                A
├── .gitignore                      A
├── .env.example                    A
├── contracts/                      A; shared formats
│   ├── __init__.py
│   ├── schema.py
│   ├── validate_samples.py
│   ├── sample_verdict.json
│   ├── sample_papers.txt
│   ├── sample_cow_vars.txt
│   ├── sample_tests.json
│   ├── sample_failures.json
│   └── sample_lessons.json
├── config.py                       A; planned
├── checker.py                      A; planned
├── ledger.py                       A; planned
├── improve.py                      C / Sylvia; planned
├── run_tests.py                    D / Amitej; planned
├── run_rounds.py                   D; planned
├── data/
│   ├── papers.txt                  B / Jerry; planned
│   ├── cow_vars.txt                C; planned
│   ├── tests.json                  D; planned
│   ├── lessons.json                C; planned
│   ├── failures.json               D; generated, ignored
│   └── ledger.jsonl                A; generated, ignored
├── docs/
│   ├── sources.md                  B; planned
│   └── suggested_tests.md          B; optional, planned
└── results/                        D; generated results ignored
```

Only Jia edits `contracts/`; announce contract changes before teammates pull.
Everyone edits their assigned files, pulls before starting, and pushes at
least daily. Use GitHub issues to request changes to another person's files.
Commit selected final experiment results explicitly if they should be shared;
runtime output is ignored by default.

## Shared formats and handoffs

Import models from `contracts.schema`. It uses
[Pydantic v2 models](https://docs.pydantic.dev/latest/concepts/models/).
IDs must be unique within each file; citations and lessons refer to stable IDs.

| Real input/output | Format | Sample / model |
| --- | --- | --- |
| `data/papers.txt` | UTF-8 JSON Lines; one JSON object per nonblank line, no comments | `sample_papers.txt` / `Paper` |
| `data/cow_vars.txt` | UTF-8 JSON Lines; one dataset object per nonblank line, no comments | `sample_cow_vars.txt` / `Dataset` |
| `data/tests.json` | JSON array of cases | `sample_tests.json` / `TestCase` |
| `data/failures.json` | JSON array of wrong verdicts from the learning split | `sample_failures.json` / `Failure` |
| `data/lessons.json` | JSON array of reviewed or pending lessons | `sample_lessons.json` / `Lesson` |
| `data/ledger.jsonl` | JSON Lines; one metadata envelope and verdict per call | `LedgerRecord`, containing `Verdict` |

The `.txt` files use JSON Lines for reliable parsing; the sample files are the
exact formatting templates. Use `is_sample: false` on real papers and datasets.
Include actual source links, peer-review status, codebook variable names,
units, years, and known limitations.

Readers use the matching sample only when the real file **does not exist**.
An existing empty array means zero records; malformed files must raise a clear
error rather than silently falling back. Resolve file paths relative to the
repository, not the shell's working directory. Do not label runs using any
sample corpus as real-data evaluations.

Planned Python interfaces:

```python
check(hypothesis: str) -> Verdict
fake_check(hypothesis: str) -> Verdict
```

`fake_check` returns a validated copy of `sample_verdict.json` with the input
hypothesis substituted. It does not inspect expected labels and its judgments
are not meaningful. The runner owns evaluation metadata; `ledger.py` appends
`LedgerRecord` envelopes. The checker must validate returned paper IDs and
dataset-variable references against its actual inputs before accepting them.

The checker uses at most ten approved lessons from its current model's lesson
history. Order selection deterministically and record applied lesson IDs.
Pending lessons (`approved: false`) never influence a verdict. No approved
lessons in a real file means no lessons; it must not load sample lessons.

## Evaluation and improvement protocol

Amitej writes 20 reviewed cases, approximately 7 proceed / 7 revise / 6 reject,
and splits them into ten learning and ten holdout cases with similar class
coverage. The three sample tests illustrate formats only. They are not the
benchmark. Agree on gold labels and rationales against the final corpus and
data inventory before freezing the split. Do not pass expected labels or
rationales into the checker.

1. Freeze the corpus, dataset inventory, benchmark, and decision rubric.
2. Run round 0 with no lessons for each model and record the baseline.
3. For rounds 1–3, evaluate the learning split, write only its wrong verdicts to
   `data/failures.json`, and generate proposed lessons.
4. Sylvia manually reviews the proposed lessons. Pause the round until review
   is complete; the runner must not auto-approve lessons.
5. Evaluate the holdout with the approved lessons and save accuracy overall
   and per decision category, run metadata, and applied lesson IDs.

Holdout errors and rationales never enter `improve.py`, lesson review, or prompt
edits. Compare DeepSeek and Qwen from separate no-lesson baselines and separate
lesson histories. Log prompt/schema versions, model identifiers, corpus/test
file hashes, temperature, rounds, and lesson IDs with the run results. With ten
holdout cases, one answer changes accuracy by ten percentage points, so report
counts and treat this as a small prototype evaluation.

Response logging is an audit trail. The reviewed lesson loop is the improvement
mechanism; it changes instructions, not the model's weights.

## Team milestones and handoff

- **Sunday, October 11:** shared contracts committed and available to everyone.
- **Monday, October 12:** each person's component pushed and independently
  checked. Jia completes one real API call early.
- **Tuesday, October 13:** integrate, run both models from baseline through
  reviewed improvement rounds, and resolve demo issues.
- **Wednesday, October 14:** demonstrate verdicts, evidence, and evaluation.

After collaborator access is ready, Jia can send this message in the team chat:

> Contracts are in—pull the repo and run `python -m contracts.validate_samples`.
> Use `contracts/schema.py` and the sample files as your interfaces. Jerry owns
> papers and sources; Sylvia owns data coverage and lessons; Amitej owns tests
> and evaluation. Samples are fictional. Only Jia edits contracts; raise an
> issue for any format changes.

This handoff is prepared here; it has not been sent to anyone.
