"""What a finding's trust stands on, written down.

A finished run records that a quote was found. This module records what that finding needs in order to be relied
on, one obligation at a time, and what each obligation depends on:

    QUOTE_EXISTS    the quoted words stand in a section        depends on that one section
    QUOTE_UNIQUE    and stand in one place in the document     depends on every section
    FACT_MATCHES    a period, amount, percentage or date the   depends on the quoted span
                    quote states, as code parsed it
    READER_COMPATIBLE  the quotes stand in the document as    depends on the code and the quoted span
                    today's reader reads it
    RULES_COMPATIBLE   today's verifier finds each quote      depends on the code and the quoted span
                    where the record located it

The split by dependency is the point. That words stand in a document needs one witness and depends only on the
section the witness is in. That they stand once is a statement about every section. So when a revised document
arrives, a change in one clause reaches the findings that cite it, and the uniqueness of every quote, and nothing
else (`trust.diff`).

Nothing here judges whether a finding is right. A fact that matches is a number code read in a quote; that the number
is about the point the finding makes is the model's reading, as everywhere else in this application.

Everything is a frozen value. A manifest is derived from the immutable record of a run and can be derived again; it
is never stored and never edited.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum

from ..hashing import fingerprint, sha256_text

TRUST_VERSION = "trust-v1"
CONTEXT_CHARS = 40  # of section text kept on each side of a quote, to find the place again when the words change


class Need(StrEnum):
    QUOTE_EXISTS = "quote_exists"
    QUOTE_UNIQUE = "quote_unique"
    FACT_MATCHES = "fact_matches"
    READER_COMPATIBLE = "reader_compatible"
    RULES_COMPATIBLE = "rules_compatible"


class Standing(StrEnum):
    ESTABLISHED = "established"
    NOT_ESTABLISHED = "not_established"  # code cannot say it holds, and says why
    CONTRADICTED = "contradicted"  # the place the evidence stood now states something else


class TrustState(StrEnum):
    SUPPORTED = "supported"  # every quote stands, once, read and decided under today's code
    NEEDS_REVIEW = "needs_review"  # the quotes stand, and something a person should look at does not hold
    UNSUPPORTED = "unsupported"  # a quote does not stand, or what stood there has changed


class On(StrEnum):
    SECTION = "section"  # the content of one section
    DOCUMENT = "document"  # the content of every section
    SPAN = "span"  # the quoted characters themselves
    CODE = "code"  # a version of this application's reader or rules


class FactKind(StrEnum):
    DURATION = "duration"
    MONEY = "money"
    PERCENT = "percent"
    DATE = "date"


@dataclass(frozen=True)
class Dependency:
    on: On
    ref: str = ""


@dataclass(frozen=True)
class Fact:
    """One typed value as the text states it. ``value`` is the normal form two writings of the same value share."""

    kind: FactKind
    value: str
    surface: str


@dataclass(frozen=True)
class SectionText:
    """A section as the reader stored it: what a quote is located in."""

    ordinal: int
    number: str
    heading: str
    text: str

    @property
    def label(self) -> str:
        return f"{self.number} {self.heading}".strip()

    @property
    def content_hash(self) -> str:
        return sha256_text(self.text)

    @property
    def key(self) -> str:
        """What a located quote depends on in this section: its text, and the label a quote may carry in front."""
        return fingerprint("section/v1", self.label, self.content_hash)

    @property
    def name(self) -> str:
        """How the section is named to a reader."""
        return f"§{self.number} {self.heading}".strip() if self.number else (self.heading or f"section {self.ordinal + 1}")


@dataclass(frozen=True)
class Occurrences:
    """How many places a quote stands in one section. Kept per section so that a later count scans only what is new."""

    section_key: str
    count: int


@dataclass(frozen=True)
class Evidence:
    """One quote of one finding, and where it stands."""

    span: int
    quote: str
    cited_label: str
    section_key: str = ""  # empty when the quote was not located
    section_number: str = ""
    section_heading: str = ""
    section_name: str = ""
    start: int = -1
    end: int = -1
    method: str = "none"
    before: str = ""
    after: str = ""
    occurrences: tuple[Occurrences, ...] = ()  # every section the quote stands in, with how often

    @property
    def located(self) -> bool:
        return bool(self.section_key)

    @property
    def places(self) -> int:
        return sum(o.count for o in self.occurrences)


@dataclass(frozen=True)
class Obligation:
    obligation_id: str  # "<finding ordinal>.<span ordinal>/<need>[#n]", stable for a run
    need: Need
    standing: Standing
    reason: str
    depends_on: tuple[Dependency, ...] = ()
    span: int | None = None
    fact: Fact | None = None


@dataclass(frozen=True)
class FindingProof:
    finding_id: str
    ordinal: int
    topic: str
    recorded_status: str  # the status on the run record; this layer never changes it
    state: TrustState
    evidence: tuple[Evidence, ...]
    obligations: tuple[Obligation, ...]


def derive(obligations: tuple[Obligation, ...]) -> TrustState:
    """A finding's trust state, from its obligations and from nothing else.

    No quote obligation at all: nothing stands behind the finding, so it is unsupported. A quote that does not
    stand, or anything contradicted: unsupported. Otherwise needs review when any obligation is not established, and
    supported only when all are.
    """
    quotes = [o for o in obligations if o.need is Need.QUOTE_EXISTS]
    if not quotes or any(o.standing is not Standing.ESTABLISHED for o in quotes):
        return TrustState.UNSUPPORTED
    if any(o.standing is Standing.CONTRADICTED for o in obligations):
        return TrustState.UNSUPPORTED
    if any(o.standing is not Standing.ESTABLISHED for o in obligations):
        return TrustState.NEEDS_REVIEW
    return TrustState.SUPPORTED


@dataclass(frozen=True)
class TrustManifest:
    """Why a run's findings are trusted, as of the document the run read. Bound to that document's snapshot."""

    run_id: str
    document_id: str
    document_sha256: str
    snapshot_hash: str
    reader_version: str
    rule_versions: tuple[tuple[str, str], ...]
    findings: tuple[FindingProof, ...]
    trust_version: str = TRUST_VERSION

    @property
    def manifest_id(self) -> str:
        """The same run, document and code give the same id; anything that changes an answer changes it."""
        return fingerprint("trust-manifest/v1", json.dumps(asdict(self), sort_keys=True, ensure_ascii=False, default=str))[:16]

    def counts(self) -> dict[str, int]:
        return {state.value: sum(1 for f in self.findings if f.state is state) for state in TrustState}


def snapshot_hash(reader_version: str, sections: tuple[SectionText, ...]) -> str:
    """The identity of one reading of one document: the reader, and every section's number, heading and text, in
    order. Two uploads with different bytes and the same text under the same reader share it; a filename is no part
    of it."""
    parts: list[str] = [reader_version]
    for section in sections:
        parts += [section.number, section.heading, section.content_hash]
    return fingerprint("snapshot/v1", *parts)
