# papers.txt Schema

`papers.json` is a JSON list. Each JSON entry represents one papers. There are currently 10 papers in the corpus. This is meant to serve as the corpus for the recursive-training loop. If a value is unknown we default to `null` (`[]` for lists). No field is left out so we will not have missing fields.

## Schema Template

```json
{
  "id": "lastname_year",
  "title": "",
  "authors": [""],
  "year": 0,
  "journal": "",
  "volume": null,
  "issue": null,
  "pages": "",
  "doi": null,
  "url": null,
  "peer_reviewed": true,
  "study_type": "",
  "uses_real_world_data": true,
  "method_summary": "",
  "tags": [""],
  "research_question": "",
  "main_finding": "",
  "key_findings": [""],
  "claims_tested_with_data": [""],
  "predictions_not_tested_in_this_paper": [""],
  "variables": {
    "outcome": [""],
    "explanatory": [""],
    "controls": [""]
  },
  "data": {
    "sources": [""],
    "years": null,
    "unit": "",
    "sample_size": null,
    "notes": ""
  },
  "limitations": [""],
  "open_questions": [""],
  "related": [{"id": "", "relation": ""}]
}
```

## Fields

**Identity**

| Field | What it is |
|---|---|
| `id` | Structured and UNIQUE descriptor of a paper, `lastname_year`. Verdicts and lessons use it to cite the paper. |
| `title`, `authors`, `year` | Basic information of the paper. |
| `journal`, `volume`, `issue`, `pages` | Where it was published. |
| `doi`, `url` | Link to the paper if checked, else `null`. |

**What kind of study**

| Field | What it is |
|---|---|
| `peer_reviewed` | `true` if experts checked it before publication. |
| `study_type` | One of: `statistical_analysis`, `game_theory_model`, `theory_paper`, `lab_experiments`, `case_study_review`, `game_theory_model_plus_statistical_test`, `theory_plus_statistical_analysis`. |
| `uses_real_world_data` | `false` if the paper is pure math or argument with no data. |
| `method_summary` | 2–4 plain sentences on what the authors actually did. |
| `tags` | Topic labels (e.g. `audience_costs`, `territory`). The checker uses them to pick relevant papers. Reuse existing tags before making new ones. |

**What it found**

| Field | What it is |
|---|---|
| `research_question` | The question the paper asks, in one sentence. |
| `main_finding` | The answer, in 1–3 sentences. |
| `key_findings` | Specific results, with numbers where possible. |
| `claims_tested_with_data` | Claims the paper checked against data. End each with (supported), (not supported), or (mixed). |
| `predictions_not_tested_in_this_paper` | Claims the paper argues for but never checks. Keeps the checker from calling these "already tested." |

**What the papers measured**

| Field | What it is |
|---|---|
| `variables.outcome` | What the paper is trying to explain (eg whether war happens). |
| `variables.explanatory` | What it thinks causes the outcome. |
| `variables.controls` | Other factors it holds constant so they don't skew the results. |
| `data.sources` | Datasets used (e.g. MID, CoW, Polity IV). Empty for theory papers. |
| `data.years` | Years covered. Lets the checker spot extensions to new time periods. |
| `data.unit` | What one row of data is (e.g. a country pair in one year). |
| `data.sample_size` | How many cases. |
| `data.notes` | Anything excluded or unusual about the data. |

**What's is still unclear**

| Field | What it is |
|---|---|
| `limitations` | Weak points and concessions the authors admit, or that are clear from the paper. |
| `open_questions` | What the paper leaves unanswered. This is where extension hypotheses come from. |
| `related` | Links to other papers in the file, each with a short reason. Helps the checker find a theory's tests in other papers. |

## Rules

- Write in plain language. A non-expert should understand every line.
- Only state what the paper says. No guesses.
- Run `python -m json.tool data/papers.txt` before pushing. One missing comma breaks the whole file.