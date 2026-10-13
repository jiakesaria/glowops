"""Version 1 shared formats. See README.md for the decision rubric and handoffs."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1)]
Decision = Literal["proceed", "revise", "reject"]
Split = Literal["learn", "holdout"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class YearRange(Contract):
    start: int
    end: int

    @model_validator(mode="after")
    def chronological(self):
        if self.end < self.start:
            raise ValueError("end year must be >= start year")
        return self


class PaperVariables(Contract):
    outcome: list[Text]
    explanatory: list[Text]
    controls: list[Text]


class PaperData(Contract):
    sources: list[Text]
    years: Text | None  # Free text because papers report ranges and caveats.
    unit: Text
    sample_size: Text | None
    notes: str


class RelatedPaper(Contract):
    id: Text
    relation: Text


class Paper(Contract):
    """One entry of data/papers.json; see data/schema.md for field meanings."""

    id: Text
    title: Text
    authors: list[Text] = Field(min_length=1)
    year: int
    journal: Text | None
    volume: int | None
    issue: int | None
    pages: Text | None
    doi: Text | None
    url: Text | None
    peer_reviewed: bool | None
    study_type: Text
    uses_real_world_data: bool
    method_summary: Text
    tags: list[Text]
    research_question: Text
    main_finding: Text
    key_findings: list[Text]
    claims_tested_with_data: list[Text]
    predictions_not_tested_in_this_paper: list[Text]
    variables: PaperVariables
    data: PaperData
    limitations: list[Text]
    open_questions: list[Text]
    related: list[RelatedPaper]
    is_sample: bool = False  # Only the fictional fixtures set this to true.


class Variable(Contract):
    name: Text
    description: Text


class Dataset(Contract):
    id: Text
    name: Text
    version: Text
    source_url: Text | None
    unit_of_analysis: Text
    years: YearRange
    variables: list[Variable] = Field(min_length=1)
    limitations: list[Text] = Field(min_length=1)
    is_sample: bool


class Falsifiability(Contract):
    status: Literal["yes", "no", "unknown"]
    explanation: Text


class Citation(Contract):
    paper_id: Text
    evidence: Text  # A supported paraphrase; exact quotations are optional.


class PriorResearch(Contract):
    status: Literal["found", "not_found", "unknown"]
    explanation: Text
    citations: list[Citation]

    @model_validator(mode="after")
    def require_evidence(self):
        if self.status == "found" and not self.citations:
            raise ValueError("found requires at least one corpus citation")
        if self.status != "found" and self.citations:
            raise ValueError("citations require status found")
        return self


class VariableMatch(Contract):
    concept: Text
    dataset_id: Text
    variable_names: list[Text] = Field(min_length=1)
    explanation: Text


class DataCoverage(Contract):
    status: Literal["available", "partial", "unavailable", "unknown"]
    explanation: Text
    required_unit_of_analysis: Text | None
    required_years: YearRange | None
    matches: list[VariableMatch]
    missing_requirements: list[Text]

    @model_validator(mode="after")
    def require_coverage(self):
        if self.status == "available":
            if not self.matches or self.missing_requirements:
                raise ValueError("available requires matches and no missing requirements")
            if self.required_unit_of_analysis is None or self.required_years is None:
                raise ValueError("available requires a defined unit and time range")
        elif not self.missing_requirements:
            raise ValueError("incomplete coverage requires missing requirements")
        return self


class Verdict(Contract):
    schema_version: Literal["1.0"] = "1.0"
    hypothesis: Text
    falsifiable: Falsifiability
    already_tested: PriorResearch
    testable_with_available_data: DataCoverage
    suggested_rewording: Text | None
    decision: Decision
    decision_reason: Text

    @model_validator(mode="after")
    def safe_to_proceed(self):
        if self.decision == "proceed":
            if self.falsifiable.status != "yes":
                raise ValueError("proceed requires falsifiable=yes")
            if self.testable_with_available_data.status != "available":
                raise ValueError("proceed requires data coverage=available")
        return self


class TestCase(Contract):
    id: Text
    hypothesis: Text
    split: Split
    expected_decision: Decision
    rationale: Text
    expected_falsifiable: Literal["yes", "no", "unknown"] | None = None
    expected_already_tested: Literal["found", "not_found", "unknown"] | None = None
    expected_data_coverage: Literal["available", "partial", "unavailable", "unknown"] | None = None


class Failure(Contract):
    test_id: Text
    split: Split
    round: int = Field(ge=0)
    model: Text
    hypothesis: Text
    expected_decision: Decision
    rationale: Text
    actual_verdict: Verdict

    @model_validator(mode="after")
    def actual_failure(self):
        if self.actual_verdict.hypothesis != self.hypothesis:
            raise ValueError("failure and verdict hypotheses must match")
        if self.actual_verdict.decision == self.expected_decision:
            raise ValueError("failure requires a wrong decision")
        return self


class Lesson(Contract):
    id: Text
    tag: Literal["falsifiability", "prior_research", "data_coverage", "decision"]
    text: Text
    source_test_ids: list[Text] = Field(min_length=1)
    source_split: Literal["learn"]  # Holdout errors must never generate lessons.
    round: int = Field(ge=0)
    model: Text
    approved: bool = False


class LedgerRecord(Contract):
    schema_version: Literal["1.0"] = "1.0"
    timestamp_utc: Text  # ISO 8601 UTC, for example 2026-10-10T18:00:00Z.
    run_id: Text
    model: Text
    mode: Literal["fake", "real"]
    round: int = Field(ge=0)
    split: Split | None  # null for a hypothesis outside the benchmark.
    test_id: Text | None
    corpus_is_sample: bool
    applied_lesson_ids: list[Text]
    verdict: Verdict
