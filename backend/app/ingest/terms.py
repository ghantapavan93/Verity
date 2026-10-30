"""Where a contract defines a term: the one reader of it, which the links, the reading's labels and the family
fingerprint each ask (second wave of the stress test, 2026-10-30).

Until then each had its own pattern and they disagreed. The links that hand a clause's definitions to the model
(runs/links.py, retrieval-v3) read every pair of quotation marks a contract is drafted with and up to three words before
the defining verb; the reading's section labels (ingest/sections.split_lead_in) read three kinds of quotes with the verb
right after the term; the family fingerprint read double quotes only. A UK definition in single quotes was linked but
neither labelled nor fingerprinted, and '"including" means "including without limitation"' was labelled "including", a
word of construction the links refuse. This is the links' reader, which was the widest and the one measured
(retrieval-v3 on CUAD), moved here unchanged so that every reader asks the same question; what a reader keeps of the
answer is its own (the fingerprint keeps capitalised terms).
"""

from __future__ import annotations

import re
from collections.abc import Iterator

# A defining sentence: the term between a pair of quotation marks, up to three words, then a defining verb. Every pair a
# contract is drafted with (retrieval-v3, stress test 2026-10-30, retrieval corner): until then only double quotes were
# read, so a definition in single quotes or guillemets, as UK and EU drafting writes them, was never linked. A single
# quotation mark opens a term only where no letter precedes it and closes one only where none follows, so an apostrophe
# never does ("the Parties' and the Members' interest includes"), and a term may hold one ("‘Customer’s Data’").
QUOTED = (
    r"(?:[“\"](?P<double>[^”\"]{1,60})[”\"]"
    r"|‘(?<!\w‘)(?P<curly>(?:[^‘’\n]|’(?=\w)){1,60}?)’(?!\w)"
    r"|'(?<!\w')(?<!'')(?P<straight>(?:[^'\n]|'(?=\w)){1,60}?)'(?!\w)"
    r"|«\s?(?P<guillemet>[^«»\n]{1,60}?)\s?»"
    r"|„(?P<low>[^„“”\n]{1,60})[“”])"
)
DEFINES = re.compile(QUOTED + r"(?:\s+[\w-]+){0,3}?\s+(?:means|mean|shall mean|has the meaning|have the meaning|is to|are to|refers to|includes)\b")
# The words of construction an interpretation clause defines ('"including" means "including without limitation"', '"to"
# means "to but excluding"'). They are not terms: every clause uses them, so their definition took one of the two link
# places from whatever the clause cites (CUAD, 2026-10-30: 198 of 17,850 runs).
CONSTRUCTION = frozenset(
    {"to", "from", "until", "till", "through", "include", "includes", "including", "or", "and", "any", "will", "shall", "may"}
    | {"herein", "hereof", "hereunder", "hereto", "hereby", "to the extent"}
)
OPENING_QUOTE = "“\"‘'«„"


def term_of(match: re.Match[str], text: str) -> str | None:
    """The term a defining sentence (a match of ``DEFINES`` in ``text``) defines, or None when it defines a word of
    construction: one of ``CONSTRUCTION``, a lower-case word the definition quotes again ('"including" means "including
    without limitation"'), or no word at all ('"$" means', '"[***]" means')."""
    term = (match.group(match.lastgroup or 0) or "").strip()
    if not any(ch.isalpha() for ch in term) or term.casefold() in CONSTRUCTION:
        return None
    if term.islower() and re.compile(rf"\s*[{OPENING_QUOTE}]\s?{re.escape(term)}(?!\w)", re.IGNORECASE).match(text, match.end()):
        return None
    return term


def definitions(text: str) -> Iterator[tuple[str, re.Match[str]]]:
    """Each term the text defines, in order, with the match of its defining sentence."""
    for match in DEFINES.finditer(text):
        term = term_of(match, text)
        if term:
            yield term, match


def defined_at_start(text: str) -> str | None:
    """The term a text defines where it opens with the definition ('"Agreement" means …'), or None."""
    match = DEFINES.match(text)
    return term_of(match, text) if match else None
