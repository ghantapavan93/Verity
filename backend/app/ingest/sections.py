"""Turn a stream of blocks (headings and body text) into numbered sections.

A section starts at every heading. Text before the first heading becomes the title block.
Numbers come from the heading text when it starts with one ("12.4 Termination"); otherwise
they are computed from heading levels, which matches Word's automatic numbering when the
document numbers its headings top to bottom and is best effort otherwise.

Many templates (Common Paper among them) style the whole clause as a heading paragraph:
"Access and Use.  During the Subscription Period …". Such a paragraph is split into a short
heading and a body at its first sentence break, so the clause text is retrievable and quotable.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

# Nine digits per part: a "number" longer than that is not a clause number, and Python refuses to parse thousands of digits.
HEADING_NUMBER = re.compile(r"^\s*(?:(?:Section|Clause|Article)\s+)?(\d{1,9}(?:\.\d{1,9})*)[.)]?\s+(.*\S)\s*$", re.IGNORECASE)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
LEAD_IN = re.compile(r"^(.{3,80}?[.:])\s+(?=\S)")
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
    # Whether the format numbers this heading without the number being in its text (Word's automatic numbering), so a
    # number may be computed from levels. Plain text and PDF show every number they have; their headings say False.
    implicit_number: bool = True


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
    match = LEAD_IN.match(text)
    if match and len(text) - match.end() >= MIN_BODY_CHARS:
        lead = match.group(1).rstrip(".:").strip()
        # A title is short. "The following sections will survive expiration or termination of the
        # Agreement:" is the first sentence of the clause, and every word of it must stay quotable.
        if len(lead) <= MAX_LEAD_IN_CHARS and len(lead.split()) <= MAX_LEAD_IN_WORDS:
            return lead, text[match.end() :].strip()
    if len(text) <= MAX_HEADING_CHARS and not looks_like_sentence(text):
        return text.rstrip(".").strip(), ""
    # A sentence, or a long paragraph with no early break: a short label; all of it is body.
    words = text.split()
    return " ".join(words[:8]) + "…", text


def looks_like_sentence(text: str) -> bool:
    """Several words ending in a stop: a numbered paragraph that is a clause, not a title."""
    return len(text.split()) >= SENTENCE_MIN_WORDS and text.rstrip().endswith((".", ";", ":"))


def build_sections(blocks: list[Block], title: str = "") -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    counters: list[int] = []
    parent_headings: dict[int, str] = {}
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
            elif not block.implicit_number:
                pass  # labelled by its heading alone; the numbering of the headings around it is untouched
            else:
                counters = counters[:level]
                while len(counters) < level:
                    counters.append(0)
                counters[level - 1] += 1
                number = ".".join(str(c) for c in counters)
                computed = True
            if heading.endswith("…") and level > 1 and parent_headings.get(level - 1):
                # A list item styled as a heading ("if the other party fails to cure…"): label it by its parent.
                heading = parent_headings[level - 1]
            parent_headings[level] = heading
            current = ParsedSection(number=number, heading=heading, number_computed=computed)
            if body:
                current.paragraphs.append(body)
        else:
            current.paragraphs.append(text)
    _push(sections, current)
    return [s for s in sections if s.paragraphs or s.heading]


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
    """A paragraph cut into pieces no longer than ``cap``, at sentence ends where there are any, else at the cap."""
    pieces: list[str] = []
    start = 0
    while len(text) - start > cap:
        # The last sentence end inside the window, unless that leaves a sliver; then the cap itself.
        cut = max((m.end() for m in SENTENCE_END.finditer(text, start, start + cap)), default=start)
        if cut - start < cap // 4:
            cut = start + cap
        piece = text[start:cut].strip()
        if piece:
            pieces.append(piece)
        start = cut
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return pieces


def looks_like_heading(line: str) -> bool:
    """For plain text and PDF: a short numbered line or a short all-caps line."""
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    match = HEADING_NUMBER.match(stripped)
    if match and not stripped.endswith((".", ";", ",", ":")):
        title = match.group(2)
        # A heading's title opens with a capital; a numbered line whose words open in lower case is a wrapped sentence
        # ("Section 19 of the Facility Lease, or modify …"), a figure ("3.50 to 1.00", "15 years") or a list item
        # inside a clause ("3.1.14 make available for …"). Measured 2026-10-08: 460 of 11,646 numbered heading lines in
        # the CUAD texts and 300 EDGAR filings; none of 60 sampled was a clause title.
        if title[:1].islower():
            return False
        # Cross-references read like headings and are not: "5.5 (Effect of Termination), Section 5.6 (Survival)".
        return not (title.startswith("(") or re.search(r"\b(?:Section|Clause|Article)s?\s+\d", title, re.IGNORECASE))
    letters = [c for c in stripped if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters) and len(stripped.split()) <= 10
