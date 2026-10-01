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


@dataclass
class Block:
    kind: str  # "heading" | "text"
    text: str
    level: int = 0  # heading level, 1-based; 0 for text


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
                sections.append(ParsedSection(section.number, f"{section.heading} (part {index})", part, section.number_computed))
                index += 1
                part, size = [], 0
            for chunk in split_paragraph(paragraph, MAX_SECTION_CHARS):
                sections.append(ParsedSection(section.number, f"{section.heading} (part {index})", [chunk], section.number_computed))
                index += 1
            continue
        if part and size + len(paragraph) > MAX_SECTION_CHARS:
            sections.append(ParsedSection(section.number, f"{section.heading} (part {index})", part, section.number_computed))
            index += 1
            part, size = [], 0
        part.append(paragraph)
        size += len(paragraph) + len(PARAGRAPH_SEPARATOR)
    if part:
        sections.append(ParsedSection(section.number, f"{section.heading} (part {index})" if index > 1 else section.heading, part, section.number_computed))


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
        # Cross-references read like headings and are not: "5.5 (Effect of Termination), Section 5.6 (Survival)".
        return not (title.startswith("(") or re.search(r"\b(?:Section|Clause|Article)s?\s+\d", title, re.IGNORECASE))
    letters = [c for c in stripped if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters) and len(stripped.split()) <= 10
