# Hypothesis Generation and Screening Prototype

Generate possible extensions of reviewed international-relations papers, assess their research
viability, and evaluate screening decisions against a small draft benchmark. This prototype
does not establish whether a hypothesis is scientifically true.

## Start here

Use Python 3.11 or newer. From this repository's root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Run the following copy only if you do not already have a .env file:
cp .env.example .env
```

Edit `.env` locally. Use the **conflict team's** keys, not the finance team's:

| Variable | Value |
| --- | --- |
| `MODEL` | `foundry` |
| `FOUNDRY_API_KEY` | Key Vault secret `conflict-foundry-key` |
| `FOUNDRY_BASE_URL` | `https://uwcapstone-resource.services.ai.azure.com/openai/v1/` |
| `FOUNDRY_DEPLOYMENT` | `DeepSeek-V4-Flash-2` |
| `TYPESAFE_API_KEY` | Key Vault secret `conflict-jev-key` |
| `JEV_MODEL` | `jev-1.13.0` |

`config.py` and `jev.py` load `.env` explicitly. Variables already set in your shell
have priority. `.env` is Git-ignored. Keys are never intentionally included in prompts,
logs, reports or ledgers. Keep keys out of screenshots and chat messages.
The example template contains blank values; the endpoint, deployment and Jev model above
are the code defaults. A local `.env` stores secrets as plain text; shell environment
variables are also supported if you prefer not to save secrets on disk.

This repository already includes the paper summaries and dataset inventory. It does not
have the finance project's `prepare_data.py`; do not run the finance setup here.

## Run the prototype

```sh
# No keys or API requests: validate the connected components.
python -m unittest discover -s tests -v
python run_tests.py --fake
python run_rounds.py --fake
python generate.py --fake --count 1

# After setting your two keys: one tiny request to each service.
python smoke_test.py

# One real generated hypothesis, grounded in a reviewed paper, then checker + Jev.
python generate.py --count 1 --paper-id braithwaite_2011

# One real benchmark case first; then the full 20-case evaluation.
python run_tests.py --with-jev --limit 1
python run_tests.py --with-jev
```

`generate.py` uses Foundry to propose an extension with source references and a rationale.
Jia's checker supplies the structured evidence assessment. Jev independently chooses a
viability decision and a research-value category using typed questions. Agreement and the
shared schema gates are required for `proceed`; model disagreement or unclear research
value becomes `revise`. Both component decisions are preserved. Jev's categories do not
provide free-text explanations; the evidence explanations come from the checker.

Generation accepts 1–5 candidates per run and defaults to one. `--paper-id` can be repeated;
without it the first three corpus papers are used. `--topic` supplies an optional focus.
Paper IDs are validated against the selected corpus. Human review is still needed to
check whether the proposed extension faithfully represents the paper.

If generation succeeded but screening failed, retry the saved candidates without paying
for a new generation call:

```sh
python generate.py --screen-file results/generated_candidates.json
```

The original candidate IDs and generator model are preserved. Invalid generation responses
are saved in `results/generation_response.json`; checker schema failures are saved in
`results/checker_validation.json`. These contain research output, not API headers or keys.

## Where results go

| File | Meaning |
| --- | --- |
| `data/tests.json` | Your 20 draft benchmark hypotheses and expected decisions |
| `results/generated_candidates.json` | Latest generated hypotheses and screening results |
| `data/candidate_ledger.jsonl` | Append-only generation and screening events, linked by candidate ID |
| `data/ledger.jsonl` | Jia's original checker verdicts |
| `data/screening_ledger.jsonl` | Jev assessments, checker drafts and combined final verdicts |
| `results/single_run_summary.json` | Latest benchmark score, including errors |
| `results/accuracy_by_round.png` | Latest three-round chart |
| `results/round_summary.json` | Scores and review information by round |
| `results/connections.json` | Latest small connection-check status |
| `results/api_calls.jsonl` | Model, token counts, latency and safe error status; no keys or request bodies |
| `data/failures.json` | Learning-case wrong verdicts in Sylvia's exact format; never holdout failures |

Detailed runs are kept in timestamped directories under `results/`. Runtime outputs are
Git-ignored. Curated, clearly labeled example outputs are in `docs/examples/`.

The benchmark contains 7 `proceed`, 7 `revise`, and 6 `reject` cases, split 10/10 into
learning and holdout. Its labels remain **draft judgments**, not research ground truth.
Accuracy measures agreement on the final decision only. It does not establish the quality
of citations, the scientific truth of a hypothesis, or real-world predictive performance.

Fake mode calls the team's fixed `fake_check()` fixture. It answers `proceed` every time,
so the 20-case demo scores 35%; each round scores 40% on learning and 30% on holdout.
These are wiring checks, not measured model performance or improvement.

## Reviewed improvement rounds

```sh
python run_rounds.py --with-jev
```

For each of three rounds the runner evaluates learning cases, calls Sylvia's real
`improve.py` logic, pauses for human review, then evaluates holdout cases. Round 1 starts
with no lessons. The holdout phase uses approved lessons through the current round;
the next learning phase uses those same approved lessons. Generation itself is not
trained by this loop; lessons affect the screening checker.

When the runner pauses:

```sh
python improve.py list --pending
python improve.py approve LESSON_ID
# Or discard an unsuitable proposal:
python improve.py reject LESSON_ID
# Then use the exact --resume ... --review-complete command printed by run_rounds.py.
```

The runner verifies there are no pending proposals for that model and round. It never
automatically approves a lesson. Fake rounds use Sylvia's deterministic improvement code
and store unapproved fake lessons inside the run folder, separate from real lessons.
Repeated holdout measurements are prototype monitoring, not a fresh final test. Freeze
and review labels, corpus, rubric and lessons before comparing real runs. Existing approved
lessons for the same model may be reused; inspect them before restarting an experiment.
API errors count as evaluation errors and stop improvement rounds; they never become
research decisions or lessons. Requests have timeouts and no automatic transport retries;
the checker can make a bounded number of attempts to repair invalid JSON.

API implementation references: [Microsoft Foundry v1](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle),
[Jev typed questions and answers](https://docs.typesafe.ai/api), and
[Jev model versions](https://docs.typesafe.ai/models).

## Existing checker interface

```sh
# No API key needed; always returns the sample judgment and logs it as fake.
python checker.py "Democracies are peaceful." --fake

# Real calls after configuring the selected provider in .env.
python checker.py "Democracies are peaceful." --model foundry
python checker.py "Democracies are peaceful." --model qwen

# Offline integration tests, including simulated provider requests.
python -m unittest discover -s tests -v
```

Successful calls print a JSON verdict and append one `LedgerRecord` to
`data/ledger.jsonl`. `--ledger PATH` overrides the log location. The default
`--round 0` is a no-lesson baseline; use `--round 1` or higher to load the latest
approved lessons up to that round. An optional `--run-id` groups calls. For
benchmark calls, supply `--split learn|holdout` and `--test-id` together.

DeepSeek and Qwen both use the OpenAI-compatible chat interface and JSON-object
output. Set the exact model supported by your account. The Qwen base URL must
match your API key's region/workspace. Provider references:
[DeepSeek JSON output](https://api-docs.deepseek.com/guides/json_mode/) and
[Qwen OpenAI compatibility](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope).
Only select models that support JSON-object output; unsupported API parameters
cause a request error rather than a silently different request.

Example Python use for the runner:

```python
from checker import check, fake_check

verdict = fake_check("Democracies are peaceful.")
# Each call already logs once; the runner should not duplicate its ledger entry.
# verdict = check(case.hypothesis, round=1, split=case.split,
#                 test_id=case.id, run_id="deepseek-round-1")
```

Retries repair malformed JSON, schema inconsistencies, invented evidence IDs,
and insufficient declared year coverage. The error sent back to the model names what
is valid: the corpus paper IDs, the dataset IDs, the variables of the named dataset, and the years
that dataset actually covers, because a retry sees only that message. `MAX_JSON_RETRIES=2` allows up to three
model responses. Transport retries are handled separately by the SDK. Invalid
verdicts are not logged as successful outcomes. Factual support for a cited
paraphrase and appropriate measurement/join choices still need research review;
matching IDs alone does not verify those claims.

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
│   ├── sample_papers.json
│   ├── sample_cow_vars.json
│   ├── sample_tests.json
│   ├── sample_failures.json
│   └── sample_lessons.json
├── config.py                       A
├── checker.py                      A
├── ledger.py                       A
├── tests/test_checker.py           A; offline core integration checks
├── cow_data.py                     C / Sylvia; sample, check and full-download command
├── improve.py                      C / Sylvia; failures -> proposed lessons (docs/improve_design.md)
├── run_tests.py                    D / Amitej; benchmark evaluation
├── run_rounds.py                   D; reviewed improvement rounds
├── generate.py                     paper-grounded generation and candidate ledger
├── screening.py                    checker + Jev combined screening
├── jev.py                          typed Jev API client
├── smoke_test.py                   small Foundry and Jev connection checks
├── data/
|   ├──/papers_original             B: Original papers in .pdf format (10 papers, named lastname_year_short-title.pdf)
|   |   ├── braithwaite_2011_unpacking-escalation.pdf                    Braithwaite & Lemke 2011: statistical analysis
|   |   ├── carlson_1995_theory-escalation-international-conflict.pdf    Carlson 1995: game theory model + statistical test
|   |   ├── fearon_1994_domestic-political-audiences.pdf                 Fearon 1994: game theory model
|   |   ├── fearon_1995_rationalist-explanations-war.pdf                 Fearon 1995: theory paper
|   |   ├── gartzke_2007_capitalist-peace.pdf                            Gartzke 2007: statistical analysis
|   |   ├── kinsella_2002_conflict-emergence-escalation-dyads.pdf        Kinsella & Russett 2002: statistical analysis
|   |   ├── quek_2016_costly-signals-credible.pdf                        Quek 2016: lab experiments
|   |   ├── slantchev_2005_military-coercion-interstate-crises.pdf       Slantchev 2005: game theory model
|   |   ├── tang_2026_audience-costs-quasi-meta-analysis.pdf             Tang 2026: review of case studies
|   |   └── weeks_2008_autocratic-audience-costs.pdf                     Weeks 2008: theory + statistical analysis
│   ├── papers.json                 B / Jerry
|   ├── schema.md                   B Explains the schema and structure of the papers.json file
│   ├── cow_vars.json                C / Sylvia; 39 CoW file entries
│   ├── cow_files.json              C; download URL, zip member, delimiter per entry
│   ├── cow_samples/                C; 5-row sample of every entry (committed)
│   ├── cow_full/                   C; full downloads, ignored
│   ├── tests.json                  D; planned
│   ├── lessons.json                C; created by improve.py, approved by hand
│   ├── improve_log.jsonl           C; generated, ignored
│   ├── failures.json               D; generated, ignored
│   └── ledger.jsonl                A; generated, ignored
├── docs/
│   ├── improve_design.md           C; design of improve.py and the papers it draws on
│   ├── observations.md             C; findings from real runs that affect the build
│   ├── sources.md                  B
│   └── suggested_tests.md          B; optional
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
| `data/papers.json` | UTF-8 JSON array of paper objects (fields explained in `data/schema.md`) | `sample_papers.json` / `Paper` |
| `data/cow_vars.json` | UTF-8 JSON array of dataset objects | `sample_cow_vars.json` / `Dataset` |
| `data/tests.json` | JSON array of cases | `sample_tests.json` / `TestCase` |
| `data/failures.json` | JSON array of wrong verdicts from the learning split | `sample_failures.json` / `Failure` |
| `data/lessons.json` | JSON array of reviewed or pending lessons | `sample_lessons.json` / `Lesson` |
| `data/ledger.jsonl` | JSON Lines; one metadata envelope and verdict per call | `LedgerRecord`, containing `Verdict` |

Every input file is a JSON array (only `ledger.jsonl` is JSON Lines); the sample files are the
exact formatting templates. Use `is_sample: false` on real papers and datasets.
Include actual source links, peer-review status, codebook variable names,
units, years, and known limitations.

Readers use the matching sample only when the real file **does not exist**.
An existing empty array means zero records; malformed files must raise a clear
error rather than silently falling back. Resolve file paths relative to the
repository, not the shell's working directory. Do not label runs using any
sample corpus as real-data evaluations.

Python interfaces (optional keyword arguments carry evaluation metadata):

```python
check(hypothesis: str) -> Verdict
fake_check(hypothesis: str) -> Verdict
```

`fake_check` returns a validated copy of `sample_verdict.json` with the input
hypothesis substituted. It does not inspect expected labels and its judgments
are not meaningful. The runner supplies evaluation metadata; the checker calls
`ledger.py` to append `LedgerRecord` envelopes. The checker validates returned
paper IDs and dataset-variable references against its actual inputs before
accepting them. Both functions return a `Verdict` and automatically log once.

The checker uses at most ten approved lessons from its current model's lesson
history. Order selection deterministically and record applied lesson IDs.
Pending lessons (`approved: false`) never influence a verdict. No approved
lessons in a real file means no lessons; it must not load sample lessons.
Lessons match the exact configured model ID and cannot come from a later round.
Sample lessons are used only when both corpus files are sample fallbacks; no
fixture lessons are applied to a real corpus. `create_client()` and `get_config()`
in `config.py` are available for Sylvia's `improve.py` to reuse.

## CoW data inventory and on-demand download

`data/cow_vars.json` describes 39 Correlates of War files (latest version of each dataset that
suits conflict research, with each file format listed separately). Each entry was written from
the official codebook and checked against the real file header. Older versions (for example
MID 4.x, Trade 3.0, NMC 5.0, IGO 2.3) are superseded and left out. World Religion, Arms
Technology and the 1.3 GB dyadic IGO file are not included; add an entry plus a line in
`data/cow_files.json` if a hypothesis needs them.

```sh
python cow_data.py list                  # entries and whether each has a verified sample
python cow_data.py sample --all          # download and write 5-row samples to data/cow_samples/
python cow_data.py check                 # offline: samples agree with the declared variables
python cow_data.py full cow-mida-5.0     # full file into data/cow_full/ (ignored by git)
python cow_data.py full --all            # everything, roughly 0.3 GB
```

`full` refuses any entry whose sample is missing or does not match `cow_vars.json`, and removes
a download whose header differs from the sample. Full files are saved unchanged: several war
files use old Mac (CR) line endings or ISO-8859 text, and `igo_year` is tab-delimited
(`cow_files.json` records the delimiter and encoding). The samples are normalized to UTF-8.
Declared variables are sometimes a subset of a wide file; each entry's `limitations` says so.

## Lessons: propose, review, approve

`improve.py` turns learning-split failures into one-sentence lessons; the design and its sources
are in [docs/improve_design.md](docs/improve_design.md). Proposals are saved with `approved: false`
and the checker ignores them until you approve them.

```sh
python improve.py data/failures.json --round 1 --model deepseek   # propose (one model call)
python improve.py contracts/sample_failures.json --round 0 --fake # offline, no key (failures must be for model "fake")
python improve.py list --pending                                  # what awaits review
python improve.py approve deepseek-r1-01                          # also: unapprove, reject (deletes a pending proposal)
python improve.py status --round 1 --model deepseek               # exit code 3 while proposals are unreviewed
```

Only failures from the learning split, for the selected model and round, are accepted. If
`data/tests.json` exists, each failure must belong to a learning test. `--dry-run` prints without writing;
`--force` proposes again for failures already processed. `data/improve_log.jsonl` records each run.

## Evaluation and improvement protocol

Amitej’s `data/tests.json` supplies 20 draft cases: 7 proceed / 7 revise / 6 reject,
with ten learning and ten holdout cases and similar class coverage. The three sample tests illustrate formats only. They are not the
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
edits. The current assigned services are Foundry DeepSeek and Jev, used in different pipeline roles.
Legacy Qwen configuration remains supported but has not been verified with the current team accounts.
Compare configurations from separate no-lesson baselines and separate lesson histories. Log prompt/schema versions, model identifiers, corpus/test
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
