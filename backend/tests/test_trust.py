"""Version-aware trust: what a finding stands on, and what a revised document does to it.

The invariants, in the order the tests take them:

    a finding is supported only when every quote stands, stands once, and was read and decided under today's code;
    a revision makes a finding stale exactly when something it stands on no longer holds;
    a revision that does not reach a finding's evidence never makes it stale;
    counting a quote again by searching only the new sections gives what searching every section gives;
    nothing here changes a run, and one workspace's versions are not another's.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

import pytest
from fastapi.testclient import TestClient

import app.application.ingest_document as ingest_module
from app.application.trust_run import manifest_of
from app.db import SessionLocal
from app.errors import Conflict
from app.ingest import PARSER_VERSION
from app.models import Document, Run
from app.trust.compile import FindingRecord, SpanRecord, compile_manifest
from app.trust.diff import Verdict, align, full_recount, trust_diff
from app.trust.facts import facts_in
from app.trust.model import FactKind, Need, Obligation, SectionText, Standing, TrustManifest, TrustState, derive, snapshot_hash
from app.verify.spans import locate
from tests.support import CONTRACT, upload_and_ask
from tests.test_workspaces import Reviewer, two  # noqa: F401  (the fixture)

E, N, C = Standing.ESTABLISHED, Standing.NOT_ESTABLISHED, Standing.CONTRADICTED

TERMINATION = "Customer may terminate this Agreement for convenience upon fifteen (15) days' written notice to Provider."
BASE: list[tuple[str, str]] = [
    ("Term", "This Agreement commences on January 31, 2027 and continues for twelve (12) months."),
    ("Termination for Convenience", f"{TERMINATION} On termination, Customer pays all Fees accrued."),
    ("Fees", "Customer shall pay Provider USD 250,000 per year. Late amounts bear interest at 1.5% per month."),
    ("Governing Law", "This Agreement is governed by the laws of the State of Delaware."),
    ("Notices", "Notices are given in writing to the address on the cover page."),
]
QUOTES = {
    "termination": (1, TERMINATION),
    "law": (3, "governed by the laws of the State of Delaware"),
    "fee": (2, "Customer shall pay Provider USD 250,000 per year."),
    "start": (0, "This Agreement commences on January 31, 2027"),
    "interest": (2, "Late amounts bear interest at 1.5% per month."),
}


def sections(parts: list[tuple[str, str]]) -> list[SectionText]:
    return [SectionText(index, str(index + 1), heading, text) for index, (heading, text) in enumerate(parts)]


def edited(index: int, old: str, new: str, parts: list[tuple[str, str]] = BASE) -> list[tuple[str, str]]:
    heading, text = parts[index]
    assert text.count(old) == 1, old
    return [*parts[:index], (heading, text.replace(old, new)), *parts[index + 1 :]]


def manifest(
    parts: list[tuple[str, str]] = BASE,
    quotes: dict[str, tuple[int, str]] = QUOTES,
    reader: str = "v6",
    stale_rules: tuple[str, ...] = (),
    current_reading: list[SectionText] | None = None,
) -> TrustManifest:
    """A run that cited each quote in the section it stands in, verified the way the verifier would."""
    document = sections(parts)
    findings = []
    for ordinal, (topic, (index, quote)) in enumerate(quotes.items()):
        located = locate(quote, document[index].text, document[index].label)
        span = SpanRecord(
            0,
            quote,
            f"sec_{index}",
            located is not None,
            located.method if located else "none",
            index if located else None,
            located.start if located else -1,
            located.end if located else -1,
        )
        findings.append(FindingRecord(f"f-{topic}", ordinal, topic, "pass", (span,)))
    return compile_manifest(
        run_id="run", document_id="doc", document_sha256="0" * 64, reader_version=reader, current_reader="v6",
        rule_versions={"policy_version": "policy-v3"}, stale_rules=stale_rules, sections=document, findings=findings, current_reading=current_reading,
    )  # fmt: skip


def standing(m: TrustManifest, topic: str) -> dict[str, Standing]:
    proof = next(f for f in m.findings if f.topic == topic)
    return {o.obligation_id.split("/")[1]: o.standing for o in proof.obligations}


# ---------------------------------------------------------------- typed facts


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("upon fifteen (15) days' written notice", [(FactKind.DURATION, "15 calendar days")]),
        ("within 20 Working Days of receipt", [(FactKind.DURATION, "20 business days")]),
        ("a fee of $250,000 and interest at 1.5%", [(FactKind.MONEY, "$250000"), (FactKind.PERCENT, "1.5%")]),
        ("USD 250,000.00 payable", [(FactKind.MONEY, "USD250000.00")]),
        ("expires on January 31, 2027", [(FactKind.DATE, "2027-01-31")]),
        ("the 31st day of January, 2027 and 2027-02-01", [(FactKind.DATE, "2027-01-31"), (FactKind.DATE, "2027-02-01")]),
        ("on February 30, 2027", []),
        ("twenty-one (30) days", []),
        ("promptly and in good faith", []),
    ],
    ids=["duration", "business days", "money and percent", "currency code", "date", "two dates", "not a date", "ambiguous period", "no fact"],
)
def test_a_passage_states_the_typed_values_code_can_read_and_no_others(text: str, expected: list[tuple[FactKind, str]]) -> None:
    assert [(fact.kind, fact.value) for fact in facts_in(text)] == expected


# ---------------------------------------------------------------- what a finding stands on


def test_a_quote_that_stands_once_under_todays_code_is_supported_and_its_values_are_recorded() -> None:
    m = manifest()
    assert m.counts() == {"supported": 5, "needs_review": 0, "unsupported": 0}
    proof = next(f for f in m.findings if f.topic == "termination")
    assert [(o.need, o.standing) for o in proof.obligations] == [
        (Need.QUOTE_EXISTS, E),
        (Need.QUOTE_UNIQUE, E),
        (Need.FACT_MATCHES, E),
        (Need.READER_COMPATIBLE, E),
        (Need.RULES_COMPATIBLE, E),
    ]
    assert proof.obligations[2].fact is not None and proof.obligations[2].fact.value == "15 calendar days"
    assert [o.fact.value for f in m.findings for o in f.obligations if o.fact] == ["15 calendar days", "USD250000", "2027-01-31", "1.5%"]
    assert proof.recorded_status == "pass", "the status on the record is carried, never changed"


def test_existence_depends_on_one_section_and_uniqueness_on_every_section() -> None:
    proof = manifest().findings[0]
    depends = {o.need: {(d.on.value, d.ref) for d in o.depends_on} for o in proof.obligations}
    assert depends[Need.QUOTE_EXISTS] == {("section", proof.evidence[0].section_key)}
    assert depends[Need.QUOTE_UNIQUE] == {("document", "")}
    assert depends[Need.FACT_MATCHES] == {("span", "0.0/quote_exists")}
    assert depends[Need.READER_COMPATIBLE] == depends[Need.RULES_COMPATIBLE] == {("code", "")}


def test_a_quote_that_stands_twice_in_the_document_is_not_a_clean_proof() -> None:
    """The verifier found the quote in the cited section and counted that section only. The same sentence in a
    schedule makes the finding's provenance ambiguous, and the manifest says which two sections hold it."""
    doubled = [*BASE, ("Schedule 1", f"For reference: {TERMINATION}")]
    proof = next(f for f in manifest(doubled).findings if f.topic == "termination")
    unique = next(o for o in proof.obligations if o.need is Need.QUOTE_UNIQUE)
    assert proof.state is TrustState.NEEDS_REVIEW and unique.standing is N
    assert "2 places" in unique.reason and "§2 Termination for Convenience" in unique.reason and "§6 Schedule 1" in unique.reason
    assert proof.evidence[0].places == 2


def test_a_quote_that_was_not_found_and_a_finding_with_no_quote_are_unsupported() -> None:
    absent = manifest(quotes={"invented": (1, "Customer may terminate at will without any notice whatsoever.")})
    assert absent.findings[0].state is TrustState.UNSUPPORTED and standing(absent, "invented") == {
        "quote_exists": N,
        "quote_unique": N,
        "reader_compatible": E,
        "rules_compatible": E,
    }
    bare = compile_manifest(
        run_id="r", document_id="d", document_sha256="0" * 64, reader_version="v6", current_reader="v6", rule_versions={}, stale_rules=(),
        sections=sections(BASE), findings=[FindingRecord("f", 0, "nothing cited", "missing", ())],
    )  # fmt: skip
    assert bare.findings[0].state is TrustState.UNSUPPORTED, "no quote obligation is not the same as every obligation met"


def test_an_earlier_reader_alone_is_not_a_reason_to_doubt_a_finding() -> None:
    """Every release of the reader would otherwise put the whole record under review. What is asked is whether the
    quotes stand in the same document as today's reader reads it."""
    same_text = manifest(reader="v5", current_reading=sections(BASE))
    assert {f.state for f in same_text.findings} == {TrustState.SUPPORTED}
    reason = next(o.reason for o in same_text.findings[0].obligations if o.need is Need.READER_COMPATIBLE)
    assert reason.startswith("read by reader v5; the current reader is v6; every quote this finding rests on also stands")
    # Today's reader splits the document differently and numbers it differently. The words are the same words.
    resplit = [("Preamble", BASE[0][1]), ("Part A", f"{BASE[1][1]} {BASE[2][1]}"), ("Part B", f"{BASE[3][1]} {BASE[4][1]}")]
    assert {f.state for f in manifest(reader="v5", current_reading=sections(resplit)).findings} == {TrustState.SUPPORTED}


def test_an_earlier_reader_that_read_the_quoted_text_differently_needs_review() -> None:
    """The two readers disagree about the words one finding rests on. That finding needs a person; the others do not."""
    reads_differently = sections(edited(1, "fifteen (15) days'", "fifteen (15) business days'"))
    m = manifest(reader="v5", current_reading=reads_differently)
    states = {f.topic: f.state for f in m.findings}
    assert states["termination"] is TrustState.NEEDS_REVIEW and {state for topic, state in states.items() if topic != "termination"} == {TrustState.SUPPORTED}
    termination = next(f for f in m.findings if f.topic == "termination")
    reader = next(o for o in termination.obligations if o.need is Need.READER_COMPATIBLE)
    assert reader.standing is N and "1 of this finding's 1 quote(s) do not stand in the document as the current reader reads it" in reader.reason
    assert ("span", "0.0/quote_exists") in {(d.on.value, d.ref) for d in reader.depends_on}


def test_an_earlier_reader_whose_document_cannot_be_read_again_needs_review() -> None:
    cannot_compare = manifest(reader="v5", current_reading=None)
    assert {f.state for f in cannot_compare.findings} == {TrustState.NEEDS_REVIEW}
    assert "could not be read again to compare" in next(o.reason for o in cannot_compare.findings[0].obligations if o.need is Need.READER_COMPATIBLE)


STALE_RULES = ("policy version policy-v2 then, policy-v3 now", "verifier version v5 then, v6 now")


def test_earlier_rules_alone_are_not_a_reason_to_doubt_a_findings_evidence() -> None:
    """Most of the record was made before rule versions were recorded. The verifier can be asked again, and is."""
    old_rules = manifest(stale_rules=STALE_RULES)
    assert {f.state for f in old_rules.findings} == {TrustState.SUPPORTED}
    rules = next(o for o in old_rules.findings[0].obligations if o.need is Need.RULES_COMPATIBLE)
    assert rules.standing is E and "policy version policy-v2 then, policy-v3 now" in rules.reason
    assert "today's verifier finds every quote where the record located it. The recorded status is the one decided then" in rules.reason
    assert ("span", "0.0/quote_exists") in {(d.on.value, d.ref) for d in rules.depends_on}


def a_quote_only_an_earlier_verifier_accepted(stale_rules: tuple[str, ...]) -> TrustManifest:
    """The record says a quote was found at offsets in a section. Today's verifier does not find those words there:
    what a laxer verifier accepted before v6, when a space moved inside the letters was forgiven."""
    document = sections([("Care", "Each patient is seen by a therapist within ten (10) days of referral.")])
    record = FindingRecord("f", 0, "care", "pass", (SpanRecord(0, "seen by the rapist within ten (10) days", "sec_0", True, "typed", 0, 16, 54),))
    assert locate(record.spans[0].quote, document[0].text, document[0].label) is None
    return compile_manifest(
        run_id="r", document_id="d", document_sha256="0" * 64, reader_version="v6", current_reader="v6", rule_versions={}, stale_rules=stale_rules,
        sections=document, findings=[record],
    )  # fmt: skip


def test_earlier_rules_under_which_todays_verifier_would_not_find_the_quote_need_review() -> None:
    proof = a_quote_only_an_earlier_verifier_accepted(STALE_RULES).findings[0]
    rules = next(o for o in proof.obligations if o.need is Need.RULES_COMPATIBLE)
    assert proof.state is TrustState.NEEDS_REVIEW and rules.standing is N
    assert "today's verifier does not find 1 of this finding's 1 quote(s) where the record located them" in rules.reason


@pytest.mark.parametrize(
    ("standings", "expected"),
    [
        ((E, E, E), TrustState.SUPPORTED),
        ((E, N, E), TrustState.NEEDS_REVIEW),
        ((E, E, N), TrustState.NEEDS_REVIEW),
        ((N, N, E), TrustState.UNSUPPORTED),
        ((C, N, E), TrustState.UNSUPPORTED),
        ((E, E, C), TrustState.UNSUPPORTED),
    ],
)
def test_the_state_is_derived_from_the_obligations(standings: tuple[Standing, Standing, Standing], expected: TrustState) -> None:
    needs = (Need.QUOTE_EXISTS, Need.QUOTE_UNIQUE, Need.FACT_MATCHES)
    assert derive(tuple(Obligation(f"0.0/{need.value}", need, s, "") for need, s in zip(needs, standings, strict=True))) is expected
    assert derive(()) is TrustState.UNSUPPORTED


def test_the_manifest_id_is_the_same_for_the_same_record_and_different_for_any_other() -> None:
    assert manifest().manifest_id == manifest().manifest_id
    assert manifest().manifest_id != manifest(edited(4, "in writing", "by email")).manifest_id
    assert manifest().manifest_id != manifest(reader="v5").manifest_id


def test_a_snapshot_is_the_reader_and_the_text_and_nothing_else() -> None:
    assert snapshot_hash("v6", tuple(sections(BASE))) == snapshot_hash("v6", tuple(sections(list(BASE))))
    assert snapshot_hash("v6", tuple(sections(BASE))) != snapshot_hash("v5", tuple(sections(BASE)))
    assert snapshot_hash("v6", tuple(sections(BASE))) != snapshot_hash("v6", tuple(sections(edited(4, "cover page", "cover sheet"))))


# ---------------------------------------------------------------- a revised document: the matrix

INSERTED = [BASE[0], ("Definitions", "Capitalised terms have the meanings given in Schedule A."), *BASE[1:]]


@dataclass(frozen=True)
class Revision:
    """One row of the matrix: the revised sections, and exactly what the diff must say about them."""

    to: list[tuple[str, str]]
    stale: set[str]
    revalidated: set[str]
    why: list[str]  # a fragment of the reason each stale finding must give
    changed: dict[str, Standing]  # every obligation whose standing changes, and what it becomes


MATRIX: dict[str, Revision] = {
    "the supporting number changes": Revision(
        to=edited(1, "fifteen (15)", "thirty (30)"),
        stale={"termination"},
        revalidated=set(),
        why=["15 calendar days → 30 calendar days"],
        changed={"0.0/quote_exists": C, "0.0/quote_unique": N, "0.0/fact_matches#0": C},
    ),
    "an amount changes": Revision(
        to=edited(2, "USD 250,000", "USD 300,000"),
        stale={"fee"},
        revalidated={"interest"},
        why=["USD250000 → USD300000"],
        changed={"2.0/quote_exists": C, "2.0/quote_unique": N, "2.0/fact_matches#0": C},
    ),
    "a date changes": Revision(
        to=edited(0, "January 31, 2027", "March 1, 2027"),
        stale={"start"},
        revalidated=set(),
        why=["2027-01-31 → 2027-03-01"],
        changed={"3.0/quote_exists": C, "3.0/quote_unique": N, "3.0/fact_matches#0": C},
    ),
    "one word of the quoted clause changes": Revision(
        to=edited(3, "governed by the laws", "governed by the courts"),
        stale={"law"},
        revalidated=set(),
        why=["now reads"],
        changed={"1.0/quote_exists": C, "1.0/quote_unique": N},
    ),
    "the clause is copied into a new section": Revision(
        to=[*BASE, ("Schedule 1", f"Restated: {TERMINATION}")],
        stale={"termination"},
        revalidated=set(),
        why=["stand in 2 places"],
        changed={"0.0/quote_unique": N},
    ),
    "the whole section is duplicated": Revision(
        to=[*BASE, BASE[1]],
        stale={"termination"},
        revalidated=set(),
        why=["stand in 2 places"],
        changed={"0.0/quote_unique": N},
    ),
    "an unrelated paragraph changes": Revision(to=edited(4, "in writing", "by email"), stale=set(), revalidated=set(), why=[], changed={}),
    "the cited section is revised around the quote": Revision(
        to=edited(1, "Customer pays all Fees accrued", "Customer pays all Fees accrued and due"),
        stale=set(),
        revalidated={"termination"},
        why=[],
        changed={},
    ),
    "a clause is inserted and every later section is renumbered": Revision(
        to=INSERTED,
        stale=set(),
        revalidated={"termination", "fee", "interest", "law"},
        why=[],
        changed={},
    ),
    "the quoted sentence moves to another section": Revision(
        to=[
            BASE[0],
            ("Termination for Convenience", "On termination, Customer pays all Fees accrued."),
            BASE[2],
            BASE[3],
            ("Notices", f"{BASE[4][1]} {TERMINATION}"),
        ],
        stale=set(),
        revalidated={"termination"},
        why=[],
        changed={},
    ),
    "the cited section is removed": Revision(
        to=[BASE[0], BASE[1], BASE[2], BASE[4]],
        stale={"law"},
        revalidated=set(),
        why=["is not in the revision"],
        changed={"1.0/quote_exists": N, "1.0/quote_unique": N},
    ),
    "the number is reworded to the same value": Revision(
        to=edited(1, "fifteen (15) days'", "15 days'"),
        stale={"termination"},
        revalidated=set(),
        why=["now reads"],
        changed={"0.0/quote_exists": C, "0.0/quote_unique": N},
    ),
}


@pytest.mark.parametrize("name", MATRIX)
def test_revision_matrix(name: str) -> None:
    """For each revision: exactly these findings go stale, for these reasons; exactly these are established again;
    every other finding is unchanged; and the manifest the diff was taken from is what it was."""
    row = MATRIX[name]
    old = manifest()
    before = old.manifest_id
    diff = trust_diff(old, sections(BASE), sections(row.to), "v6")
    by_verdict = {v: {f.topic for f in diff.findings if f.verdict is v} for v in (Verdict.STALE, Verdict.REVALIDATED, Verdict.UNCHANGED)}
    assert by_verdict[Verdict.STALE] == row.stale, "stale"
    assert by_verdict[Verdict.REVALIDATED] == row.revalidated, "revalidated"
    assert by_verdict[Verdict.UNCHANGED] == set(QUOTES) - row.stale - row.revalidated, "unchanged"
    changed = {o.obligation_id: o.after for f in diff.findings for o in f.obligations if o.verdict is Verdict.CHANGED}
    assert changed == row.changed, "obligations whose standing changed"
    why = " | ".join(sentence for f in diff.findings for sentence in f.why)
    assert all(fragment in why for fragment in row.why), why
    assert all(f.after is f.before for f in diff.findings if f.verdict is not Verdict.STALE)
    assert old.manifest_id == before == diff.manifest_id and diff.to_snapshot != diff.from_snapshot


def test_the_same_document_leaves_every_finding_unchanged_and_searches_nothing() -> None:
    diff = trust_diff(manifest(), sections(BASE), sections(list(BASE)), "v6")
    assert diff.counts() == {"unchanged": 5, "revalidated": 0, "stale": 0} and diff.sections_searched == 0 and not diff.sections.any
    assert all(o.verdict is Verdict.UNTOUCHED for f in diff.findings for o in f.obligations)


def test_a_reworded_number_keeps_its_fact_and_loses_its_quote() -> None:
    """The words changed and the value did not. The fact still stands; the quotation is no longer the document's."""
    diff = trust_diff(manifest(), sections(BASE), sections(edited(1, "fifteen (15) days'", "15 days'")), "v6")
    termination = next(f for f in diff.findings if f.topic == "termination")
    after = {o.obligation_id.split("/")[1]: (o.after, o.reason) for o in termination.obligations}
    assert after["fact_matches#0"] == (E, "the passage was reworded and still states 15 calendar days")
    assert after["quote_exists"][0] is C and termination.after is TrustState.UNSUPPORTED


def test_a_place_is_read_only_when_its_surroundings_mark_one_place() -> None:
    """The number changed and the sentence before the quote now stands twice: there is no one place to read, so
    nothing is read from the first of them. Not established, never contradicted."""
    quote = "Provider may suspend the Services on ten (10) days' notice."
    lead = "Invoices are payable in full within the period stated here. "
    parts = [("Suspension", f"{lead}{quote} Suspension ends on payment.")]
    old = manifest(parts, {"suspend": (0, quote)})
    revised = [("Suspension", f"{lead}Provider may suspend the Services on five (5) days' notice. Suspension ends on payment. {lead}Nothing else applies.")]
    suspend = trust_diff(old, sections(parts), sections(revised), "v6").findings[0]
    assert {o.obligation_id.split("/")[1]: o.after for o in suspend.obligations}["quote_exists"] is N
    assert {o.obligation_id.split("/")[1]: o.after for o in suspend.obligations}["fact_matches#0"] is N and suspend.verdict is Verdict.STALE


def test_a_number_alone_never_aligns_two_sections() -> None:
    """Inserting a clause moves every number after it. §3 before and §3 after are different clauses."""
    old = sections([("Term", "Twelve months."), ("Fees", "USD 10 per seat."), ("Law", "Delaware law governs.")])
    new = sections(
        [("Term", "Twelve months."), ("Audit", "Provider may audit once a year."), ("Charges", "USD 12 per seat."), ("Law", "Delaware law governs.")]
    )
    alignment = align(old, new)
    assert old[1].key not in alignment.counterpart, "§2 Fees is not §2 Audit"
    assert (
        alignment.counterpart[old[2].key].heading == "Law"
        and alignment.changes.removed == ("§2 Fees",)
        and alignment.changes.added == ("§2 Audit", "§3 Charges")
    )


def test_a_section_retitled_and_revised_at_once_is_still_found_by_what_it_says() -> None:
    """Heading and text both changed: no label and no hash connects the two versions. Most of the wording does."""
    clause = "Provider may suspend the Services on ten (10) days' notice if any undisputed invoice remains unpaid after its due date."
    old = sections([("Term", "Twelve months from the Effective Date."), ("Suspension", clause), ("Law", "Delaware law governs.")])
    new = sections(
        [
            ("Term", "Twelve months from the Effective Date."),
            ("Suspension of Services", clause.replace("ten (10)", "five (5)")),
            ("Law", "Delaware law governs."),
        ]
    )
    alignment = align(old, new)
    assert alignment.counterpart[old[1].key].heading == "Suspension of Services" and alignment.changes.changed == ("§2 Suspension",)
    quote = "Provider may suspend the Services on ten (10) days' notice"
    located = locate(quote, old[1].text, old[1].label)
    assert located is not None
    record = FindingRecord("f", 0, "suspension", "pass", (SpanRecord(0, quote, "sec_1", True, located.method, 1, located.start, located.end),))
    before = compile_manifest(
        run_id="r",
        document_id="d",
        document_sha256="0" * 64,
        reader_version="v6",
        current_reader="v6",
        rule_versions={},
        stale_rules=(),
        sections=old,
        findings=[record],
    )
    change = trust_diff(before, old, new, "v6").findings[0]
    assert change.verdict is Verdict.STALE and any("10 calendar days → 5 calendar days" in sentence for sentence in change.why)


def test_two_sections_that_share_little_wording_are_never_called_one_section() -> None:
    old = sections([("Fees", "Customer shall pay Provider USD 250,000 per year in quarterly instalments.")])
    new = sections([("Audit", "Provider may audit Customer's records once in any period of twelve months.")])
    alignment = align(old, new)
    assert not alignment.counterpart and alignment.changes.removed == ("§1 Fees",) and alignment.changes.added == ("§1 Audit",)


def test_only_the_sections_whose_content_is_new_are_searched() -> None:
    row = MATRIX["the supporting number changes"]
    diff = trust_diff(manifest(), sections(BASE), sections(row.to), "v6")
    assert (diff.sections_searched, diff.sections_total, diff.sections.identical) == (1, 5, 4)


# ---------------------------------------------------------------- uniqueness is a count over the whole revision
#
# The invariant. A finding may keep or regain uniqueness only when every section of the revised document is accounted
# for: carried over unchanged, contributing the count it had, or searched. Searching three sections of 123 is sound
# only because the other 120 are byte-for-byte sections the run already counted. Each row below fixes, for the
# termination quote, the count before, how many sections are searched and how many reused, the count after, and the
# trust state; and in every row the count after must equal a search of every section.


def fixed(*parts: tuple[str, str, str]) -> list[SectionText]:
    """Sections with their numbers given, so that a section can move, or stay, without being renumbered."""
    return [SectionText(index, number, heading, text) for index, (number, heading, text) in enumerate(parts)]


V1 = fixed(*[(str(index + 1), heading, text) for index, (heading, text) in enumerate(BASE)])
TERM, CONV, FEES, LAW, NOTICES = [(s.number, s.heading, s.text) for s in V1]
PAYS = "On termination, Customer pays all Fees accrued."


@dataclass(frozen=True)
class Count:
    """One adversarial revision and the whole account of the termination quote under it."""

    to: list[SectionText]
    before: int  # places in the old document
    searched: int
    reused: int
    after: int  # places in the revision
    state: TrustState
    old: list[SectionText] | None = None  # when the case needs another starting document


DOUBLED_V1 = fixed(TERM, CONV, FEES, LAW, NOTICES, ("6", "Schedule 1", f"Restated: {TERMINATION}"))
ADVERSARIAL: dict[str, Count] = {
    "01 a duplicate is added to a distant section that changed": Count(
        to=fixed(TERM, CONV, FEES, LAW, ("5", "Notices", f"{NOTICES[2]} {TERMINATION}")), before=1, searched=1, reused=4, after=2, state=TrustState.NEEDS_REVIEW
    ),
    "02 a duplicate existed and one copy is deleted": Count(
        old=DOUBLED_V1, to=fixed(TERM, CONV, FEES, LAW, NOTICES), before=2, searched=0, reused=5, after=1, state=TrustState.SUPPORTED
    ),
    "02b a duplicate existed and the cited copy is the one deleted": Count(
        old=DOUBLED_V1,
        to=fixed(TERM, FEES, LAW, NOTICES, ("6", "Schedule 1", f"Restated: {TERMINATION}")),
        before=2,
        searched=0,
        reused=5,
        after=1,
        state=TrustState.SUPPORTED,
    ),
    "03 an unrelated section becomes an exact duplicate of the cited one": Count(
        to=fixed(TERM, CONV, FEES, LAW, ("2", "Termination for Convenience", CONV[2])), before=1, searched=0, reused=5, after=2, state=TrustState.NEEDS_REVIEW
    ),
    "04 the cited section moves, byte for byte the same": Count(
        to=fixed(TERM, FEES, LAW, NOTICES, CONV), before=1, searched=0, reused=5, after=1, state=TrustState.SUPPORTED
    ),
    "05 only the heading of the cited section changes": Count(
        to=fixed(TERM, ("2", "Termination Without Cause", CONV[2]), FEES, LAW, NOTICES), before=1, searched=1, reused=4, after=1, state=TrustState.SUPPORTED
    ),
    "06 only the body of the cited section changes, around the quote": Count(
        to=fixed(TERM, ("2", CONV[1], f"{TERMINATION} {PAYS} No refund is due."), FEES, LAW, NOTICES),
        before=1,
        searched=1,
        reused=4,
        after=1,
        state=TrustState.SUPPORTED,
    ),
    "06b only the body of the cited section changes, and the quote with it": Count(
        to=fixed(TERM, ("2", CONV[1], CONV[2].replace("fifteen (15)", "thirty (30)")), FEES, LAW, NOTICES),
        before=1,
        searched=1,
        reused=4,
        after=0,
        state=TrustState.UNSUPPORTED,
    ),
    "07 the cited section is deleted": Count(to=fixed(TERM, FEES, LAW, NOTICES), before=1, searched=0, reused=4, after=0, state=TrustState.UNSUPPORTED),
    "07b another section is deleted": Count(to=fixed(TERM, CONV, FEES, NOTICES), before=1, searched=0, reused=4, after=1, state=TrustState.SUPPORTED),
    "08 an entirely new section is added, repeating nothing": Count(
        to=fixed(TERM, CONV, FEES, LAW, NOTICES, ("6", "Audit", "Provider may audit once a year.")),
        before=1,
        searched=1,
        reused=5,
        after=1,
        state=TrustState.SUPPORTED,
    ),
    "08b an entirely new section is added, repeating the quote": Count(
        to=fixed(TERM, CONV, FEES, LAW, NOTICES, ("6", "Schedule 1", f"Restated: {TERMINATION}")),
        before=1,
        searched=1,
        reused=5,
        after=2,
        state=TrustState.NEEDS_REVIEW,
    ),
    "09 two old sections merge into one": Count(
        to=fixed(TERM, ("2", "Termination and Fees", f"{CONV[2]} {FEES[2]}"), LAW, NOTICES), before=1, searched=1, reused=3, after=1, state=TrustState.SUPPORTED
    ),
    "10 the cited section splits in two, the quote whole in one half": Count(
        to=fixed(TERM, ("2", "Termination for Convenience", TERMINATION), ("3", "Effect of Termination", PAYS), FEES, LAW, NOTICES),
        before=1,
        searched=2,
        reused=4,
        after=1,
        state=TrustState.SUPPORTED,
    ),
    "10b the cited section splits in two, through the middle of the quote": Count(
        to=fixed(TERM, ("2", "Termination for Convenience", TERMINATION[:60]), ("3", "Notice", f"{TERMINATION[60:]} {PAYS}"), FEES, LAW, NOTICES),
        before=1,
        searched=2,
        reused=4,
        after=0,
        state=TrustState.UNSUPPORTED,
    ),
    "11 the same quote in every section but one, and that one is the only section searched": Count(
        old=fixed(*[(str(n), f"Part {n}", f"Clause {n}. {TERMINATION}") for n in range(1, 7)]),
        to=fixed(*[(str(n), f"Part {n}", f"Clause {n}. {TERMINATION}") for n in range(1, 6)], ("6", "Part 6", "Clause 6. Reserved.")),
        before=6,
        searched=1,
        reused=5,
        after=5,
        state=TrustState.NEEDS_REVIEW,
    ),
}


def termination_manifest(old: list[SectionText]) -> TrustManifest:
    """A run whose one finding quotes the termination sentence from the first section that holds it."""
    index = next(i for i, section in enumerate(old) if locate(TERMINATION, section.text, section.label))
    located = locate(TERMINATION, old[index].text, old[index].label)
    assert located is not None
    record = FindingRecord(
        "f-termination", 0, "termination", "pass", (SpanRecord(0, TERMINATION, f"sec_{index}", True, located.method, index, located.start, located.end),)
    )
    return compile_manifest(
        run_id="run",
        document_id="doc",
        document_sha256="0" * 64,
        reader_version="v6",
        current_reader="v6",
        rule_versions={},
        stale_rules=(),
        sections=old,
        findings=[record],
    )


@pytest.mark.parametrize("name", ADVERSARIAL)
def test_uniqueness_accounts_for_every_section_of_the_revision(name: str) -> None:
    case = ADVERSARIAL[name]
    old = case.old or V1
    before = termination_manifest(old)
    diff = trust_diff(before, old, case.to, "v6")
    unique = next(o for o in diff.findings[0].obligations if o.need is Need.QUOTE_UNIQUE)
    everywhere = sum(located.count for section in case.to if (located := locate(TERMINATION, section.text, section.label)) is not None)

    assert before.findings[0].evidence[0].places == unique.places_before == case.before, "old global occurrence count"
    assert diff.sections_searched == case.searched, "changed sections searched"
    assert diff.sections_reused == case.reused, "reused sections"
    assert diff.sections_searched + diff.sections_reused == diff.sections_total == len(case.to), "every section is accounted for"
    assert unique.places_after == case.after == everywhere, "new global occurrence count, equal to a search of every section"
    assert diff.findings[0].after is case.state, "trust state"
    assert (unique.after is E) == (case.after == 1), "unique exactly when the quote stands once in the whole revision"


def test_a_diff_that_leaves_a_section_unaccounted_for_cannot_be_built() -> None:
    """The account is checked where it is made: searched and reused must add up to the revision."""
    diff = trust_diff(termination_manifest(V1), V1, V1, "v6")
    with pytest.raises(ValueError, match="neither searched nor carried over"):
        replace(diff, sections_reused=diff.sections_reused - 1)


# ---------------------------------------------------------------- the same rules over generated revisions

FILLER = ["Recital", "Schedule", "Annex", "Exhibit", "Protocol", "Addendum"]
PLANTS = [TERMINATION, QUOTES["law"][1], "USD 250,000", "fifteen (15) days", BASE[2][1]]


def revise(parts: list[tuple[str, str]], rng: random.Random) -> list[tuple[str, str]]:
    parts = list(parts)
    kind = rng.choice(["add", "remove", "edit", "copy", "swap", "plant", "retitle", "figure"])
    at = rng.randrange(len(parts)) if parts else 0
    if kind == "add" or not parts:
        parts.insert(
            rng.randrange(len(parts) + 1), (f"{rng.choice(FILLER)} {rng.randrange(99)}", f"The parties record item {rng.randrange(999)} for reference only.")
        )
    elif kind == "remove" and len(parts) > 1:
        del parts[at]
    elif kind == "copy":
        parts.insert(rng.randrange(len(parts) + 1), parts[at])
    elif kind == "swap":
        rng.shuffle(parts)
    elif kind == "retitle":
        parts[at] = (f"{parts[at][0]} (amended)", parts[at][1])
    elif kind == "plant":
        parts[at] = (parts[at][0], f"{parts[at][1]} {rng.choice(PLANTS)}")
    elif kind == "figure":
        heading, text = parts[at]
        for old_figure, new_figure in (("fifteen (15)", "thirty (30)"), ("250,000", "300,000"), ("1.5%", "2%"), ("January 31", "March 1")):
            if old_figure in text and rng.random() < 0.6:
                text = text.replace(old_figure, new_figure, 1)
        parts[at] = (heading, text)
    else:
        heading, text = parts[at]
        cut = rng.randrange(len(text) + 1)
        parts[at] = (heading, text[:cut] + rng.choice([" as amended", "", " and so on"]) + text[cut + rng.randrange(0, 12) :])
    return parts


@pytest.mark.parametrize("seed", range(300))
def test_counting_by_searching_only_new_sections_gives_what_searching_every_section_gives(seed: int) -> None:
    """The recount keeps the counts of sections carried over unchanged and searches only the others. That is safe
    only if nothing a carried-over count depends on has changed, which is checked against a full search."""
    rng = random.Random(seed)
    parts = list(BASE)
    for _ in range(rng.randrange(1, 5)):
        parts = revise(parts, rng)
    old, new = manifest(), sections(parts)
    diff = trust_diff(old, sections(BASE), new, "v6")
    for proof, change in zip(old.findings, diff.findings, strict=True):
        places = full_recount(proof, new)[0]
        unique = next(o for o in change.obligations if o.need is Need.QUOTE_UNIQUE)
        found = any(locate(proof.evidence[0].quote, s.text, s.label) for s in new)
        assert (unique.after is E) == (found and places == 1), (proof.topic, places, unique.reason)
        assert unique.places_after == (places if found else 0) and unique.places_before == proof.evidence[0].places
        assert diff.sections_searched + diff.sections_reused == diff.sections_total == len(new)
        exists = next(o for o in change.obligations if o.need is Need.QUOTE_EXISTS)
        assert (exists.after is E) == found, "a quote is established in the revision exactly when the verifier finds it there"
        if places > 1:
            assert f"{places} places" in unique.reason


@pytest.mark.parametrize("seed", range(120))
def test_new_sections_that_repeat_nothing_never_make_a_finding_stale(seed: int) -> None:
    """No false invalidation: any number of new sections, anywhere, and a new order. Every quote still stands once."""
    rng = random.Random(seed)
    parts = list(BASE)
    for _ in range(rng.randrange(1, 6)):
        parts.insert(
            rng.randrange(len(parts) + 1), (f"{rng.choice(FILLER)} {rng.randrange(99)}", f"The parties record item {rng.randrange(999)} for reference only.")
        )
    if rng.random() < 0.5:
        rng.shuffle(parts)
    diff = trust_diff(manifest(), sections(BASE), sections(parts), "v6")
    assert diff.counts()["stale"] == 0 and all(f.after is TrustState.SUPPORTED for f in diff.findings)


@pytest.mark.parametrize("copies", [1, 2, 4])
def test_any_number_of_copies_anywhere_ends_uniqueness(copies: int) -> None:
    parts = [*BASE, *[(f"Copy {n}", f"Restated: {TERMINATION}") for n in range(copies)]]
    termination = next(f for f in trust_diff(manifest(), sections(BASE), sections(parts), "v6").findings if f.topic == "termination")
    assert termination.verdict is Verdict.STALE and termination.after is TrustState.NEEDS_REVIEW and f"{copies + 1} places" in termination.why[0]


@pytest.mark.parametrize("copies", [1, 2, 3])
def test_a_section_carried_over_more_than_once_counts_as_often_as_it_stands(copies: int) -> None:
    """The same section, label and text, standing several times in the revision: nothing about it is new, so it is
    not searched, and the count it had is taken once for each time it stands. (The fault-injection run found this
    path untested: every other duplicate in this file gets a new number, and with it a new label.)"""
    old = sections(BASE)
    new = [*old, *[old[1]] * copies]
    diff = trust_diff(manifest(), old, new, "v6")
    termination = next(f for f in diff.findings if f.topic == "termination")
    assert diff.sections_searched == 0, "an identical section is never searched again"
    assert termination.verdict is Verdict.STALE and f"{copies + 1} places" in termination.why[0]
    assert full_recount(manifest().findings[0], new)[0] == copies + 1


# ---------------------------------------------------------------- through the API

REVISED = CONTRACT.replace("fifteen (15) days", "thirty (30) days")
RELATED = CONTRACT.replace("the State of Delaware", "the State of New York")


def upload(client: TestClient | Reviewer, text: str, name: str = "agreement-v2.txt") -> str:
    response = client.post("/api/documents", files={"file": (name, text.encode("utf-8"), "text/plain")})
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


def test_a_run_accounts_for_what_its_findings_stand_on(client: TestClient) -> None:
    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    trust = client.get(f"/api/runs/{result['run_id']}/trust")
    assert trust.status_code == 200, trust.text
    body = trust.json()
    finding = body["findings"][0]
    assert body["counts"] == {"supported": 1, "needs_review": 0, "unsupported": 0} and body["runId"] == result["run_id"]
    assert [o["need"] for o in finding["obligations"]] == ["quote_exists", "quote_unique", "fact_matches", "reader_compatible", "rules_compatible"]
    assert finding["obligations"][2]["fact"] == {"kind": "duration", "value": "15 calendar days", "surface": "fifteen (15) days"}
    assert finding["recordedStatus"] == result["run"]["findings"][0]["status"]
    assert client.get(f"/api/runs/{result['run_id']}/trust").json()["manifestId"] == body["manifestId"]


def test_a_revised_contract_makes_the_finding_it_reaches_stale_and_says_why(client: TestClient) -> None:
    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    run_id, first = result["run_id"], result["document"]["id"]
    record_before = client.get(f"/api/runs/{run_id}").json()
    second = upload(client, REVISED)

    refused = client.get(f"/api/runs/{run_id}/trust/diff", params={"documentId": second})
    assert refused.status_code == 409 and "later version" in refused.json()["detail"]

    said = client.post(f"/api/documents/{second}/supersedes", json={"previousDocumentId": first})
    assert said.status_code == 201 and said.json()["supersedesDocumentId"] == first
    again = client.post(f"/api/documents/{second}/supersedes", json={"previousDocumentId": first})
    assert again.status_code == 200 and again.json()["lineageId"] == said.json()["lineageId"]

    diff = client.get(f"/api/runs/{run_id}/trust/diff", params={"documentId": second}).json()
    assert diff["counts"] == {"unchanged": 0, "revalidated": 0, "stale": 1}
    finding = diff["findings"][0]
    assert (finding["before"], finding["after"], finding["verdict"]) == ("supported", "unsupported", "stale")
    assert any("15 calendar days → 30 calendar days" in sentence for sentence in finding["why"])
    assert diff["sections"]["changed"] == ["§2 Termination for Convenience"] and diff["sectionsSearched"] == 1
    assert client.get(f"/api/runs/{run_id}").json() == record_before, "asking changes nothing on the run"

    versions = client.get(f"/api/documents/{second}/versions").json()
    assert [v["documentId"] for v in versions] == [first, second] and versions[0]["supersedesDocumentId"] is None
    assert versions[0]["snapshotHash"] != versions[1]["snapshotHash"] and versions[0]["lineageId"] == versions[1]["lineageId"]


def test_a_revision_elsewhere_in_the_contract_leaves_the_finding_supported(client: TestClient) -> None:
    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    second = upload(client, RELATED)
    assert client.post(f"/api/documents/{second}/supersedes", json={"previousDocumentId": result["document"]["id"]}).status_code == 201
    diff = client.get(f"/api/runs/{result['run_id']}/trust/diff", params={"documentId": second}).json()
    assert diff["counts"] == {"unchanged": 1, "revalidated": 0, "stale": 0} and diff["findings"][0]["why"] == []
    assert diff["sections"]["changed"] == ["§3 Governing Law"]


def test_a_version_supersedes_one_document_and_never_itself(client: TestClient) -> None:
    result = upload_and_ask(client, "What notice period applies to termination for convenience?")
    first, second, third = result["document"]["id"], upload(client, REVISED), upload(client, RELATED, "agreement-v3.txt")
    assert client.post(f"/api/documents/{second}/supersedes", json={"previousDocumentId": first}).status_code == 201
    assert client.post(f"/api/documents/{second}/supersedes", json={"previousDocumentId": third}).status_code == 409
    assert client.post(f"/api/documents/{first}/supersedes", json={"previousDocumentId": second}).status_code == 409, (
        "the first of a line cannot be placed after a later one"
    )
    assert client.post(f"/api/documents/{first}/supersedes", json={"previousDocumentId": first}).status_code == 422
    assert client.post(f"/api/documents/{third}/supersedes", json={"previousDocumentId": "0" * 16}).status_code == 404
    assert client.post(f"/api/documents/{third}/supersedes", json={"previousDocumentId": second}).status_code == 201
    through = client.get(f"/api/runs/{result['run_id']}/trust/diff", params={"documentId": third})
    assert through.status_code == 200, "a version two steps later descends from the one the run read"
    assert [v["documentId"] for v in client.get(f"/api/documents/{first}/versions").json()] == [first, second, third]


def run_under_an_earlier_reader(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """A finished run whose document row says an earlier reader read it, made the way such rows were made."""
    with monkeypatch.context() as earlier:
        earlier.setattr(ingest_module, "PARSER_VERSION", "v5")
        return upload_and_ask(client, "What notice period applies to termination for convenience?")


def test_a_run_read_by_an_earlier_reader_is_supported_when_todays_reader_finds_its_quotes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    result = run_under_an_earlier_reader(client, monkeypatch)
    assert result["document"]["parserVersion"] == "v5"  # type: ignore[index]
    trust = client.get(f"/api/runs/{result['run_id']}/trust").json()
    reader = next(o for o in trust["findings"][0]["obligations"] if o["need"] == "reader_compatible")
    assert trust["readerVersion"] == "v5" and trust["counts"] == {"supported": 1, "needs_review": 0, "unsupported": 0}
    assert reader["standing"] == "established" and reader["reason"].startswith(f"read by reader v5; the current reader is {PARSER_VERSION}; every quote")
    assert client.get(f"/api/documents/{result['document']['id']}").json()["parserVersion"] == "v5", "the run's own reading is not replaced"  # type: ignore[index]


def test_a_run_read_by_an_earlier_reader_needs_review_when_the_document_cannot_be_read_again(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    result = run_under_an_earlier_reader(client, monkeypatch)
    with SessionLocal() as session:
        document = session.get(Document, result["document"]["id"])  # type: ignore[index]
        assert document is not None
        ingest_module.original_path(document).unlink()
    trust = client.get(f"/api/runs/{result['run_id']}/trust").json()
    reader = next(o for o in trust["findings"][0]["obligations"] if o["need"] == "reader_compatible")
    assert trust["counts"] == {"supported": 0, "needs_review": 1, "unsupported": 0}
    assert reader["standing"] == "not_established" and "could not be read again" in reader["reason"]


def test_an_unfinished_run_has_nothing_to_account_for() -> None:
    with pytest.raises(Conflict, match="has not finished"):
        manifest_of(None, Run(id="r", stage="checking"))  # type: ignore[arg-type]


def test_one_workspaces_versions_and_trust_are_not_anothers(two: tuple[Reviewer, Reviewer, TestClient]) -> None:  # noqa: F811
    a, b, _ = two
    first = upload(a, CONTRACT, "agreement.txt")
    started = a.post("/api/runs", json={"documentId": first, "guidanceId": None, "question": "What notice period applies to termination for convenience?"})
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    second = upload(a, REVISED)
    assert a.post(f"/api/documents/{second}/supersedes", json={"previousDocumentId": first}).status_code == 201
    assert a.get(f"/api/runs/{run_id}/trust").status_code == 200 and a.get(f"/api/runs/{run_id}/trust/diff?documentId={second}").status_code == 200

    missing = b.get("/api/runs/0000000000000000/trust")
    for path in (f"/api/runs/{run_id}/trust", f"/api/runs/{run_id}/trust/diff?documentId={second}", f"/api/documents/{second}/versions"):
        refused = b.get(path)
        assert refused.status_code == 404 and refused.json()["detail"].split()[-2:] == missing.json()["detail"].split()[-2:], path
    assert b.post(f"/api/documents/{second}/supersedes", json={"previousDocumentId": first}).status_code == 404

    # B uploads the same two files. The rows are shared by content; what B says about them is B's own.
    b_first, b_second = upload(b, CONTRACT, "agreement.txt"), upload(b, REVISED)
    assert (b_first, b_second) == (first, second)
    assert b.get(f"/api/documents/{b_second}/versions").json() == [], "A's statement is not visible to B"
    assert b.post(f"/api/documents/{b_first}/supersedes", json={"previousDocumentId": b_second}).status_code == 201, "and does not bind B"
    assert [v["documentId"] for v in a.get(f"/api/documents/{second}/versions").json()] == [first, second]
