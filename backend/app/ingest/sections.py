"""Turn a stream of blocks (headings and body text) into numbered sections.

A section starts at every heading. Text before the first heading becomes the title block.
Numbers come from the heading text when it starts with one ("12.4 Termination"); otherwise, for a
DOCX heading Word numbers itself, the number Word prints for it (reader v14, Block.word_number, worked
out from the list's own counters by readers._Numbering). A heading that states no number and whose
number the reader cannot say exactly is labelled by its heading alone: never a number the document does
not show.

Many templates (Common Paper among them) style the whole clause as a heading paragraph:
"Access and Use.  During the Subscription Period …". Such a paragraph is split into a short
heading and a body at its first sentence break, so the clause text is retrievable and quotable.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from ..verify.spans import bounded, verification_pass

# Nine digits per part: a "number" longer than that is not a clause number, and Python refuses to parse thousands of digits.
HEADING_NUMBER = re.compile(r"^\s*(?:(?:Section|Clause|Article)\s+)?(\d{1,9}(?:\.\d{1,9})*)[.)]?\s+(.*\S)\s*$", re.IGNORECASE)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# "Agreement" means …: a definition is labelled by its term and the whole sentence is its body.
DEFINED_TERM = re.compile(r"^[“\"‘']([^”\"’']{1,60})[”\"’']\s+(?:means|has the meaning|shall mean|shall have the meaning|includes)", re.IGNORECASE)
SENTENCE_MIN_WORDS = 6
MAX_LEAD_IN_CHARS = 60
MAX_LEAD_IN_WORDS = 8
PARAGRAPH_SEPARATOR = "\n\n"
MAX_SECTION_CHARS = 6000  # a section longer than this is split so retrieval and the model see it whole
MAX_HEADING_CHARS = 110


# How far a stated clause number may run ahead of the last one. Measured on the 510 CUAD texts under reader v6
# (2026-10-08): between consecutive numbered headings the top-level number moved by 0 or 1 in 4,879 of 5,418 steps and by
# 2 to 20 in 298 (clauses written inline are not headings, so numbering skips); of the 17 forward jumps past 20, the eight
# inspected were all an address, a year, a registration or a table figure ("10450 Science Center Drive", "180 Days").
# A step back (224) is a restart, as in an exhibit.
MAX_NUMBER_GAP = 20


def continues_numbering(number: str, last_top: int) -> bool:
    """Whether a heading's stated number can be a clause number after a heading numbered ``last_top`` (0 before any)."""
    top = number.split(".", 1)[0]
    return top.isdigit() and int(top) <= last_top + MAX_NUMBER_GAP


# The title a clause states before its first sentence: "Governing Law." in "13.2 Governing Law. This Agreement …".
CLAUSE_TITLE = re.compile(r"^([^.:;]{2,60})[.:](?:\s|$)")
TITLE_SMALL_WORDS = frozenset({"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"})


def inline_clause(paragraph: str, last_top: int) -> tuple[str, str] | None:
    """(number, title) of a paragraph that opens with a numbered clause title ("6. WRF Patents. Washington …", "10. Term
    and Termination."), or None. The number must continue the numbering without going back (a list inside a clause
    restarts at 1) and the title must read as one: at most eight words, every significant word capitalised. A numbered
    sentence ("1.1 Cargill agrees to perform …", "30 days after notice. …") is not a title."""
    match = HEADING_NUMBER.match(paragraph)
    if not match:
        return None
    number = match.group(1)
    if int(number.split(".", 1)[0]) < last_top or not continues_numbering(number, last_top):
        return None
    title = CLAUSE_TITLE.match(match.group(2))
    if not title:
        return None
    words = title.group(1).split()
    significant = [w for w in words if w.lower() not in TITLE_SMALL_WORDS]
    if len(words) > MAX_LEAD_IN_WORDS or not significant or not all(w[0].isupper() or not w[0].isalpha() for w in significant):
        return None
    return number, title.group(1).strip()


# A section longer than MAX_SECTION_CHARS is stored as parts headed "<heading> (part N)"; `_push` writes the heading and
# `clause_label_in` reads it back, through these two definitions only.
PART_HEADING = re.compile(r"^(?P<base>.*) \(part (?P<index>\d+)\)$")


def part_heading(heading: str, index: int) -> str:
    return f"{heading} (part {index})"


def clause_label_in(sections: Sequence[tuple[str, str, str]], index: int, start: int) -> str | None:
    """``clause_label`` for a passage at ``start`` of ``sections[index]`` (each section as number, heading, text, in
    reading order). A part after the first is read after the parts before it, because they are one section of the source
    split for size: a clause that opened in part 2 still holds a passage at the top of part 3, unless a numbered paragraph
    outside it came between, which ends it as within one part."""
    number, heading, text = sections[index]
    texts = [text]
    part = PART_HEADING.match(heading)
    if part:
        expected, i = int(part.group("index")) - 1, index - 1
        while expected >= 1 and i >= 0:
            earlier_number, earlier_heading, earlier_text = sections[i]
            earlier = PART_HEADING.match(earlier_heading)
            first = expected == 1 and earlier_heading == part.group("base")
            if earlier_number != number or not (first or (earlier and earlier.group("base") == part.group("base") and int(earlier.group("index")) == expected)):
                break
            texts.insert(0, earlier_text)
            expected, i = expected - 1, i - 1
    offset = sum(len(t) + len(PARAGRAPH_SEPARATOR) for t in texts[:-1])
    top = number.split(".", 1)[0]
    return clause_label(PARAGRAPH_SEPARATOR.join(texts), offset + start, int(top) if top.isdigit() else 0)


def _ends_clause(number: str, clause: str) -> bool:
    """A numbered paragraph ends the clause found before it unless it is one of the clause's own sub-numbers ("13.2.1"
    within 13.2) or a list that starts again below it ("1." inside clause 4)."""
    top, clause_top = number.split(".", 1)[0], clause.split(".", 1)[0]
    return top.isdigit() and int(top) >= int(clause_top) and not number.startswith(clause + ".")


# A sentence inside a paragraph that may open a clause: "… in writing. 3.2 Governing Law. This …" (real-model smoke on a
# printed PDF, 2026-10-08: the governing-law quote was labelled "§3.1 Notices").
SENTENCE_START = re.compile(r"(?<=[.;:])\s+(?=\d)")

# A clause number as a document opens a clause with it: "12.3 Notwithstanding …", "6. TERMINATION.", "Section 5 Fees"
# at the start of a paragraph, or "… in writing. 4.1 Late fees …" after a sentence end. A bare whole number must be
# followed by "." or ")" so that "30 days after notice" is not clause 30, and must open a titled clause (`inline_clause`)
# so that a list item ("2. invoice monthly;") is not clause 2; a cross-reference ("Subject to Section 9") opens nothing.
_OPENING_NUMBER = r"(\d{1,9}(?:\.\d{1,9})+|\d{1,9}(?=[.)]))[.)]?[ \t]+(?=\S)"
_CLAUSE_OPENING = re.compile(
    rf"^[ \t]*(?:(?:Section|Clause|Article)[ \t]+(\d{{1,9}}(?:\.\d{{1,9}})*)[.)]?[ \t]+(?=\S)|{_OPENING_NUMBER})"
    # After a sentence end the opening must carry a title: "Fees are due. 1.5 times the fee" opens nothing (bug hunt).
    rf"|(?<=[.;:])[ \t]+{_OPENING_NUMBER}(?-i:(?=[A-Z]))",
    re.IGNORECASE | re.MULTILINE,
)


OPENING_WINDOW = 200  # characters: a number, a title of at most eight words, its stop


def clause_openings(text: str) -> list[tuple[str, int]]:
    """(number, offset) of every clause the text opens, in order, the offset where the number is printed. A dotted
    number ("12.3") opens a clause wherever it opens; a whole number only where it opens a titled clause ("6. WRF
    Patents."), because a numbered list restarts at 1 inside any clause (triage, 2026-10-09)."""
    found: list[tuple[str, int]] = []
    for match in _CLAUSE_OPENING.finditer(text):
        index = next(i for i, group in enumerate(match.groups(), start=1) if group)
        number, start = match.group(index), match.start(index)
        if "." not in number:
            # A clause title is read from at most OPENING_WINDOW characters: one line of thousands of openings cost
            # a scan to its end per opening, quadratic (security audit, 2026-10-09).
            end = text.find("\n", start, start + OPENING_WINDOW)
            if inline_clause(text[start : end if end >= 0 else start + OPENING_WINDOW], int(number)) is None:
                continue
        found.append((number, start))
    return found


def stated_clause_numbers(texts: Sequence[str]) -> set[str]:
    """Every number the texts open a clause with, as printed (`clause_openings`): what a reference may name although no
    section of this reading carries it (a numbered paragraph inside a stored section, or a document read without
    numbering)."""
    return {number for text in texts for number, _ in clause_openings(text)}


def follows(previous: str, number: str) -> bool:
    """Whether a clause numbered ``number`` can be the next one after ``previous``: its first sub-clause (3 then 3.1), a
    later sibling a short step on (3.1 then 3.2 to 3.4), or the next top-level clause bare or at .1 (5.5 then 6 or 6.1,
    16 then 17 or 18). A list item, a cross-reference or an abbreviation ("Amendment No. 3 Joinder") rarely does."""
    a, b = previous.split("."), number.split(".")
    if b[:-1] == a and b[-1] == "1":
        return True
    if len(a) == len(b) and a[:-1] == b[:-1] and a[-1].isdigit() and b[-1].isdigit():
        return 0 < int(b[-1]) - int(a[-1]) <= MAX_SIBLING_STEP
    if a[0].isdigit() and b[0].isdigit() and 0 < int(b[0]) - int(a[0]) <= MAX_TOP_STEP:
        return len(b) == 1 or (len(b) == 2 and b[1] == "1")
    return False


MAX_SIBLING_STEP = 3
MAX_TOP_STEP = 2


def clause_label(text: str, start: int, seed: int = 0) -> str | None:
    """Where a passage starting at ``start`` of a section's text sits, read from that text alone: the clause whose
    opening ("13.2 Governing Law. This …") comes last before it, as "§13.2 Governing Law", or None.

    A reading keeps a clause written inline as body under the last standalone heading, so a section's label can name a
    different clause than the passage is in ("§5 Intellectual Property (part 3)" for a governing-law clause; QA campaign,
    2026-10-08). Every number returned is printed as an opening before the passage: at the start of a paragraph, or after
    a sentence inside one. A numbered paragraph that is not part of the clause found (not its sub-number, not a list
    restarting below it: "13.3 the Parties agree …" after 13.2) ends it. ``seed`` is the section's own top-level number: a
    clause numbered below it is a list inside the section ("1. Indemnification by Licensee." under §8), never a clause of
    the document. Earlier parts of a split section are read by `clause_label_in`.

    Inside a paragraph (a printed PDF often runs clauses together: "… in writing. 3.2 Governing Law. This …"), only the
    clause that follows the one found (`follows`) moves the label, and only after a real sentence end. Anything else
    there that could open a clause, a number that follows without a title, or an opening after an abbreviation's
    period ("Amendment No. 3 Joinder") leaves the clause unknown; nothing inside a paragraph names a clause when none was
    found before it. None leaves the section's label."""
    found: tuple[str, str] | None = None
    last_top = seed
    offset = 0
    for paragraph in text.split(PARAGRAPH_SEPARATOR):
        if offset > start:
            break
        clause = inline_clause(paragraph, last_top)
        if clause is not None:
            found, last_top = clause, int(clause[0].split(".", 1)[0])
        elif found is not None and (numbered := HEADING_NUMBER.match(paragraph)) and _ends_clause(numbered.group(1), found[0]):
            found = None
        for sentence in SENTENCE_START.finditer(paragraph):
            if found is None or offset + sentence.end() > start:
                break
            rest = paragraph[sentence.end() :]
            numbered = HEADING_NUMBER.match(rest)
            if numbered is None:
                continue
            number, opened = numbered.group(1), inline_clause(rest, last_top)
            if not follows(found[0], number):
                if opened is not None:
                    found = None  # reads as a clause opening and is not the next clause: which clause this is, is unknown
            elif opened is not None and not _abbreviation_before(paragraph, sentence.start()):
                found, last_top = opened, int(opened[0].split(".", 1)[0])
            elif not number.startswith(found[0] + "."):
                found = None  # the next number, untitled or after an abbreviation: the clause found has ended, maybe
        offset += len(paragraph) + len(PARAGRAPH_SEPARATOR)
    return f"§{found[0]} {found[1]}" if found else None


# What a period that ends an abbreviation looks like: one capitalised word of up to three letters ("No.", "Sec.", "Co.")
# or a dotted initialism ("U.S."). A number after it ("No. 3") is a reference, not an opening.
ABBREVIATION = re.compile(r"(?:^|\s)(?:[A-Z][a-z]{0,2}|(?:[A-Za-z]\.){1,}[A-Za-z])[.]$")


def _abbreviation_before(paragraph: str, at: int) -> bool:
    return ABBREVIATION.search(paragraph[:at]) is not None


@dataclass
class Block:
    kind: str  # "heading" | "text"
    text: str
    level: int = 0  # heading level, 1-based; 0 for text
    # Whether the format numbers this heading without the number being in its text, so a number may be computed from
    # levels. Plain text and PDF show every number they have; their headings say False. A DOCX heading says False from
    # reader v14 and carries the number Word prints for it instead (`word_number`), or none.
    implicit_number: bool = True
    # The clause number Word prints for this heading from its list (reader v14, readers._Numbering), when the reader
    # could work it out exactly; None when Word prints none or the reader cannot say which.
    word_number: str | None = None
    # The page the block was printed on, counted from 0, in a format that has pages (PDF); None in one that does not.
    page: int | None = None


@dataclass
class ParsedSection:
    number: str
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    number_computed: bool = False

    @property
    def text(self) -> str:
        return PARAGRAPH_SEPARATOR.join(p for p in self.paragraphs if p)


def split_heading(text: str) -> tuple[str, str]:
    """('12.4', 'Termination for Convenience') from '12.4 Termination for Convenience'."""
    match = HEADING_NUMBER.match(text)
    if match:
        return match.group(1), match.group(2).strip()
    return "", text.strip()


MIN_BODY_CHARS = 20  # a remainder shorter than this is part of the heading, not a clause body


def split_lead_in(text: str) -> tuple[str, str]:
    """('Access and Use', 'During the Subscription Period …') when a heading carries its body;
    ('Agreement', '"Agreement" means …') for a definition; a sentence that is a clause in its own
    right keeps all its text as body under a short label, so every word of it stays quotable."""
    term = DEFINED_TERM.match(text)
    if term:
        return term.group(1).strip(), text
    match = _lead_in(text)
    if match:
        lead = match[0].rstrip(".:").strip()
        # A title is short. "The following sections will survive expiration or termination of the
        # Agreement:" is the first sentence of the clause, and every word of it must stay quotable.
        short = len(lead) <= MAX_LEAD_IN_CHARS and len(lead.split()) <= MAX_LEAD_IN_WORDS
        # A line that wraps a clause ("Payment of Principal and Interest. The Borrower shall") carries little body on
        # it, the rest being on the lines below: its title is still its title, not the clause's (reader v14).
        wrapped = looks_like_sentence(text) and not _CLAUSE_VERB.search(lead)
        if short and (len(text) - match[1] >= MIN_BODY_CHARS or wrapped):
            return lead, text[match[1] :].strip()
    if len(text) <= MAX_HEADING_CHARS and not looks_like_sentence(text):
        return text.rstrip(".").strip(), ""
    # A sentence, or a long paragraph with no early break: a short label; all of it is body.
    words = text.split()
    return " ".join(words[:8]) + "…", text


def looks_like_sentence(text: str) -> bool:
    """Several words ending in a stop, or a sentence end inside the line (reader v14): a numbered paragraph that is a
    clause, not a title. A PDF line that wraps a clause ("11.2 This Lease may be amended only by a written amendment
    signed by both parties. If an") was a heading until v14, so its label stopped mid-sentence and its first sentence
    sat in no section text; so was a clause's first line that states an obligation or a permission ("8.1 Seller shall
    indemnify Buyer against Losses arising from (a) any breach of Seller's"): a title does not say "shall"."""
    words = text.split()
    if shouting(text) and capitals_sentence(text):
        return True  # reader v16: a line in capitals has no case for the tests below to read, so its words decide first
    if len(words) < SENTENCE_MIN_WORDS or title_cased(text):
        return False  # "Conduct of Business Prior to the Closing." is a title, its full stop aside
    if text.rstrip().endswith((".", ";", ":")) or _CLAUSE_VERB.search(text):
        return True
    # A long line whose words mostly open in lower case is a wrapped clause, not a title ("4.2 Any Monthly Rent not paid
    # within ten (10) days after its due date bears a late charge"): its operative words sat in the title, which is not
    # quotable section text (retrieval study, 2026-10-14: 6 PDF cases).
    if len(words) >= _LONG_LINE_WORDS and sum(1 for word in words if word[:1].islower()) * 2 > len(words):
        return True
    return any(match.group(1).casefold() not in _NOT_SENTENCE_ENDS for match in _INNER_SENTENCE_END.finditer(text))


_LONG_LINE_WORDS = 10


def title_cased(text: str) -> bool:
    """Every word opens with a capital, a digit or a bracket, except the small words a title keeps in lower case: "Purchase
    Price Adjustment.", "Conduct of Business Prior to the Closing." A single full stop may end it; none may sit inside."""
    words = text.strip().rstrip(".").split()
    if not words or len(words) > 12 or "." in text.strip().rstrip(".").replace("No.", "No"):
        return False
    return all(word[:1].isupper() or word[:1].isdigit() or word[:1] in "(&§-–" or word.casefold() in TITLE_SMALL_WORDS for word in words)


# What a clause says and a title does not (reader v14): its operative verb, in lower case ("May 2026 Amendment" is a title).
_CLAUSE_VERB = re.compile(r"\b(?:shall|must|may|will)\b")


# Reader v16: a line in capitals carries no case, so every test above that tells a sentence from a title by case passed
# it: "SECTION 9 OF THIS AGREEMENT, IN NO EVENT SHALL eGAIN BE LIABLE TO CUSTOMER FOR" was §9 and the exclusion of
# consequential damages after it sat in headings only, where no quote is searched (stress test, 2026-10-30: CUAD's eGain
# hosting agreement; 96 of 5,229 EDGAR texts held operative capitals lines only in headings). Such a line is judged on
# its words: it is a sentence, or a piece of one, when it states an operative word or a form of "to be", ends in a comma or a semicolon, or
# opens with a function word no title opens with. A line that ends in a function word is a title that wraps ("ARTICLE IV
# REPRESENTATIONS AND" / "WARRANTIES"), joined to its next line by readers._blocks_from_lines, or a sentence's first
# line, which the line after it shows.
_OPERATIVE = re.compile(r"\b(?:shall|must|will|may(?!\s+\d)|hereby|in\s+no\s+event|is|are|be|been|was|were)\b")
_ENDING_WORDS = frozenset(
    {"of", "to", "for", "the", "a", "an", "and", "or", "in", "at", "as", "by", "with", "any", "such", "that", "than", "whether", "including", "from", "on"}
    | {"upon", "under", "into", "between", "among", "against", "nor", "but"}
)
_OPENING_WORDS = frozenset({"of", "to", "for", "and", "or", "by", "with", "any", "such", "that", "than", "whether", "including", "from", "upon", "nor", "but"})
_WORD = re.compile(r"[a-z]+(?:[-'’][a-z]+)*")


def shouting(text: str) -> bool:
    """Whether a line is set in capitals: four letters or more, at most one in ten in lower case ("eGAIN" in a
    capitals clause is a name, not case evidence)."""
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and sum(1 for c in letters if c.islower()) * 10 <= len(letters)


def capitals_sentence(text: str) -> bool:
    """Whether a line in capitals reads as a sentence or a piece of one, judged on its words (reader v16)."""
    folded = text.casefold()
    words = _WORD.findall(folded)
    if not words:
        return False
    stripped = text.rstrip()
    return bool(_OPERATIVE.search(folded)) or stripped.endswith((",", ";")) or words[0] in _OPENING_WORDS


def states(text: str) -> bool:
    """Whether a line states an operative word or a form of "to be", in any case ("SHALL", "IN NO EVENT", "IS")."""
    return bool(_OPERATIVE.search(text.casefold()))


def goes_on(text: str) -> bool:
    """Whether a line stops where its sentence or title cannot end: on a comma or a semicolon ("2. SALE AND PURCHASE;
    CLOSING;" goes on to its next line's title), or on a function word ("REPRESENTATIONS AND", "in accordance with", "by
    and between")."""
    stripped = text.rstrip()
    words = _WORD.findall(stripped.casefold())
    return stripped.endswith((",", ";")) or (bool(words) and words[-1] in _ENDING_WORDS and stripped[-1:].isalpha())


# A line that ends a passage: a stop, then any closing quote or bracket (reader v16, readers._blocks_from_lines).
PASSAGE_ENDS = re.compile(r"[.;:!?][\"'”’)\]]*$")


# A sentence end inside a line: a word of three or more lower-case letters, a full stop, a space and a capitalised
# word ("parties. If"). Not after an abbreviation a heading carries ("Acme Corp. Master Agreement").
_INNER_SENTENCE_END = re.compile(r"\b([A-Za-z]*[a-z]{3})\.\s+(?=[A-Z][a-z])")
_NOT_SENTENCE_ENDS = frozenset({"corp", "inc", "ltd", "llc", "bros", "dept", "govt", "assn", "intl", "mfg", "etc", "approx", "incl"})


# The lead-in title of a heading that carries its body: "Governing Law." in "Governing Law. This Agreement …". A full
# stop that ends an abbreviation is not a title's end (reader v14): a reference word before a number ("AMENDMENT NO. 1
# TO EQUIPMENT LEASE AGREEMENT" was cut to the title "AMENDMENT NO" with "1 TO …" as its body, and the model's citation
# of that section was shown as "found in AMENDMENT NO.", the legal pilot's H1-Q1), or a name's abbreviation ("Acme Corp.
# Master Services Agreement" was the title "Acme Corp").
_LEAD_IN_END = re.compile(r"[.:](?=\s+\S)")
_REFERENCE_WORD_BEFORE = re.compile(r"(?:^|\s)(no|nos|sec|secs|art|arts|para|paras|sch|sched|ex|exh|vol|pt|pts|ch|cl|ref|fig|app|appx|rev|ver)$", re.IGNORECASE)
_NAME_ABBREVIATION_BEFORE = re.compile(r"(?:^|\s)(corp|inc|ltd|llc|co|bros|dept|govt|assn|intl|mfg|plc|pty|st)$", re.IGNORECASE)


def _lead_in(text: str) -> tuple[str, int] | None:
    """The first lead-in title of ``text``, three to eighty characters on its first line ending in a full stop or a
    colon before more text: the title with its stop, and where the body starts. A full stop that ends a reference word
    before a number ("NO. 1", "Sec. 5") or a name's abbreviation ("Corp.", "Inc.") is passed over (reader v14)."""
    for end in _LEAD_IN_END.finditer(text):
        title_end = end.end()
        if "\n" in text[:title_end] or title_end > 81:
            return None
        if title_end < 4:
            continue
        rest = text[title_end:].lstrip()
        if end.group(0) == "." and (
            (_REFERENCE_WORD_BEFORE.search(text, 0, end.start()) and rest[:1].isdigit()) or _NAME_ABBREVIATION_BEFORE.search(text, 0, end.start())
        ):
            continue
        return text[:title_end], len(text) - len(rest)
    return None


_DIGITS = re.compile(r"\d{1,9}")  # a page number; nine digits keeps int() from refusing a hostile heading
_NOT_LETTERS = re.compile(r"[^a-z ]+")
# A running line names the page or the document, never a part of it: "EXHIBIT B-1", "B-2", "B-3" are headings.
_STRUCTURAL = frozenset({"exhibit", "schedule", "annex", "appendix", "article", "section", "part", "attachment", "chapter", "clause"})
MIN_RUNNING_PAGES = 3


def _words(text: str) -> str:
    return " ".join(_NOT_LETTERS.sub(" ", text.casefold()).split())


def running_lines(blocks: Sequence[Block], title: str = "") -> set[int]:
    """The indexes of heading blocks that are a page's running header or footer, read two ways: by its page number in
    any format (below), and, in a format that has pages, by being printed on most of them (`page_furniture`).

    By page number ("1 – LEASE AGREEMENT" at the foot of every page; holdout audit, 2026-10-09): a heading whose words,
    its page number aside, are "Page" or a heading the document also prints unnumbered, at least MIN_RUNNING_PAGES times
    in a row with that number rising. A run that restarts (an exhibit numbered from 1 again) counts on its own. Measured
    over 510 CUAD and 800 EDGAR texts and the audit's lease: 87 of 54,901 heading lines in 7 documents, each a page
    footer or a contents line with its page number."""
    headings = [(i, b.text.strip()) for i, b in enumerate(blocks) if b.kind == "heading" and b.text.strip()]
    plain = {_words(text) for _, text in headings if not _DIGITS.search(text)} | {_words(title)}
    by_words: dict[str, list[tuple[int, int]]] = {}
    for index, text in headings:
        number = _DIGITS.search(text)
        words = _words(text)
        if number and words and (words in ("page", "page of") or (words in plain and words.split()[0] not in _STRUCTURAL)):
            by_words.setdefault(words, []).append((index, int(number.group(0))))
    running: set[int] = set()
    for occurrences in by_words.values():
        run = occurrences[:1]
        for previous, current in pairwise(occurrences):
            if current[1] > previous[1]:
                run.append(current)
                continue
            if len(run) >= MIN_RUNNING_PAGES:
                running.update(index for index, _ in run)
            run = [current]
        if len(run) >= MIN_RUNNING_PAGES:
            running.update(index for index, _ in run)
    return running | page_furniture(blocks)


def _line(text: str) -> str:
    return " ".join(text.casefold().split())


def page_furniture(blocks: Sequence[Block]) -> set[int]:
    """The indexes of heading blocks that are page furniture: a line printed the same, digits included, on at least
    MIN_RUNNING_PAGES pages and on most of the pages that carry text. "ACME SERVICES AGREEMENT" at the top of every page,
    "CONFIDENTIAL" or "DRAFT" stamped on each, a company name, a document number ("US-DOCS\\123456789.3") at the foot: the
    line belongs to the page, not to the clause a page break falls in, and as a heading it cut §7 from its exception
    (war room F-04, 2026-10-13). A line with a page number in it differs page to page and is read by `running_lines`.

    Not furniture: a line that opens with a clause number (the document's numbering), a structural line ("EXHIBIT B" on
    each page of the exhibit names a part, as `running_lines` holds), a line on fewer pages, and the line's first
    printing when the document opens with it, on its first page before any other heading: that is the document's own
    heading, printed once at its head and then repeated as the header ("HOSTING AGREEMENT" in CUAD's eGain agreement).
    Only a format that says where each page begins has any: blocks without a page are left alone."""
    printed_on: dict[str, set[int]] = {}
    for block in blocks:
        if block.page is not None and block.text.strip() and len(block.text) <= MAX_HEADING_CHARS:
            printed_on.setdefault(_line(block.text), set()).add(block.page)
    pages = {block.page for block in blocks if block.page is not None and block.text.strip()}
    if len(pages) < MIN_RUNNING_PAGES:
        return set()

    def furniture(line: str) -> bool:
        on = printed_on.get(line, set())
        first_word = _words(line).split()[:1]
        return len(on) >= MIN_RUNNING_PAGES and 2 * len(on) > len(pages) and not HEADING_NUMBER.match(line) and not set(first_word) & _STRUCTURAL

    first_page = min(pages)
    found: set[int] = set()
    opening = True  # before the first heading that is not furniture
    kept: set[str] = set()  # the lines kept there as the document's own headings, once each
    for index, block in enumerate(blocks):
        if block.kind != "heading" or block.page is None or not block.text.strip():
            continue
        line = _line(block.text)
        if not furniture(line):
            opening = False
        elif opening and block.page == first_page and line not in kept:
            kept.add(line)
        else:
            found.add(index)
    return found


# How many lines at each edge of a page are read for a running header or footer: one or two in every PDF measured.
EDGE_LINES = 2
_NUMBER_RUN = re.compile(r"\d{1,9}")


@dataclass(frozen=True)
class EdgeFurniture:
    """The indexes of the lines a PDF's reading leaves out as page furniture, by edge (reader v15)."""

    headers: frozenset[int]
    footers: frozenset[int]


def page_edge_furniture(lines: Sequence[str], pages: Sequence[int]) -> EdgeFurniture:
    """The lines that are a page's running header (at its top) or footer (at its foot), for a format that has pages:
    among the first or last EDGE_LINES lines with text on a page, a line printed the same on at least MIN_RUNNING_PAGES
    pages and on most of the pages that carry text, or printed the same but for a number that rises page by page ("Page
    3 of 12", "- 3 -"). Since reader v15 these are left out of the sections and counted in the coverage, as a Word
    file's headers and footers are (blind contract stress test, 2026-10-16: "SYNTHETIC LEGAL BENCHMARK / LARKSPUR-2026"
    at the top of each page sat inside §3, §11 and §13 and broke the sentence a page break fell in).

    Kept: a line that opens with a clause number, a structural line ("EXHIBIT B" on each page of the exhibit), a line on
    fewer pages, a line in the body of the page, and the lines at the top of the first page before any other line, which
    are the document's own heading printed at its head (CUAD's eGain agreement, `page_furniture`)."""
    by_page: dict[int, list[int]] = {}
    for index, (line, page) in enumerate(zip(lines, pages, strict=True)):
        if line.strip():
            by_page.setdefault(page, []).append(index)
    if len(by_page) < MIN_RUNNING_PAGES:
        return EdgeFurniture(frozenset(), frozenset())

    def same(line: str) -> str:
        return " ".join(line.casefold().split())

    def numbered(line: str) -> str:
        return _NUMBER_RUN.sub("#", same(line))

    def found(edge: dict[int, list[int]]) -> set[int]:
        exact: dict[str, list[int]] = {}
        rising: dict[str, list[tuple[int, int, int]]] = {}  # shape -> (page, number, index)
        for page, indexes in edge.items():
            for index in indexes:
                line = lines[index]
                if HEADING_NUMBER.match(line) or set(_words(line).split()[:1]) & _STRUCTURAL:
                    continue
                exact.setdefault(same(line), []).append(index)
                if number := _NUMBER_RUN.search(line):
                    rising.setdefault(numbered(line), []).append((page, int(number.group(0)), index))

        def most(count: int) -> bool:
            return count >= MIN_RUNNING_PAGES and 2 * count > len(by_page)

        out = {index for indexes in exact.values() if most(len({pages[i] for i in indexes})) for index in indexes}
        for printings in rising.values():
            ordered = sorted(printings)
            if most(len({page for page, _, _ in ordered})) and all(b[1] > a[1] for a, b in pairwise(ordered)):
                out |= {index for _, _, index in ordered}
        return out

    tops = found({page: indexes[:EDGE_LINES] for page, indexes in by_page.items()})
    foots = found({page: indexes[-EDGE_LINES:] for page, indexes in by_page.items()}) - tops
    # The document's own heading, printed at the head of its first page before anything else, stays.
    for index in by_page[min(by_page)]:
        if index not in tops:
            break
        tops.discard(index)
    return EdgeFurniture(frozenset(tops), frozenset(foots))


def build_sections(blocks: list[Block], title: str = "") -> list[ParsedSection]:
    # A running header or footer is never a heading. In a text with no pages it stays text where it stands; a PDF's page
    # furniture is left out before this, and counted as left out (readers.read_pdf, reader v15).
    running = running_lines(blocks, title)
    blocks = [Block("text", b.text) if i in running else b for i, b in enumerate(blocks)]
    sections: list[ParsedSection] = []
    counters: list[int] = []
    parent_headings: dict[int, str] = {}
    parent_numbers: dict[int, str] = {}
    current = ParsedSection(number="", heading=title)
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        if block.kind == "heading":
            if current.paragraphs or current.heading or sections:
                _push(sections, current)
            number, rest = split_heading(text)
            heading, body = split_lead_in(rest)
            computed = False
            level = max(1, block.level or 1)
            if number:
                counters = [int(p) for p in number.split(".") if p.isdigit()]
            elif block.word_number:
                number = block.word_number  # what Word prints, not a count of headings (reader v14)
            elif not block.implicit_number:
                pass  # labelled by its heading alone; the numbering of the headings around it is untouched
            else:
                counters = counters[:level]
                while len(counters) < level:
                    counters.append(0)
                counters[level - 1] += 1
                number = ".".join(str(c) for c in counters)
                computed = True
            if heading.endswith("…") and level > 1 and parent_headings.get(level - 1) and _within(parent_numbers.get(level - 1, ""), number):
                # A list item styled as a heading ("if the other party fails to cure…"): label it by its parent.
                heading = parent_headings[level - 1]
            parent_headings[level] = heading
            parent_numbers[level] = number
            current = ParsedSection(number=number, heading=heading, number_computed=computed)
            if body:
                current.paragraphs.append(body)
        else:
            current.paragraphs.append(text)
    _push(sections, current)
    return [s for s in sections if s.paragraphs or s.heading]


def _within(parent: str, number: str) -> bool:
    """Whether a section numbered ``parent`` holds one numbered ``number``, so that its title may label it (reader v14).
    Both carry a number, and a dotted one sits in its parent's: "1.4" in "1", never in an unnumbered "SITE DEVELOPMENT
    AND HOSTING AGREEMENT" that happens to be the last heading a level up, whose title it took. A list label without a
    dot ("(a)") sits in the numbered heading above it. An unnumbered line keeps its own words: a signature block
    ("E.PIPHANY, INC. HIGH SPEED NET SOLUTIONS, INC.") took the title "7" of the clause above it."""
    if not parent or not number:
        return False
    return "." not in number or number.startswith((parent + ".", parent + "("))  # "5.3(a)" sits in "5.3"


def _push(sections: list[ParsedSection], section: ParsedSection) -> None:
    if not section.paragraphs and not section.heading:
        return
    if len(section.text) <= MAX_SECTION_CHARS:
        sections.append(section)
        return
    # Split an oversized section at paragraph boundaries, keeping the heading on each part. A paragraph longer than
    # a section is cut at sentence ends into parts of its own, so no part exceeds the cap (hostile review, 2026-10-01).
    part: list[str] = []
    size = 0
    index = 1
    for paragraph in section.paragraphs:
        if len(paragraph) > MAX_SECTION_CHARS:
            if part:
                sections.append(ParsedSection(section.number, part_heading(section.heading, index), part, section.number_computed))
                index += 1
                part, size = [], 0
            for chunk in split_paragraph(paragraph, MAX_SECTION_CHARS):
                sections.append(ParsedSection(section.number, part_heading(section.heading, index), [chunk], section.number_computed))
                index += 1
            continue
        if part and size + len(paragraph) > MAX_SECTION_CHARS:
            sections.append(ParsedSection(section.number, part_heading(section.heading, index), part, section.number_computed))
            index += 1
            part, size = [], 0
        part.append(paragraph)
        size += len(paragraph) + len(PARAGRAPH_SEPARATOR)
    if part:
        sections.append(ParsedSection(section.number, part_heading(section.heading, index) if index > 1 else section.heading, part, section.number_computed))


def split_paragraph(text: str, cap: int) -> list[str]:
    """A paragraph cut into pieces of about ``cap`` characters, each cut at a place every reader of the text reads as a
    passage end (`_cut`). A piece may run past the cap to reach one; a paragraph with no such place left stays whole.

    Until reader v16 the cut fell at the cap itself when no sentence end was in the window, inside a word or a number:
    a credit agreement's part ended "the greater of $350," and the next began "000,000 and 7.5%", and a quote of "the
    greater of $350" was verified, since the end of a part is the end of the text the verifier searches (stress test,
    2026-10-30). The invariant: a part's edge is never inside a word, inside a number as it is written
    (verify.tokens.written_numbers), or inside a sentence when a sentence end is within reach."""
    pieces: list[str] = []
    start = 0
    with verification_pass():  # the paragraph's numbers are read once for all its cuts
        while len(text) - start > cap:
            cut = _cut(text, start, cap)
            if cut is None:
                break
            piece = text[start:cut].strip()
            if piece:
                pieces.append(piece)
            start = cut
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return pieces


# A passage end: a stop that ends a sentence or an item of a list, any closing quote or bracket after it, and the space
# after that; the CJK stops need no space (reader v16; "。" was no end before, so a Chinese paragraph was cut at the cap).
PASSAGE_END = re.compile(r"[.!?;][\"'”’)\]]*\s+|[。！？；][」』”’）)\]]*\s*")
_SPACE = re.compile(r"\s+")


def _cut(text: str, start: int, cap: int) -> int | None:
    """Where the piece of ``text`` from ``start`` ends: the last passage end within the cap that splits nothing (not a
    sliver, so not before a quarter of it); else the first one past the cap, within half a cap more; else the last space
    within the cap that splits nothing (a number written with a sign keeps its spaces: "-Rs. 5M"), else the first past
    it; else None, and the rest stays whole. "Splits nothing" is the verifier's own test of an edge (spans.bounded)."""
    low, high = start + cap // 4, start + cap

    def fits(at: int) -> bool:
        return start < at < len(text) and bounded(text, at, at)

    ends = [m.end() for m in PASSAGE_END.finditer(text, low, high + cap // 2)]
    found = next((at for at in reversed(ends) if at <= high and fits(at)), None)
    if found is None:
        found = next((at for at in ends if at > high and fits(at)), None)
    if found is None:
        spaces = [m.end() for m in _SPACE.finditer(text, low, high)]
        found = next((at for at in reversed(spaces) if fits(at)), None)
    if found is None:
        found = next((m.end() for m in _SPACE.finditer(text, high) if fits(m.end())), None)
    return found


# "Schedule A. Service Level and Credits", "Annex 2 – Fees", "Appendix B: Data Processing Terms": a part of the agreement
# named by its kind, its mark and, after a full stop, a colon or a dash, its title (reader v15). A Word file styles such a
# line a heading; in a PDF it was body text, so a schedule was read into the clause before it and its passages were cited
# as that clause's ("§13.3 No Penalty for Non-Renewal" for Schedule A's credit table; blind contract stress test,
# 2026-10-16). Not a heading: the mark alone ("Exhibit 10.1" is printed at the top of every page of many EDGAR texts,
# and as a heading it split their clauses at each page break: 174 of 5,984 corpus texts in the first v15 replay), a mark
# followed by a space and words (a contents line, "Schedule 1 The Mandated Lead Arrangers and the Lenders"), a mark the
# title runs into ("Schedule 2.5Fees"), and a title that ends in a page number.
ATTACHMENT_HEADING = re.compile(
    r"^(?:Schedule|Exhibit|Appendix|Annexure|Annex|Attachment|Addendum)\s+(?:[A-Z]{1,2}|\d{1,3}(?:\.\d{1,3})*)(?:[.:]|\s+[–—-])\s+(?P<title>\S.*)$"
)
_ENDS_IN_A_PAGE = re.compile(r"(?:\d|\.{3,}\s*\d*)$")


def looks_like_heading(line: str) -> bool:
    """For plain text and PDF: a short numbered line, a line naming a part of the agreement, or a short all-caps line."""
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if attachment := ATTACHMENT_HEADING.match(stripped):
        # Its title is a title: "Schedule A. This schedule sets out the fees" is a sentence, "Exhibit A. (Form of
        # Assignment), Exhibit B …" a list of references, "Schedule A. Fees ........ 14" a contents line.
        title = attachment.group("title").strip()
        return not title.startswith("(") and not _ENDS_IN_A_PAGE.search(title) and title_cased(title)
    match = HEADING_NUMBER.match(stripped)
    # A title may end in a full stop ("Section 2.7 Purchase Price Adjustment."): until reader v14 such a line was body,
    # and a whole Article became one unnumbered section (retrieval study, 2026-10-14: 33 of 51 headings of an EDGAR-shaped
    # purchase agreement). A title-cased line is a title, full stop or not; a sentence is not title-cased.
    if match and (not stripped.endswith((".", ";", ",", ":")) or (stripped.endswith(".") and title_cased(match.group(2)))):
        title = match.group(2)
        # A heading's title opens with a capital; a numbered line whose words open in lower case is a wrapped sentence
        # ("Section 19 of the Facility Lease, or modify …"), a figure ("3.50 to 1.00", "15 years") or a list item
        # inside a clause ("3.1.14 make available for …"). Measured 2026-10-08: 460 of 11,646 numbered heading lines in
        # the CUAD texts and 300 EDGAR filings; none of 60 sampled was a clause title.
        if title[:1].islower():
            return False
        # The same in capitals, which have no case (reader v16): "SECTION 19 OF THE FACILITY LEASE, OR MODIFY" is the
        # capitals twin of the lower-case line above, a wrapped sentence opening with a function word.
        words = _WORD.findall(title.casefold())
        if shouting(title) and words and words[0] in _OPENING_WORDS:
            return False
        # Cross-references read like headings and are not: "5.5 (Effect of Termination), Section 5.6 (Survival)".
        return not (title.startswith("(") or re.search(r"\b(?:Section|Clause|Article)s?\s+\d", title, re.IGNORECASE))
    letters = [c for c in stripped if c.isalpha()]
    if not (len(letters) >= 4 and all(c.isupper() for c in letters) and len(stripped.split()) <= 10):
        return False
    if match:
        # A numbered capitals line that stops on a comma or a semicolon is a clause opening ("5.21 WAIVER OF JURY TRIAL.
        # IN ANY ACTION, SUIT,", "2. SALE AND PURCHASE; CLOSING;"): a heading, its words kept as body by split_lead_in,
        # unless its title opens with a function word (reader v16).
        words = _WORD.findall(match.group(2).casefold())
        return not (words and words[0] in _OPENING_WORDS)
    # A capitals line is a heading when it is short and reads as a title, not as a sentence (reader v16).
    return not capitals_sentence(stripped)
