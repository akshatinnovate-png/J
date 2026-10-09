"""Pydantic schemas. Extracted facts and generated interpretations are kept
in separate models so the UI can never present one as the other."""
from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class EvidenceStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partially_supported"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting_evidence"
    INSUFFICIENT = "insufficient_information"


class FlagKind(str, Enum):
    UNIT_MISMATCH = "unit_mismatch"
    VALUE_CONFLICT = "value_conflict"
    DATE_CONFLICT = "date_conflict"
    MISSING_RANGE = "missing_reference_range"
    MISSING_DATE = "missing_date"
    INCOMPARABLE_CONTEXT = "incomparable_context"
    STATEMENT_CONFLICT = "statement_conflict"


class FlagSeverity(str, Enum):
    FORMATTING = "confirmed_formatting_inconsistency"
    POSSIBLE = "possible_factual_contradiction"


class Provenance(BaseModel):
    """Where an extracted item physically came from. Never synthesised."""
    doc_id: str
    page: int | None = None
    line: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    raw_text: str = Field(description="Verbatim source span, unmodified.")


class Document(BaseModel):
    doc_id: str
    filename: str
    doc_type: str | None = None          # None when not explicitly stated
    doc_date: _dt.date | None = None     # None when not explicitly stated
    date_is_explicit: bool = False
    page_count: int = 1
    text: str = ""
    is_synthetic: bool = False
    extraction_error: str | None = None
    injection_findings: list[str] = Field(default_factory=list)


class Measurement(BaseModel):
    """A numeric observation literally present in a document."""
    fact_id: str
    analyte: str                 # normalised key, e.g. "hba1c"
    display_name: str            # as printed in the document
    value: float
    unit: str | None = None
    unit_canonical: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    ref_text: str | None = None
    observed_on: _dt.date | None = None
    context: str | None = None   # e.g. "fasting", "post-prandial"
    provenance: Provenance

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float) -> float:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("value must be finite")
        return v


class Statement(BaseModel):
    """A non-numeric recorded line: medication, instruction, observation."""
    fact_id: str
    category: Literal["medication", "instruction", "observation", "allergy", "other"]
    text: str
    subject: str | None = None   # normalised key for cross-doc comparison
    observed_on: _dt.date | None = None
    provenance: Provenance


class ImagingRecord(BaseModel):
    """An imaging study referenced in a document.

    CAREGRAPH does not receive real DICOM pixel data. When a document names a
    study, it renders a SIMULATED illustration of that modality so the record has
    something to show. The illustration is generated, never a real patient image,
    and is labelled as such everywhere it appears.
    """
    fact_id: str
    modality: str                 # key into imaging.MODALITIES
    printed_name: str             # exactly as written in the document
    body_part: str | None = None
    observed_on: _dt.date | None = None
    report_text: str | None = None
    provenance: Provenance
    is_illustration: bool = True


class Claim(BaseModel):
    """A generated explanation. Must point at real fact_ids or be unverified."""
    claim_id: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    rejected_evidence_ids: list[str] = Field(
        default_factory=list,
        description="Cited ids that matched no extracted fact. Retained for audit.")
    status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    caveat: str | None = None
    is_general_education: bool = False
    generator: str = "deterministic"

    @field_validator("text")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("claim text must not be empty")
        return v


class Flag(BaseModel):
    """A potential cross-document inconsistency. Never auto-resolved."""
    flag_id: str
    kind: FlagKind
    severity: FlagSeverity
    title: str
    reason: str
    needs_clarification: str
    evidence_ids: list[str] = Field(default_factory=list)


class Question(BaseModel):
    question_id: str
    text: str
    priority: int = 3            # 1 = highest
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class GapItem(BaseModel):
    """Something absent from the record. Describes absence; invents nothing."""
    gap_id: str
    label: str
    detail: str
    related_doc_ids: list[str] = Field(default_factory=list)


class Case(BaseModel):
    """The full analysed record set."""
    documents: list[Document] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    statements: list[Statement] = Field(default_factory=list)
    imaging: list[ImagingRecord] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    gaps: list[GapItem] = Field(default_factory=list)

    def fact_ids(self) -> set[str]:
        return ({m.fact_id for m in self.measurements}
                | {s.fact_id for s in self.statements}
                | {i.fact_id for i in self.imaging})

    def doc(self, doc_id: str) -> Document | None:
        return next((d for d in self.documents if d.doc_id == doc_id), None)

    def fact(self, fact_id: str) -> Measurement | Statement | None:
        for f in (*self.measurements, *self.statements, *self.imaging):
            if f.fact_id == fact_id:
                return f
        return None


class LLMExplanation(BaseModel):
    """Structured shape an LLM must return. Validated before use."""
    plain_language: str
    evidence_ids: list[str] = Field(default_factory=list)
    caveat: str | None = None
