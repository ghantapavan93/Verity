"""The shape the model must return. Kept as plain JSON Schema so Ollama can constrain decoding
and pydantic can validate the result independently."""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, Field

# What the model may propose for a finding's status. Code decides the status (runs.status).
StatusHint = Literal["pass", "needs_review", "missing"]
STATUS_HINTS: tuple[StatusHint, ...] = get_args(StatusHint)


class EvidenceOut(BaseModel):
    section_id: str = Field(description="the [sec_N] id of the section the quote comes from")
    quote: str = Field(description="verbatim passage copied from that section")


class FindingOut(BaseModel):
    topic: str
    conclusion: str
    status_hint: StatusHint
    # A finding without a quoted passage is not a finding; constrained decoding enforces this too.
    evidence: list[EvidenceOut] = Field(min_length=1, max_length=3)
    guidance_reference: str | None = None
    observed: str | None = None
    required: str | None = None
    suggested_position: str | None = None


class AnalysisOut(BaseModel):
    findings: list[FindingOut] = Field(max_length=5)
    insufficient_evidence: bool = False
    note: str | None = None


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "conclusion": {"type": "string"},
                    "status_hint": {"type": "string", "enum": list(STATUS_HINTS)},
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "properties": {"section_id": {"type": "string"}, "quote": {"type": "string"}},
                            "required": ["section_id", "quote"],
                        },
                    },
                    "guidance_reference": {"type": ["string", "null"]},
                    "observed": {"type": ["string", "null"]},
                    "required": {"type": ["string", "null"]},
                    "suggested_position": {"type": ["string", "null"]},
                },
                "required": ["topic", "conclusion", "status_hint", "evidence", "guidance_reference", "observed", "required", "suggested_position"],
            },
        },
        "insufficient_evidence": {"type": "boolean"},
        "note": {"type": ["string", "null"]},
    },
    "required": ["findings", "insufficient_evidence", "note"],
}
