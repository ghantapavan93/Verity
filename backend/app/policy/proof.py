"""What code must establish before it may call a comparison a pass.

`durations.evaluate` compares a period in a verified quote with a period in the guidance. That is arithmetic. A pass
is a claim about meaning: that the two periods are about the same thing, said the same way, with nothing in the clause
that takes it back. Code can read a few signs of that from the two texts, and no more than signs; so each sign that is
missing blocks the pass, and none of them is ever a reason to pass. A blocked pass is not a failure: the status stays
the model's, shown as the model's view, with the reasons recorded.

Only a pass is gated. A shortfall ("60 days where the guidance requires 90") is reported by code as before: that
direction sends the finding to a person, and a person can see in one glance whether the 60 days were the right 60.

Everything here reads source text only: the verified quotes and the guidance. Nothing the model wrote about them (its
topic, its `observed`, its `required`) is an input, so the model's wording cannot earn a pass.

Reproduced before each check was written (2026-10-02), all of them computed passes at the time:
"on no more than 30 days' notice" against "at least 30 days"; "within 90 days after each anniversary" and "at least
90 days before the end of the term" against "90 days' notice"; "shall not be required to give 90 days' notice";
a payment term of 45 days against a termination rule of 30; a clause that is "subject to Section 14.3" when the
model was never handed Section 14.3.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .durations import (
    GuidanceRule,
    Operator,
    counts_back,
    explicit_operator,
    parse_durations,
    period_sentences,
    stated_periods,
    window_after,
    window_before,
    without_comparisons,
)

# Words that say nothing about which clause a sentence is: units, parties, modals, the vocabulary of any notice.
# fmt: off
_GENERIC = frozenset([
    "days", "weeks", "week", "months", "month", "years", "year", "calendar", "business", "working", "period", "periods", "time", "notice",
    "notices", "notify", "written", "writing", "prior", "advance", "party", "parties", "either", "other", "each", "both", "agreement",
    "agreements", "contract", "contracts", "terms", "shall", "must", "will", "would", "should", "have", "been", "being", "does", "least", "most",
    "more", "less", "than", "fewer", "longer", "shorter", "later", "earlier", "minimum", "maximum", "exceed", "within", "before", "after",
    "below", "above", "upon", "with", "without", "that", "this", "these", "those", "their", "there", "such", "which", "when", "where", "what",
    "from", "into", "under", "over", "require", "requires", "required", "requirement", "need", "needs", "needed", "standard", "policy",
    "guidance", "accept", "accepts", "acceptable", "anything", "nothing", "review", "reviews", "able", "allow", "allows", "allowed", "permit",
    "permits", "permitted", "provide", "provides", "provided", "customer", "customers", "provider", "providers", "company", "supplier", "vendor",
    "client", "only", "also", "then", "given", "give", "gives",
])
# fmt: on
_WORD = re.compile(r"[a-z]{4,}")
# How many of a guidance sentence's own words the quotes must carry before code treats them as being about the same point.
CONCEPT_WORDS_NEEDED = 2

# The contract's own bound, where the guidance vocabulary has no word for it: "notice of less than 30 days".
_BELOW = re.compile(r"(?<!not )(?<!no )(?<!nor )\b(?:less than|fewer than|shorter than|under|below)\s*\(?\s*$", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:not|no|never|without|nor|neither|cannot|waives?|waived)\b", re.IGNORECASE)
# A condition or an exception anywhere in the quote. A bare "if" is not listed: it is how most rights are granted.
_CARVE_OUT = re.compile(
    r"\b(?:unless|except|excluding|provided(?:,)? (?:that|however)|notwithstanding|subject to|save (?:as|that|for)|other than|only if"
    r"|so long as|as long as|in which case|however|but not|to the extent)\b",
    re.IGNORECASE,
)


def concept_stems(text: str) -> set[str]:
    """The words of a sentence that could say what it is about, by their first five letters, so that "terminate"
    and "termination" are one word."""
    return {word[:5] for word in _WORD.findall(text.lower()) if word not in _GENERIC}


def same_point(quotes: Sequence[str], guidance: str) -> bool:
    """Whether the quotes name what the guidance is about: every sentence of the guidance that states a period shares
    words of its own with them. With one such sentence that is the rule itself; with several, a quote that is about
    one of them is not shown to be about "the guidance". A sentence with no word of its own about a subject ("Anything
    below 30 days requires review.") restates a period and is about whatever the others are about; guidance with no
    such word anywhere is about nothing code can check. No sentence is chosen by the model's topic here."""
    quoted = set().union(*(concept_stems(q) for q in quotes)) if quotes else set()
    subjects = [about for about in (concept_stems(sentence) for sentence in period_sentences(guidance)) if about]
    return bool(subjects) and all(len(about & quoted) >= min(CONCEPT_WORDS_NEEDED, len(about)) for about in subjects)


def _quote_operator(quote: str, mention_index: int) -> Operator | None:
    mention = parse_durations(quote)[mention_index]
    if _BELOW.search(window_before(quote, mention)):
        return Operator.MAXIMUM
    return explicit_operator(quote, mention)


def _negated(quote: str, mention_index: int) -> str | None:
    """A negation word near the period, once the comparison phrases that contain one ("not less than") are set aside."""
    mention = parse_durations(quote)[mention_index]
    before = without_comparisons(window_before(quote, mention))
    found = _NEGATION.search(before) or _NEGATION.search(window_after(quote, mention))
    return found.group(0).lower() if found else None


def pass_blockers(quotes: Sequence[str], guidance: str, rule: GuidanceRule, dependencies: Sequence[str] = (), passages: Sequence[str] = ()) -> list[str]:
    """Every reason code cannot call this comparison a pass; empty when it found none. ``dependencies`` are the
    sections a verified passage points at that the model was not handed (`runs.status.unseen_references`).
    ``passages`` are the whole sentences the quotes sit in, from the stored section text: a quote is the shortest
    passage that carries the point, and the words that take it back are often just outside it."""
    blockers: list[str] = []

    if not same_point(quotes, guidance):
        blockers.append("the quote and the guidance share too few words to show they speak of the same point")

    guidance_counts_back = any(counts_back(guidance, m) for m in parse_durations(guidance) if m.duration is not None)
    for quote in quotes:
        for index, mention in enumerate(parse_durations(quote)):
            if mention.duration is None:
                continue
            # Said the same way. A period the contract states as a ceiling does not meet a floor, and the reverse; a
            # range in the guidance is met only by a period stated plainly.
            operator = _quote_operator(quote, index)
            if operator is not None and (rule.maximum is not None or operator is not rule.operator):
                wanted = "range" if rule.maximum is not None else _BOUND[rule.operator]
                blockers.append(f'the quote states its period as a {_BOUND[operator]} ("{mention.surface}") and the guidance sets a {wanted}')
            negation = _negated(quote, index)
            if negation is not None:
                blockers.append(f'a negation stands beside the period ("{negation}"), and code does not read what it negates')
            # Counted the same way. "90 days before the end of the term" is a deadline; "90 days' notice" is a length.
            if counts_back(quote, mention) != guidance_counts_back:
                blockers.append("one of the two periods is counted back from an event and the other is not")
    for passage in passages or quotes:
        carve_out = _CARVE_OUT.search(passage)
        if carve_out is not None:
            blockers.append(f'the clause carries a condition or an exception ("{carve_out.group(0).lower()}")')
    quoted_periods = set().union(*(stated_periods(q) for q in quotes)) if quotes else set()
    beside = set().union(*(stated_periods(p) for p in passages)) - quoted_periods if passages else set()
    if beside:
        blockers.append("the sentence around the quote states another period that the quote left out")

    # Read whole. A passage that points at a section the model never saw may be changed by it.
    if dependencies:
        blockers.append(f"the quoted passage refers to {', '.join(dependencies)}, which the model was not handed")
    return list(dict.fromkeys(blockers))


_BOUND = {Operator.MINIMUM: "floor", Operator.MAXIMUM: "ceiling", Operator.EXACT: "fixed period"}
