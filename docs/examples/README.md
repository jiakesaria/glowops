# Offline examples

These examples were produced by the integrated code in fake mode. They are not live
Foundry/Jev results and do not demonstrate model accuracy or scientific findings.

- `fake_candidate.json`: one deterministic candidate, source reference, and fixed checker verdict.
- `fake_evaluation.json`: evaluation of 20 draft cases against the team’s always-proceed fixture.

To reproduce from the repository root:

```sh
python generate.py --fake --count 1
python run_tests.py --fake
python run_rounds.py --fake
```

The three-round chart appears at `results/accuracy_by_round.png`. Real outputs remain
local under `results/` and `data/*ledger.jsonl`; review them before sharing.
