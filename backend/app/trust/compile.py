"""From the record of a run to its trust manifest.

The inputs are plain values taken from the record (`SpanRecord`, `FindingRecord`), so this module reads no database
and can be tested on invented text. Whether a quote was found is the record's own answer: the verifier decided it
when the run was made, and a finished run does not change. How many places the quote stands in the whole document
is counted here, with the verifier's own `locate`, because the record counts within the cited section only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..verify.spans import locate
from .facts import facts_in
from .model import (
    CONTEXT_CHARS,
    Dependency,
    Evidence,
    FindingProof,
    Need,
    Obligation,
    Occurrences,
    On,
    SectionText,
    Standing,
    TrustManifest,
    derive,
    snapshot_hash,
)


@dataclass(frozen=True)
class SpanRecord:
    """One evidence span as the run recorded it. ``section`` indexes the document's sections; None when not located."""

    ordinal: int
    quote: str
    cited_label: str
    verified: bool
    method: str
    section: int | None
    start: int
    end: int


@dataclass(frozen=True)
class FindingRecord:
    finding_id: str
    ordinal: int
    topic: str
    status: str
    spans: tuple[SpanRecord, ...]


def count_places(quote: str, sections: Sequence[SectionText]) -> tuple[Occurrences, ...]:
    """Every section the quote stands in under the verifier's rules, with how many places in each."""
    found = []
    for section in sections:
        located = locate(quote, section.text, section.label)
        if located is not None:
            found.append(Occurrences(section.key, located.count))
    return tuple(found)


def unique_obligation(obligation_id: str, span: int, located: bool, places: int, sections_named: str = "") -> Obligation:
    """The one rule for uniqueness, used when a manifest is compiled and when it is taken to a revised document."""
    everything = (Dependency(On.DOCUMENT),)
    if not located:
        return Obligation(
            obligation_id, Need.QUOTE_UNIQUE, Standing.NOT_ESTABLISHED, "the quote was not located, so there is no place to count", everything, span
        )
    if places == 1:
        return Obligation(obligation_id, Need.QUOTE_UNIQUE, Standing.ESTABLISHED, "the quoted words stand in one place in the document", everything, span)
    where = f" ({sections_named})" if sections_named else ""
    return Obligation(
        obligation_id, Need.QUOTE_UNIQUE, Standing.NOT_ESTABLISHED,
        f"the quoted words stand in {places} places in the document{where}; which passage the finding rests on is not established", everything, span,
    )  # fmt: skip


def evidence_of(span: SpanRecord, sections: Sequence[SectionText]) -> Evidence:
    if not span.verified or span.section is None or span.start < 0:
        return Evidence(span.ordinal, span.quote, span.cited_label)
    section = sections[span.section]
    return Evidence(
        span=span.ordinal, quote=span.quote, cited_label=span.cited_label, section_key=section.key, section_number=section.number,
        section_heading=section.heading, section_name=section.name, start=span.start, end=span.end, method=span.method,
        before=section.text[max(0, span.start - CONTEXT_CHARS) : span.start], after=section.text[span.end : span.end + CONTEXT_CHARS],
        occurrences=count_places(span.quote, sections),
    )  # fmt: skip


def span_obligations(prefix: str, evidence: Evidence, names: Mapping[str, str]) -> list[Obligation]:
    """The obligations one quote carries: that it stands, that it stands once, and each typed value it states."""
    exists_id = f"{prefix}/{Need.QUOTE_EXISTS.value}"
    if not evidence.located:
        exists = Obligation(
            exists_id,
            Need.QUOTE_EXISTS,
            Standing.NOT_ESTABLISHED,
            "the quote was not found in the sections the model was given",
            (Dependency(On.DOCUMENT),),
            evidence.span,
        )
        return [exists, unique_obligation(f"{prefix}/{Need.QUOTE_UNIQUE.value}", evidence.span, False, 0)]
    out = [
        Obligation(
            exists_id, Need.QUOTE_EXISTS, Standing.ESTABLISHED, f"the quoted words stand in {evidence.section_name} ({evidence.method})",
            (Dependency(On.SECTION, evidence.section_key),), evidence.span,
        ),
        unique_obligation(
            f"{prefix}/{Need.QUOTE_UNIQUE.value}", evidence.span, True, evidence.places,
            ", ".join(names.get(o.section_key, "a section") for o in evidence.occurrences) if evidence.places > 1 else "",
        ),
    ]  # fmt: skip
    for index, fact in enumerate(facts_in(evidence.quote)):
        out.append(
            Obligation(
                f"{prefix}/{Need.FACT_MATCHES.value}#{index}", Need.FACT_MATCHES, Standing.ESTABLISHED,
                f"the quoted passage states {fact.value} ({fact.kind.value})", (Dependency(On.SPAN, exists_id),), evidence.span, fact,
            )
        )  # fmt: skip
    return out


def reader_obligation(
    prefix: str, reader_version: str, current_reader: str, evidence: Sequence[Evidence], current_reading: Sequence[SectionText] | None
) -> Obligation:
    """Whether the finding's evidence holds under today's reader.

    A reader's version changing is not, by itself, a reason to doubt a finding: a run keeps the reader that produced
    its sections, and most of what a new reader changes touches no quote. So the question asked is the one that
    matters. The same bytes, as today's reader reads them: does every quote the finding rests on still stand there?

        the run was read by today's reader                        established
        an earlier reader, and every quote stands in today's      established, and the earlier reader is named
          reading of the same bytes
        an earlier reader, and a quote does not stand there       not established: the two readers disagree about
                                                                  the text the finding rests on
        an earlier reader, and no reading by today's reader       not established: it cannot be compared
          can be made (the original bytes are gone or unread)
    """
    obligation_id = f"{prefix}/{Need.READER_COMPATIBLE.value}"
    code = (Dependency(On.CODE),)
    if reader_version == current_reader:
        return Obligation(obligation_id, Need.READER_COMPATIBLE, Standing.ESTABLISHED, f"read by reader {reader_version}, the current one", code)
    earlier = f"read by reader {reader_version or 'not recorded'}; the current reader is {current_reader}"
    located = [item for item in evidence if item.located]
    depends = (*code, *(Dependency(On.SPAN, f"{prefix}.{item.span}/{Need.QUOTE_EXISTS.value}") for item in located))
    if current_reading is None:
        return Obligation(
            obligation_id, Need.READER_COMPATIBLE, Standing.NOT_ESTABLISHED,
            f"{earlier}, and the document could not be read again to compare the two readings", depends,
        )  # fmt: skip
    lost = [item for item in located if not any(locate(item.quote, section.text, section.label) for section in current_reading)]
    if lost:
        return Obligation(
            obligation_id, Need.READER_COMPATIBLE, Standing.NOT_ESTABLISHED,
            f"{earlier}, and {len(lost)} of this finding's {len(located)} quote(s) do not stand in the document as the current reader reads it", depends,
        )  # fmt: skip
    return Obligation(
        obligation_id, Need.READER_COMPATIBLE, Standing.ESTABLISHED,
        f"{earlier}; every quote this finding rests on also stands in the document as the current reader reads it", depends,
    )  # fmt: skip


def rules_obligation(prefix: str, stale_rules: Sequence[str], evidence: Sequence[Evidence]) -> Obligation:
    """Whether the finding's evidence holds under today's rules.

    The same principle as for the reader. A run keeps the rule versions it was decided under, and a version that
    has moved on is not, alone, a reason to doubt its evidence: most of the record was made before versions were
    recorded at all. The one rule that decides evidence is the verifier, and it can be asked again. So it is: for
    every quote the record located, does today's verifier find it in the section the record located it in?

        decided under today's rules                               established
        earlier rules, and today's verifier finds every quote     established, and what differs is named
        earlier rules, and today's verifier does not find one     not established

    What this does not cover, and says so: the recorded *status* (pass, needs review) is the one the policy of the
    time decided, and the sections handed to the model are the ones the retrieval of the time chose. This layer
    accounts for evidence. It does not decide a status again.
    """
    obligation_id = f"{prefix}/{Need.RULES_COMPATIBLE.value}"
    code = (Dependency(On.CODE),)
    if not stale_rules:
        return Obligation(obligation_id, Need.RULES_COMPATIBLE, Standing.ESTABLISHED, "decided under the current rules", code)
    earlier = f"recorded under earlier rules ({'; '.join(stale_rules)})"
    located = [item for item in evidence if item.located]
    depends = (*code, *(Dependency(On.SPAN, f"{prefix}.{item.span}/{Need.QUOTE_EXISTS.value}") for item in located))
    lost = [item for item in located if not any(o.section_key == item.section_key for o in item.occurrences)]
    if lost:
        return Obligation(
            obligation_id, Need.RULES_COMPATIBLE, Standing.NOT_ESTABLISHED,
            f"{earlier}, and today's verifier does not find {len(lost)} of this finding's {len(located)} quote(s) where the record located them", depends,
        )  # fmt: skip
    return Obligation(
        obligation_id, Need.RULES_COMPATIBLE, Standing.ESTABLISHED,
        f"{earlier}; today's verifier finds every quote where the record located it. The recorded status is the one decided then", depends,
    )  # fmt: skip


def compile_manifest(
    *,
    run_id: str,
    document_id: str,
    document_sha256: str,
    reader_version: str,
    current_reader: str,
    rule_versions: Mapping[str, str],
    stale_rules: Sequence[str],
    sections: Sequence[SectionText],
    findings: Sequence[FindingRecord],
    current_reading: Sequence[SectionText] | None = None,
) -> TrustManifest:
    """``current_reading`` is the same document as today's reader reads it; it is consulted only when the run was read
    by an earlier reader, and None means no such reading could be made."""
    names = {section.key: section.name for section in sections}
    proofs = []
    for finding in findings:
        prefix = str(finding.ordinal)
        evidence = tuple(evidence_of(span, sections) for span in finding.spans)
        obligations: list[Obligation] = []
        for item in evidence:
            obligations += span_obligations(f"{prefix}.{item.span}", item, names)
        obligations.append(reader_obligation(prefix, reader_version, current_reader, evidence, current_reading))
        obligations.append(rules_obligation(prefix, stale_rules, evidence))
        proofs.append(
            FindingProof(finding.finding_id, finding.ordinal, finding.topic, finding.status, derive(tuple(obligations)), evidence, tuple(obligations))
        )
    return TrustManifest(
        run_id=run_id, document_id=document_id, document_sha256=document_sha256, snapshot_hash=snapshot_hash(reader_version, tuple(sections)),
        reader_version=reader_version, rule_versions=tuple(sorted(rule_versions.items())), findings=tuple(proofs),
    )  # fmt: skip
