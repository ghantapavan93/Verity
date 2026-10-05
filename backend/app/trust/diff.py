"""Trust diff: a revised document arrived; which findings does the revision reach, and what becomes of them?

    the manifest of a run on version 1   +   the sections of version 2   ->   an account of every finding

Nothing is written. The run, its findings and its manifest stay what they were; the account is derived, and can be
derived again.

Sections are compared by content, never by position or by a database id. A section of the old version is *identical*
when the new version holds a section with the same label and text; otherwise it is *aligned* to its counterpart (the
same text under a new number, or the same number and heading, or the same heading) or it is gone.

Each obligation is then asked whether the revision reaches what it depends on:

    QUOTE_EXISTS depends on one section. If that section is identical in the new version the obligation is not
    looked at. Otherwise the quote is looked for in the counterpart, then everywhere; and if the words are gone but
    the text that surrounded them still marks one place, the passage standing there now is read.

    QUOTE_UNIQUE depends on every section. It is counted again, and only the sections whose content is new are
    searched: a section carried over unchanged contributes the count it had.

    FACT_MATCHES depends on the quoted span. While the quote stands, so does the fact. When the passage has changed,
    the values it now states are parsed, and a single different value of the same kind is a contradiction that
    names both: "15 calendar days -> 30 calendar days".

A finding comes out UNCHANGED (its evidence sections are identical and every obligation stands as it did),
REVALIDATED (a section it cites changed, the evidence was found again, and every obligation stands as it did), or
STALE (some obligation no longer stands as it did). A stale finding is not wrong; it is no longer shown to be
supported by the document in front of the reader.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from ..verify.spans import locate
from .compile import unique_obligation
from .facts import facts_in
from .model import Evidence, FindingProof, Need, Obligation, SectionText, Standing, TrustManifest, TrustState, derive, snapshot_hash

SHOWN_PASSAGE = 240  # characters of a changed passage carried in a reason


class Verdict(StrEnum):
    UNTOUCHED = "untouched"  # an obligation the revision does not reach; kept without being answered again
    HELD = "held"  # answered again, the same standing
    RELOCATED = "relocated"  # answered again, the same standing, its evidence found in another section
    CHANGED = "changed"  # an obligation whose standing is not what it was
    UNCHANGED = "unchanged"  # a finding whose evidence the revision did not touch
    REVALIDATED = "revalidated"  # a finding whose evidence changed around it and was established again
    STALE = "stale"  # a finding with an obligation that no longer stands as it did


@dataclass(frozen=True)
class ObligationChange:
    obligation_id: str
    need: Need
    before: Standing
    after: Standing
    verdict: Verdict
    reason: str
    # For a uniqueness obligation: how many places the quote stood in the whole document before, and stands in now.
    places_before: int | None = None
    places_after: int | None = None


@dataclass(frozen=True)
class FindingChange:
    finding_id: str
    ordinal: int
    topic: str
    before: TrustState
    after: TrustState
    verdict: Verdict
    why: tuple[str, ...]  # one sentence per obligation whose standing changed
    obligations: tuple[ObligationChange, ...]


@dataclass(frozen=True)
class SectionChanges:
    identical: int
    changed: tuple[str, ...]  # named as the old version names them
    removed: tuple[str, ...]
    added: tuple[str, ...]

    @property
    def any(self) -> bool:
        return bool(self.changed or self.removed or self.added)


@dataclass(frozen=True)
class TrustDiff:
    manifest_id: str
    run_id: str
    from_snapshot: str
    to_snapshot: str
    sections: SectionChanges
    findings: tuple[FindingChange, ...]
    sections_total: int  # in the revised document
    sections_searched: int  # of those, how many had to be searched to count the quotes again: every one whose content is new
    sections_reused: int  # and how many were carried over unchanged, each contributing the count it had

    def __post_init__(self) -> None:
        # Every section of the revision is accounted for, one way or the other. A count that left one out would be
        # a count of part of the document, and uniqueness is a statement about all of it.
        if self.sections_reused + self.sections_searched != self.sections_total:
            raise ValueError("a section of the revision was neither searched nor carried over")

    def counts(self) -> dict[str, int]:
        return {v.value: sum(1 for f in self.findings if f.verdict is v) for v in (Verdict.UNCHANGED, Verdict.REVALIDATED, Verdict.STALE)}


# ---------------------------------------------------------------------------------------------- aligning two versions


def _heading(section: SectionText) -> str:
    return re.sub(r"[\W_]+", " ", section.heading).strip().casefold()


SHINGLE_WORDS = 4  # words per shingle when two sections are compared by what they say
SAME_SECTION = 0.5  # the share of shingles two sections must have in common to be called one section, revised


def _shingles(section: SectionText) -> frozenset[tuple[str, ...]]:
    words = re.findall(r"\w+", section.text.casefold())
    return frozenset(tuple(words[at : at + SHINGLE_WORDS]) for at in range(max(1, len(words) - SHINGLE_WORDS + 1)))


def _overlap(a: frozenset[tuple[str, ...]], b: frozenset[tuple[str, ...]]) -> float:
    """Jaccard similarity of two shingle sets: the share of their word sequences they have in common."""
    return len(a & b) / len(a | b) if a and b else 0.0


@dataclass(frozen=True)
class Alignment:
    counterpart: dict[str, SectionText]  # old section key -> the section of the new version that took its place
    changes: SectionChanges


def align(old: Sequence[SectionText], new: Sequence[SectionText]) -> Alignment:
    """Which section of the new version each changed section of the old one became. Each new section is taken once.

    Four passes over what is not identical, strongest evidence first: the same text under another label (the
    section was renumbered or retitled); the same number and heading; the same heading where it names one section
    on each side; and, for a section whose heading and text were both revised, the section it shares most of its
    wording with, when that is at least half (word shingles, best pairs first). A number alone is never enough:
    inserting a clause moves every number after it.
    """
    new_keys = Counter(section.key for section in new)
    old_keys = Counter(section.key for section in old)
    loose_old = [s for s in old if not new_keys[s.key]]
    loose_new = [s for s in new if not old_keys[s.key]]
    counterpart: dict[str, SectionText] = {}

    def pair(key_of: Callable[[SectionText], Hashable | None], only_unique: bool) -> None:
        taken = {id(s) for s in counterpart.values()}
        free = [s for s in loose_new if id(s) not in taken]
        by_key: dict[Hashable | None, list[SectionText]] = {}
        for section in free:
            by_key.setdefault(key_of(section), []).append(section)
        wanted = Counter(key_of(s) for s in loose_old if s.key not in counterpart)
        for section in loose_old:
            key = key_of(section)
            candidates = by_key.get(key, [])
            if section.key in counterpart or not key or not candidates:
                continue
            if only_unique and (len(candidates) != 1 or wanted[key] != 1):
                continue
            counterpart[section.key] = candidates.pop(0)

    pair(lambda s: s.content_hash, only_unique=False)
    pair(lambda s: (s.number, _heading(s)) if s.number and _heading(s) else None, only_unique=True)
    pair(lambda s: _heading(s) or None, only_unique=True)
    # What is still loose is compared by wording. Only the leftovers are compared, so the cost is theirs alone.
    taken = {id(s) for s in counterpart.values()}
    rest_old = [(s, _shingles(s)) for s in loose_old if s.key not in counterpart]
    rest_new = [(s, _shingles(s)) for s in loose_new if id(s) not in taken]
    scored = sorted(
        ((_overlap(a, b), i, j) for i, (_, a) in enumerate(rest_old) for j, (_, b) in enumerate(rest_new)),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    used_old: set[int] = set()
    used_new: set[int] = set()
    for score, i, j in scored:
        if score < SAME_SECTION:
            break
        if i not in used_old and j not in used_new:
            counterpart[rest_old[i][0].key] = rest_new[j][0]
            used_old.add(i)
            used_new.add(j)
    taken = {id(s) for s in counterpart.values()}
    return Alignment(
        counterpart,
        SectionChanges(
            identical=sum(1 for s in old if new_keys[s.key]),
            changed=tuple(s.name for s in loose_old if s.key in counterpart),
            removed=tuple(s.name for s in loose_old if s.key not in counterpart),
            added=tuple(s.name for s in loose_new if id(s) not in taken),
        ),
    )


# ---------------------------------------------------------------------------------------------- one quote, taken forward


def passage_now(evidence: Evidence, section: SectionText) -> str | None:
    """What stands where the quote stood: the text between its recorded surroundings, when each still marks one
    place. A quote that opened its section is bounded by the section's start, and one that closed it by its end;
    otherwise the text recorded on that side must stand exactly once. Anything less and there is no place to speak of."""
    text = section.text
    if evidence.start == 0:
        start = 0
    elif evidence.before and text.count(evidence.before) == 1:
        start = text.index(evidence.before) + len(evidence.before)
    else:
        return None
    if not evidence.after:
        return text[start:] or None
    following = [at.start() for at in re.finditer(re.escape(evidence.after), text) if at.start() >= start]
    return text[start : following[0]] if len(following) == 1 else None


@dataclass(frozen=True)
class Found:
    """Where a quote stands in the revised document, or what stands in its place."""

    section: SectionText | None = None  # where the quote was found
    moved: bool = False  # found, but not in the section that took the cited one's place
    passage: str | None = None  # not found: the passage now standing where it stood
    stood_in: SectionText | None = None  # not found: the section that took the cited one's place


def find_again(evidence: Evidence, alignment: Alignment, new: Sequence[SectionText]) -> Found:
    home = alignment.counterpart.get(evidence.section_key)
    if home is not None and locate(evidence.quote, home.text, home.label) is not None:
        return Found(section=home)
    for section in new:
        if section is not home and locate(evidence.quote, section.text, section.label) is not None:
            return Found(section=section, moved=True)
    return Found(passage=passage_now(evidence, home) if home is not None else None, stood_in=home)


def _shown(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= SHOWN_PASSAGE else flat[: SHOWN_PASSAGE - 1] + "…"


def _fact_after(old: Obligation, found: Found) -> tuple[Standing, str]:
    assert old.fact is not None
    if found.section is not None:
        return Standing.ESTABLISHED, old.reason
    if found.passage is None:
        return Standing.NOT_ESTABLISHED, f"the passage that stated {old.fact.value} is no longer found"
    now = [fact for fact in facts_in(found.passage) if fact.kind is old.fact.kind]
    values = sorted({fact.value for fact in now})
    if old.fact.value in values:
        return Standing.ESTABLISHED, f"the passage was reworded and still states {old.fact.value}"
    if len(values) == 1:
        return Standing.CONTRADICTED, f"{old.fact.value} → {values[0]}: the passage the finding quoted now states a different {old.fact.kind.value}"
    return Standing.NOT_ESTABLISHED, f"the passage that stated {old.fact.value} no longer states one {old.fact.kind.value}"


def trust_diff(manifest: TrustManifest, old: Sequence[SectionText], new: Sequence[SectionText], new_reader_version: str) -> TrustDiff:
    """Take a run's manifest to a revised document. ``old`` are the sections the run read, ``new`` the revision's."""
    to_snapshot = snapshot_hash(new_reader_version, tuple(new))
    alignment = align(old, new)
    new_keys = Counter(section.key for section in new)
    old_keys = {section.key for section in old}
    # The accounting. Every section of the revision is one of two kinds. Its label and text are those of a section
    # the run read: then how often each quote stands in it is already known, zero included, because the manifest
    # counted every section of the old version. Or they are not: then it is searched, for every quote. A section
    # of the old version that is gone contributes nothing, because nothing in the revision carries its key.
    fresh = [section for section in new if section.key not in old_keys]
    carried_over = len(new) - len(fresh)
    names = {section.key: section.name for section in new}
    same_document = to_snapshot == manifest.snapshot_hash

    def recount(evidence: Evidence) -> tuple[int, str]:
        carried = {o.section_key: o.count * new_keys[o.section_key] for o in evidence.occurrences if new_keys[o.section_key]}
        for section in fresh:
            located = locate(evidence.quote, section.text, section.label)
            if located is not None:
                carried[section.key] = carried.get(section.key, 0) + located.count
        return sum(carried.values()), ", ".join(names[key] for key in carried)

    findings = []
    for proof in manifest.findings:
        found = {e.span: None if not e.located or new_keys[e.section_key] else find_again(e, alignment, new) for e in proof.evidence}
        by_span = {e.span: e for e in proof.evidence}
        changes: list[ObligationChange] = []
        after: list[Obligation] = []
        for old_obligation in proof.obligations:
            evidence = by_span.get(old_obligation.span) if old_obligation.span is not None else None
            where = found.get(old_obligation.span) if old_obligation.span is not None else None
            standing, reason, verdict = old_obligation.standing, old_obligation.reason, Verdict.UNTOUCHED
            is_count = old_obligation.need is Need.QUOTE_UNIQUE and evidence is not None and evidence.located
            places_before = evidence.places if is_count and evidence is not None else None
            places_after = places_before
            if evidence is None or same_document or not evidence.located:
                pass  # depends on the code, or nothing changed, or there was never a quote to take forward
            elif old_obligation.need is Need.QUOTE_UNIQUE:
                still_found = where is None or where.section is not None
                places, named = recount(evidence) if still_found else (0, "")
                places_after = places
                recounted = unique_obligation(old_obligation.obligation_id, evidence.span, still_found, places, named if places > 1 else "")
                standing, reason, verdict = recounted.standing, recounted.reason, Verdict.HELD
            elif where is None:
                pass  # the cited section is identical in the revision: the quote and its facts are not looked at
            elif old_obligation.need is Need.QUOTE_EXISTS:
                if where.section is not None:
                    verdict = Verdict.RELOCATED if where.moved else Verdict.HELD
                    reason = f"the quoted words stand in {where.section.name}" + (
                        ", where they were not cited" if where.moved else ", which was revised around them"
                    )
                elif where.passage is not None and where.stood_in is not None:
                    standing, reason = Standing.CONTRADICTED, f"the cited passage in {where.stood_in.name} now reads: “{_shown(where.passage)}”"
                elif where.stood_in is not None:
                    standing, reason = Standing.NOT_ESTABLISHED, f"the quoted words no longer stand in {where.stood_in.name} or anywhere else in the revision"
                else:
                    standing, reason = (
                        Standing.NOT_ESTABLISHED,
                        f"{evidence.section_name} is not in the revision, and the quoted words stand nowhere else in it",
                    )
            elif old_obligation.need is Need.FACT_MATCHES:
                standing, reason = _fact_after(old_obligation, where)
                verdict = Verdict.HELD
            if standing is not old_obligation.standing:
                verdict = Verdict.CHANGED
            changes.append(
                ObligationChange(
                    old_obligation.obligation_id, old_obligation.need, old_obligation.standing, standing, verdict, reason, places_before, places_after
                )
            )
            after.append(replace(old_obligation, standing=standing, reason=reason))
        state = derive(tuple(after))
        changed = [c for c in changes if c.verdict is Verdict.CHANGED]
        touched = any(c.need is not Need.QUOTE_UNIQUE and c.verdict is not Verdict.UNTOUCHED for c in changes)
        verdict = Verdict.STALE if changed or state is not proof.state else Verdict.REVALIDATED if touched else Verdict.UNCHANGED
        findings.append(
            FindingChange(proof.finding_id, proof.ordinal, proof.topic, proof.state, state, verdict, tuple(c.reason for c in changed), tuple(changes))
        )
    return TrustDiff(
        manifest_id=manifest.manifest_id, run_id=manifest.run_id, from_snapshot=manifest.snapshot_hash, to_snapshot=to_snapshot,
        sections=alignment.changes, findings=tuple(findings), sections_total=len(new), sections_searched=len(fresh), sections_reused=carried_over,
    )  # fmt: skip


def full_recount(proof: FindingProof, new: Sequence[SectionText]) -> dict[int, int]:
    """Every quote of a finding counted across the whole revision, searching every section. The control for the
    incremental count above: the two must agree, and a test holds them to it."""
    return {e.span: sum(located.count for s in new if (located := locate(e.quote, s.text, s.label)) is not None) for e in proof.evidence if e.located}


__all__ = ["Alignment", "FindingChange", "ObligationChange", "SectionChanges", "TrustDiff", "Verdict", "align", "full_recount", "passage_now", "trust_diff"]
