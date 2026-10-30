"""What Word displays where a DOCX's text is not a plain walk of its w:t elements (reader v16).

The DOCX reader's claim is that its text is the text Word displays with every change accepted. Four kinds of markup
broke it, each found by the adversarial stress test (2026-10-30) with Word 16 as the oracle, and each read here once:

- Markup compatibility (ECMA-376 Part 3). An mc:AlternateContent holds one rendering per branch, and Word displays one:
  the first mc:Choice whose Requires names only namespaces it understands, else the mc:Fallback. The walk read both,
  so "ninety (90)" and "thirty (30)" stood side by side. An element of an mc:Ignorable namespace Word does not
  understand is dropped with its content (or, listed in mc:ProcessContent, replaced by its content); the walk read it.
- Fields. A field is begin, instruction, separate, result, end, spread over sibling runs and often over paragraphs;
  Word displays the result. Text inside an instruction (a nested field's result written as w:t by a tool other than
  Word) is not displayed, and the walk read it: "thirty (30) days ninety (90) days" where Word shows "ninety (90) days".
  A legacy check box or drop-down has no result text at all: Word draws the box, or the chosen entry, from its
  w:ffData, and the walk read a ticked IDTA exactly as the blank form.
- Symbols. w:sym, and text in a symbol font, display a glyph of that font: Wingdings 0xFE is a ticked box, Symbol 0xB3 is
  "≥". The walk dropped every w:sym, so "a tolerance of ±0.25" read "a tolerance of 0.25".
- Data binding. A content control bound to a part of the package (a custom XML item, the document's properties)
  displays the bound value, refreshed when Word opens the file; its cached content may be stale when another tool
  wrote the part, and the walk read the cache.

Nothing here reads a file: the reader hands over the elements and the package's parts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def _w(local: str) -> str:
    return f"{{{W}}}{local}"


ALTERNATE = f"{{{MC}}}AlternateContent"
CHOICE = f"{{{MC}}}Choice"
FALLBACK = f"{{{MC}}}Fallback"
_IGNORABLE = f"{{{MC}}}Ignorable"
_PROCESS_CONTENT = f"{{{MC}}}ProcessContent"

# The namespaces Word 16 understands, for an mc:Choice's Requires and for mc:Ignorable: WordprocessingML and its
# extensions (w14 to w16*), DrawingML and VML, math, and the Office 2010+ drawing namespaces a text box or a shape
# requires. A namespace not listed is one Word may still know (a chart's cx*): its Choice then gives way to the
# Fallback, which for text is the same text drawn the old way.
WORD_NAMESPACES = frozenset(
    {
        W,
        MC,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "http://schemas.openxmlformats.org/officeDocument/2006/math",
        "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
        "http://schemas.openxmlformats.org/drawingml/2006/main",
        "http://schemas.openxmlformats.org/drawingml/2006/picture",
        "urn:schemas-microsoft-com:vml",
        "urn:schemas-microsoft-com:office:office",
        "urn:schemas-microsoft-com:office:word",
        "urn:schemas-microsoft-com:mac:vml",
        "http://schemas.microsoft.com/office/mac/office/2008/main",
        "http://schemas.microsoft.com/office/word/2006/wordml",
        "http://schemas.microsoft.com/office/word/2010/wordml",
        "http://schemas.microsoft.com/office/word/2012/wordml",
        "http://schemas.microsoft.com/office/word/2015/wordml/symex",
        "http://schemas.microsoft.com/office/word/2016/wordml/cid",
        "http://schemas.microsoft.com/office/word/2018/wordml",
        "http://schemas.microsoft.com/office/word/2018/wordml/cex",
        "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
        "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
        "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock",
        "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
        "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
        "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
        "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
        "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
        "http://schemas.microsoft.com/office/drawing/2010/main",
        "http://schemas.microsoft.com/office/drawing/2014/main",
    }
)


def namespace_of(tag: str) -> str:
    return tag[1 : tag.index("}")] if tag.startswith("{") else ""


class Compatibility:
    """Markup compatibility as Word applies it to a part: which branch of an mc:AlternateContent is displayed, and
    which elements of an ignorable namespace are dropped or unwrapped. Read from the part's root once."""

    def __init__(self, root: etree._Element) -> None:
        self.ignorable = {root.nsmap.get(prefix) for prefix in (root.get(_IGNORABLE) or "").split()} - {None} - WORD_NAMESPACES
        self.unwrapped: set[str] = set()
        for name in (root.get(_PROCESS_CONTENT) or "").split():
            prefix, _, local = name.partition(":")
            uri = root.nsmap.get(prefix)
            if uri and local:
                self.unwrapped.add(f"{{{uri}}}{local}")

    def branch(self, alternate: etree._Element) -> etree._Element | None:
        """The branch Word displays: the first Choice whose Requires prefixes all name namespaces it understands, else the
        Fallback; None when neither applies."""
        for choice in alternate.iterchildren(CHOICE):
            required = (choice.get("Requires") or "").split()
            if required and all(choice.nsmap.get(prefix) in WORD_NAMESPACES for prefix in required):
                return choice
        return next(alternate.iterchildren(FALLBACK), None)

    def dropped(self, tag: str) -> bool:
        """An element Word leaves out with its content: one of an ignorable namespace it does not understand."""
        return tag not in self.unwrapped and namespace_of(tag) in self.ignorable

    def children(self, element: etree._Element) -> list[etree._Element]:
        """The element's children as Word renders them: each mc:AlternateContent replaced by its chosen branch's
        children, each ignorable element left out or, under mc:ProcessContent, replaced by its children; comments and
        processing instructions left out."""
        out: list[etree._Element] = []
        for child in element:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            if tag == ALTERNATE:
                chosen = self.branch(child)
                if chosen is not None:
                    out.extend(self.children(chosen))
            elif tag in self.unwrapped:
                out.extend(self.children(child))
            elif not self.dropped(tag):
                out.append(child)
        return out


# --------------------------------------------------------------------------------------------------------- fields

_FIELD_CHAR_TYPE = _w("fldCharType")
_FORM_DATA = _w("ffData")
_VAL = _w("val")
CHECKED_BOX, EMPTY_BOX = "☒", "☐"  # ☒ ☐


def _on(element: etree._Element | None) -> bool | None:
    """An OnOff property: on when present without a value or with one that is not off; None when absent."""
    if element is None:
        return None
    return element.get(_VAL) not in ("0", "false", "off")


def form_display(field_char: etree._Element) -> str | None:
    """What Word draws for a legacy form field that has no result text, from its w:ffData: a check box as ☒ or ☐
    (w:checked, then w:default), a drop-down as its chosen entry (w:result, then w:default, then the first); None for
    any other field, whose result text is displayed."""
    data = field_char.find(_FORM_DATA)
    if data is None:
        return None
    box = data.find(_w("checkBox"))
    if box is not None:
        checked = _on(box.find(_w("checked")))
        if checked is None:
            default = box.find(_w("default"))
            checked = default is not None and default.get(_VAL) not in ("0", "false", "off", None)
        return CHECKED_BOX if checked else EMPTY_BOX
    entries = data.find(_w("ddList"))
    if entries is not None:
        values = [entry.get(_VAL) or "" for entry in entries.iterfind(_w("listEntry"))]
        chosen = next((e.get(_VAL) for e in (entries.find(_w("result")), entries.find(_w("default"))) if e is not None and e.get(_VAL)), "0")
        index = int(chosen) if chosen is not None and chosen.isdigit() else 0
        return values[index] if 0 <= index < len(values) else ""
    return None


@dataclass
class _Field:
    instruction: bool = True  # before its separate: what is written is the instruction, not displayed
    display: str | None = None  # what Word draws at its end (a form field with no result)


@dataclass
class Fields:
    """The fields open at this point of a story, outermost first. Text is displayed only while no open field is in its
    instruction: a field nested in another's result (a TOC's page numbers) displays its own result, one nested in an
    instruction displays nothing. ``enabled`` is off for a story whose field marks do not balance, which is read whole."""

    enabled: bool = True
    open: list[_Field] = field(default_factory=list)
    forms: int = 0  # check boxes and drop-downs drawn from their w:ffData

    @property
    def showing(self) -> bool:
        return not self.enabled or not any(f.instruction for f in self.open)

    def mark(self, field_char: etree._Element) -> str:
        """Moves the state past a w:fldChar; returns what Word draws there (a check box, a drop-down's entry) or ""."""
        if not self.enabled:
            return ""
        kind = field_char.get(_FIELD_CHAR_TYPE)
        if kind == "begin":
            self.open.append(_Field(display=form_display(field_char)))
        elif kind == "separate" and self.open:
            self.open[-1].instruction = False
        elif kind == "end" and self.open:
            ended = self.open.pop()
            if ended.display is not None and self.showing:
                self.forms += 1
                return ended.display
        return ""


def fields_balance(marks: list[tuple[str | None, bool]]) -> bool:
    """Whether a story's field marks (type, deleted) open and close in order: every end closes a begin, none is left
    open. A deleted mark is gone once the change is accepted."""
    depth = 0
    for kind, deleted in marks:
        if deleted:
            continue
        if kind == "begin":
            depth += 1
        elif kind == "end":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


# -------------------------------------------------------------------------------------------------------- symbols

REPLACEMENT = "\ufffd"

# What each symbol font draws for a character code (the code's low byte; Word writes them as F0xx in w:sym and as
# private-use or Latin-1 characters in text), for the codes whose glyph is a mark, a sign or a letter a contract uses.
# Symbol is Adobe's Symbol encoding. Wingdings and Wingdings 2 are the check boxes, ticks and crosses Word's own
# "Insert Symbol" offers for forms. A code not listed displays a glyph this reader does not know: it is read as U+FFFD
# and counted, never as the Latin letter its code happens to share.
_SYMBOL = dict(
    zip(
        range(0x20, 0x7F),
        " !∀#∃%&∋()∗+,−./0123456789:;<=>?≅ΑΒΧΔΕΦΓΗΙϑΚΛΜΝΟΠΘΡΣΤΥςΩΞΨΖ[∴]⊥_\ufffdαβχδεφγηιϕκλμνοπθρστυϖωξψζ{|}∼",
        strict=True,
    )
) | {
    0xA2: "′",
    0xA3: "≤",
    0xA4: "⁄",
    0xA5: "∞",
    0xA6: "ƒ",
    0xAB: "↔",
    0xAC: "←",
    0xAD: "↑",
    0xAE: "→",
    0xAF: "↓",
    0xB0: "°",
    0xB1: "±",
    0xB2: "″",
    0xB3: "≥",
    0xB4: "×",
    0xB5: "∝",
    0xB6: "∂",
    0xB7: "•",
    0xB8: "÷",
    0xB9: "≠",
    0xBA: "≡",
    0xBB: "≈",
    0xBC: "…",
    0xC6: "∅",
    0xC7: "∩",
    0xC8: "∪",
    0xCE: "∈",
    0xCF: "∉",
    0xD2: "®",
    0xD3: "©",
    0xD4: "™",
    0xD5: "∏",
    0xD6: "√",
    0xD7: "⋅",
    0xD8: "¬",
    0xD9: "∧",
    0xDA: "∨",
    0xDB: "⇔",
    0xDC: "⇐",
    0xDE: "⇒",
    0xE2: "®",
    0xE3: "©",
    0xE4: "™",
    0xE5: "∑",
}
_WINGDINGS = {0x6E: "■", 0x6F: "☐", 0x78: "☒", 0xA8: "☐", 0x9F: "•", 0xA7: "▪", 0xFB: "✗", 0xFC: "✓", 0xFD: "☒", 0xFE: "☑"}
_WINGDINGS_2 = {0x4F: "✗", 0x50: "✓", 0x51: "✗", 0x52: "☑", 0x53: "☒", 0x54: "☒", 0xA3: "☐"}
SYMBOL_FONTS = {"symbol": _SYMBOL, "wingdings": _WINGDINGS, "wingdings 2": _WINGDINGS_2}


def symbol_font(name: str | None) -> dict[int, str] | None:
    return SYMBOL_FONTS.get((name or "").strip().casefold())


def symbol_text(font: str | None, code: int) -> tuple[str, bool]:
    """What a w:sym displays, and whether this reader knows it: in a symbol font, the glyph its table names for the
    code's low byte (Word writes F0xx); in any other font a code outside the private-use area is itself."""
    table = symbol_font(font)
    if table is None:
        known = not (0xE000 <= code <= 0xF8FF) and code >= 0x20
        return (chr(code), True) if known else (REPLACEMENT, False)
    low = code - 0xF000 if 0xF000 <= code <= 0xF0FF else code
    shown = table.get(low)
    return (shown, True) if shown and shown != REPLACEMENT else (REPLACEMENT, False)


def in_symbol_font(text: str, table: dict[int, str]) -> tuple[str, int]:
    """Text a run sets in a symbol font, as that font displays it, and how many characters this reader does not know."""
    out: list[str] = []
    unknown = 0
    for ch in text:
        code = ord(ch)
        low = code - 0xF000 if 0xF000 <= code <= 0xF0FF else code
        shown = table.get(low) if low <= 0xFF else None
        if shown is None or shown == REPLACEMENT:
            if ch.isspace():
                out.append(ch)
                continue
            unknown += 1
            shown = REPLACEMENT
        out.append(shown)
    return "".join(out), unknown


# --------------------------------------------------------------------------------------------------- data binding

# The store item IDs Word gives the document's own property parts, which a control may be bound to without a custom
# XML part (ECMA-376 Part 1, 17.5.2.6; the cover page properties are a custom XML part of their own).
_CORE_PROPERTIES = "{6C3C8BC8-F283-45AE-878A-BAB7291924A1}"
_EXTENDED_PROPERTIES = "{6668398D-A668-4E3E-A5EB-62B293D839F1}"
_SAFE = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_comments=True)
_PREFIX_MAPPING = re.compile(r"""xmlns:([\w.-]+)\s*=\s*(["'])(.*?)\2""")
_TYPED = tuple(_w(tag) for tag in ("date", "picture", "docPartObj", "docPartList", "citation", "bibliography", "group", "equation"))


class Bindings:
    """The parts a content control may be bound to, read from the package once: each custom XML item by its store item
    ID, and the core and extended document properties."""

    def __init__(self, parts: dict[str, bytes]) -> None:
        self.stores: dict[str, etree._Element] = {}
        for name, data in parts.items():
            match = re.fullmatch(r"customXml/itemProps(\d+)\.xml", name)
            item = f"customXml/item{match.group(1)}.xml" if match else None
            if item is None or item not in parts:
                continue
            try:
                props, root = etree.fromstring(data, _SAFE), etree.fromstring(parts[item], _SAFE)
            except etree.XMLSyntaxError:
                continue
            item_id = next((str(v) for k, v in props.attrib.items() if etree.QName(k).localname == "itemID"), None)
            if item_id:
                self.stores[item_id.upper()] = root
        for store, name in ((_CORE_PROPERTIES, "docProps/core.xml"), (_EXTENDED_PROPERTIES, "docProps/app.xml")):
            if name in parts:
                try:
                    self.stores[store] = etree.fromstring(parts[name], _SAFE)
                except etree.XMLSyntaxError:
                    continue
        self.read = 0  # bound controls displayed from their bound value or a cache that agrees with it
        self.unknown = 0  # bound controls whose displayed value this reader cannot work out: left out of the text

    def shown(self, properties: etree._Element | None, cached: str) -> str | None:
        """What a content control displays when its properties bind it (w:dataBinding): None when it is not bound or its
        store item is not in the package (Word then shows the cache too); the cache when the bound value agrees; the
        bound value for plain and rich text; a drop-down list's display text for its value; U+FFFD, counted, where the
        bound value disagrees and is displayed through a format this reader does not apply (a date, a picture)."""
        binding = properties.find(_w("dataBinding")) if properties is not None else None
        if binding is None:
            return None
        store = self.stores.get((binding.get(_w("storeItemID")) or "").upper())
        if store is None:
            return None
        namespaces = {prefix: uri for prefix, _, uri in _PREFIX_MAPPING.findall(binding.get(_w("prefixMappings")) or "")}
        try:
            found = store.xpath(binding.get(_w("xpath")) or "", namespaces=namespaces)
        except (etree.XPathError, ValueError):
            self.unknown += 1
            return REPLACEMENT
        node = found[0] if isinstance(found, list) and found else found
        if isinstance(node, etree._Element):
            value = "".join(str(text) for text in node.itertext())
        elif isinstance(node, str | bytes | int | float):
            value = str(node)
        else:
            self.unknown += 1
            return REPLACEMENT
        if " ".join(value.split()) == " ".join(cached.split()):
            self.read += 1
            return None
        assert properties is not None
        listed = properties.find(_w("dropDownList"))
        if listed is None:
            listed = properties.find(_w("comboBox"))
        if listed is not None:
            for item in listed.iterfind(_w("listItem")):
                if item.get(_w("value")) == value:
                    self.read += 1
                    return item.get(_w("displayText")) or value
        if listed is None and not any(properties.find(tag) is not None for tag in _TYPED) and not _extension_typed(properties):
            self.read += 1
            return value
        self.unknown += 1
        return REPLACEMENT


def _extension_typed(properties: etree._Element) -> bool:
    """A control typed by an extension namespace (a w14 check box, a w15 repeating section): its display is its own."""
    return any(isinstance(child.tag, str) and namespace_of(child.tag) not in (W, "") for child in properties)
