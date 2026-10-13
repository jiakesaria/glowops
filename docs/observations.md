# Observations log

Findings from running the system that affect how we build or read the results. Newest first.
Each entry says what was run, what happened, how sure we are, and what it suggests. These are
observations from a handful of calls, not measurements.

---

## 2026-10-13: the same hypothesis gets different decisions, and CoW's missing regime variable is not caught

**Run:** `checker.py` against a real model (`DeepSeek-V4-Flash` on Azure AI Foundry, temperature 0,
round 0, so no lessons), with the real corpus (10 papers in `data/papers.json`, 39 CoW file entries
in `data/cow_vars.json`) at commit ef9dc40. One hypothesis, called five times:

> Democratic dyads are less likely to fight wars than non-democratic dyads.

**What happened**

| Call | Outcome |
|---|---|
| 1 | No valid verdict. After three attempts the evidence check still failed on a year mismatch (before the validator's messages named the valid year range). |
| 2 | `proceed`, data coverage `available`. |
| 3 | `revise`, data coverage `partial`. |
| 4 | `revise`, data coverage `partial`. |
| 5 | `proceed`, data coverage `available` (after one retry that the new year-range message fixed). |

So four valid verdicts split two `proceed` and two `revise`, even at temperature 0.

**What the `proceed` verdicts relied on.** In calls 2 and 5 the matched datasets were the CoW
state-system dyad-year frame, inter-state war, directed dyadic war, national capabilities, direct
contiguity and alliances. None of the 39 entries in `data/cow_vars.json` measures regime type
(democracy), so the hypothesis's main explanatory concept had no match. I did not print the matches
for calls 3 and 4.

**What we think the right answer is, and how sure we are.** We believe `revise` is correct: the idea
is well formed and has been studied, but a regime-type measure from outside CoW (for example Polity or
V-Dem) is needed. This is our reading of the inventory, not a labelled test: `data/tests.json` does
not exist yet, so there is no gold label to check against. One hypothesis and five calls is far too
little to say how often the model gets it wrong.

**Why it happens (our reading)**

1. `validate_evidence` in `checker.py` checks that cited IDs, variable names and years exist. It does
   not check that every concept in the hypothesis has a matching variable, so a verdict can claim
   `available` while leaving a key concept unmatched.
2. The inventory says what CoW contains but never says what it lacks, so nothing tells the model that
   regime type is absent.
3. The deployment is not deterministic at temperature 0, so the same input can take either path.

**What it means for the project**

- Accuracy on the benchmark will be noisy for a reason unrelated to the lessons. A single run per
  test can flip a result. Consider running each test more than once, or at least treat one-case
  differences as noise (the README already warns that one case moves holdout accuracy by ten points).
- This failure is a natural target for a `data_coverage` lesson: a concept with no matching variable
  means `revise`, not `proceed`. It is also a fair check that lessons help, as long as the lesson does
  not name the example.
- The cheaper first fix may be in the data inventory rather than in lessons.

**Options, not yet decided**

| Option | Owner | Note |
|---|---|---|
| Add a list of what CoW does not cover (regime type, GDP, religion, and similar) to `data/cow_vars.json` or its limitations | Sylvia | Changes what the model sees; test with the same five calls. |
| Make the evidence check require a variable match for each concept the verdict names | Jia (`checker.py`) | Stronger, but needs a way to know which concepts the hypothesis requires. |
| Run each benchmark test several times and report the spread | Amitej (`run_tests.py`) | Costs about 30 seconds per call at present. |

**Related fix made on the same day:** evidence-check errors now name the valid paper IDs, dataset IDs,
variables and the dataset's real year range (commit ef9dc40). That addressed the call 1 failure; it
does not address the decision variation.
