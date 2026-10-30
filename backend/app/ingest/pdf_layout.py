"""A PDF page's text in the order a reader reads it, from the page's own drawing operations (reader v16).

Until v16 a page was pypdf's layout-mode string, cleaned of runs of spaces. That string is built by grouping every piece
of text that shares a baseline into one line, so a page set in two columns came out with each left-column line joined to
the right-column line beside it: "Customer may terminate this Agreement Supplier may terminate this Agreement on thirty
(30) days notice. on ninety (90) days notice." A quote of the junction ("Supplier may terminate this Agreement on thirty
(30) days notice.") verified exactly where the page says ninety days, code decided on it, and the evidence pack passed it
(adversarial stress test, 2026-10-30). Layout mode also skips form XObjects (a page drawn wholly by them was refused as
"a scan?") and rotated text, keeps a TJ array's strings in stream order where the page draws them in another ("09" for a
page that shows "90"), and reads text drawn so that it cannot be seen: render mode 3, white on nothing, a tenth of a
point, off the page.

The invariant: what the reading says a page shows is what the page displays, and what it does not read is counted. So
the page's operators are walked here, with pypdf's own text state (its layout mode's TextStateManager and
TextStateParams, which place each string where the page draws it) and these additions, each where a case needs it:

- form XObjects are entered, with their matrix and resources;
- a string is placed after the one before it (pypdf's layout mode does not advance past a Tj, nor between two strings of
  one TJ), and a line whose strings are drawn out of order is read in the order of their positions;
- text that cannot be seen is left out and counted: render mode 3 or 7, a fill of white with nothing painted beneath it,
  1 pt or smaller, wholly off the page. Invisible or white text laid over an image is read (it is a scan's OCR layer,
  the image showing the same words) and counted as such;
- rotated text is counted, not read (as before, but now said);
- in a font drawn by glyph name (not embedded), a digit, currency sign or "%" whose ToUnicode entry names another such
  character than the glyph its encoding names is read as U+FFFD and counted: which of the two the page shows cannot be
  told from the text layer. An embedded font is not checked: its encoding's names need not be its glyphs;
- side-by-side columns are found from the page's geometry: a vertical band at least nine tenths of a line high wide,
  clear of text on every line of a run of at least three lines, with text on both sides. Within such a run, a band of
  two lines or more (lines with no larger gap between them) whose columns all hold prose (four words or more a line on
  average) is read one column after the other, each column its own passage; anything else (a table's rows, a signature
  block) is read line by line, as tables were. No sentence is made across a gutter the reader found; one it did not find
  (narrower than the threshold) is read as before.

Every line is then laid out by pypdf's own fixed-width code, in the coordinates pypdf's layout mode gives it (it applies a
cm only inside q ... Q, and its spacing is tuned to that), so a page with none of these reads exactly as pypdf read it:
424 of the corpus's 427 readable pages (2026-10-30). Where text lies on the page is decided in the page's own coordinates.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from itertools import pairwise
from typing import Any, cast

from pypdf import PageObject

# pypdf 6.21 moved Font from pypdf._font into pypdf.generic; the lock pins 6.21.2, so a reader importing the old path
# failed to import at all under the lock (found by the lead running the reader tests under it, 2026-10-30). The second
# path serves an environment still on 6.19; every signature this module uses is the same in both.
try:
    from pypdf.generic._font import Font  # type: ignore[import-not-found,unused-ignore]
except ImportError:  # pragma: no cover - pypdf before 6.21
    from pypdf._font import Font  # type: ignore[no-redef,import-not-found,unused-ignore]
from pypdf._text_extraction import LAYOUT_NEW_BT_GROUP_SPACE_WIDTHS
from pypdf._text_extraction._layout_mode import fixed_char_width, fixed_width_page, y_coordinate_groups
from pypdf._text_extraction._layout_mode._fixed_width_page import BTGroup, bt_group, resolve_font
from pypdf._text_extraction._layout_mode._text_state_manager import TextStateManager
from pypdf._text_extraction._layout_mode._text_state_params import TextStateParams
from pypdf.generic import ContentStream, DictionaryObject, PdfObject

REPLACEMENT = "\ufffd"
MAX_FORM_DEPTH = 8
TINY_POINTS = 1.0  # text this high or lower is a line on the page, not words: the stress test hid "30" at 0.1 pt
MIN_GUTTER_LINES = 3
MIN_GUTTER_HEIGHTS = 0.9  # a gutter's width in line heights: CSS columns default to a 1 em gap
MIN_PROSE_WORDS = 4.0
BAND_GAP_HEIGHTS = 1.0  # a vertical gap of a line or more between lines ends a band of a column run
WORD_GAP_HEIGHTS = 0.15  # a gap between two strings this share of a line high or wider is a space
# Characters whose glyph and text layer must agree: a digit, a currency sign, a percent sign.
GUARDED = frozenset("0123456789$€£¥%")
INVISIBLE_MODES = frozenset({3, 7})
FILL_MODES = frozenset({0, 2, 4, 6})

Box = tuple[float, float, float, float]


@dataclass
class Shown:
    """One string a text-showing operator draws: where (pypdf's text state), in which BT block, and why it cannot be
    seen when it cannot ("render", "white", "tiny", "off_page")."""

    params: TextStateParams
    block: int
    hidden: str | None = None
    over_image: bool = False


@dataclass
class PageText:
    text: str
    hidden: dict[str, int] = field(default_factory=dict)  # characters left out, by why
    rotated: int = 0  # characters of rotated text, not read
    image_text: int = 0  # characters of invisible or white text over an image, read
    disagreements: int = 0  # characters whose text layer and glyph disagree, read as U+FFFD
    unreadable: int = 0  # characters in a font whose glyphs pypdf cannot map to text, not read
    columns: bool = False  # side-by-side prose read column by column
    side_by_side: bool = False  # side-by-side text of short cells read line by line
    drawn: bool = False  # any text-showing operator reached, read or not


@dataclass
class _Graphics:
    render: int = 0
    white: bool = False
    space: str = "/DeviceGray"


def _point(matrix: Sequence[float], x: float, y: float) -> tuple[float, float]:
    return matrix[0] * x + matrix[2] * y + matrix[4], matrix[1] * x + matrix[3] * y + matrix[5]


def _multiply(m: Sequence[float], n: Sequence[float]) -> list[float]:
    """The affine matrix m then n, as PDF composes a cm with the matrix in force (m x n)."""
    return [
        m[0] * n[0] + m[1] * n[2],
        m[0] * n[1] + m[1] * n[3],
        m[2] * n[0] + m[3] * n[2],
        m[2] * n[1] + m[3] * n[3],
        m[4] * n[0] + m[5] * n[2] + n[4],
        m[4] * n[1] + m[5] * n[3] + n[5],
    ]


def _bbox(points: Sequence[tuple[float, float]]) -> Box:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _inside(box: Box, x: float, y: float) -> bool:
    return box[0] - 0.5 <= x <= box[2] + 0.5 and box[1] - 0.5 <= y <= box[3] + 0.5


def _numbers(operands: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for operand in operands:
        try:
            out.append(float(operand))
        except (TypeError, ValueError):
            return []
    return out


def _white(operands: Sequence[Any], space: str) -> bool:
    """Whether a colour is white in its space: gray 1, RGB 1 1 1, CMYK 0 0 0 0. A space this reader does not resolve
    (a separation, an ICC profile named by a resource, a pattern) is taken as not white, so its text is read."""
    values = _numbers(operands)
    if not values or len(values) != len(operands):
        return False
    if len(values) == 1 and space in ("/DeviceGray", "/G"):
        return values[0] >= 0.999
    if len(values) == 3 and space in ("/DeviceRGB", "/RGB"):
        return all(v >= 0.999 for v in values)
    if len(values) == 4 and space in ("/DeviceCMYK", "/CMYK"):
        return all(v <= 0.001 for v in values)
    return False


def _dictionary(value: object) -> DictionaryObject:
    """A PDF object as the dictionary it should be, resolved; an empty one when it is not one."""
    resolved = value.get_object() if isinstance(value, PdfObject) else value
    return resolved if isinstance(resolved, DictionaryObject) else DictionaryObject()


def _draws_by_name(font: DictionaryObject) -> bool:
    """Whether a font draws each code's glyph by the name its encoding gives that code, so that the encoding says which
    glyph the page shows: a simple font (Type1, TrueType) that is not embedded, which the viewer draws from a font of its
    own by glyph name. An embedded font draws whatever its program holds at a code: in a subset font the encoding's
    names are not its glyphs, and checking them read Chrome's "fourteen (14)" as a disagreement (corpus, 2026-10-30)."""
    if font.get("/Subtype") not in ("/Type1", "/TrueType", "/MMType1"):
        return False
    descriptor = _dictionary(font.get("/FontDescriptor"))
    return not any(key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3"))


def _fonts(resources: DictionaryObject) -> dict[str, Font]:
    fonts: dict[str, Font] = {}
    table = _dictionary(resources.get("/Font"))
    for name in table:
        fonts[name] = Font.from_font_resource(_dictionary(table[name]))
    return fonts


class _Walk:
    """The page's operators, walked once: the strings drawn, what is painted beneath them, what is not read."""

    def __init__(self, page: PageObject) -> None:
        self.page = page
        self.state = TextStateManager()
        self.now = _Graphics()
        self.saved: list[_Graphics] = []
        self.shown: list[Shown] = []
        self.block = 0
        self.painted: list[Box] = []
        self.images: list[Box] = []
        self.unknown_paint = False
        self.path: list[tuple[float, float]] = []
        crop = page.cropbox
        self.crop: Box = (float(crop.left), float(crop.bottom), float(crop.right), float(crop.top))
        self.forms: list[int] = []
        self.disagreements = 0
        self.in_text = False
        self.outer = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]  # the cm in force outside every q (see "cm" below)
        self.named_glyphs = False  # the current font draws each code's glyph by the name its encoding gives it

    # ---------------------------------------------------------------- operators

    def run(self, operations: Iterator[tuple[list[Any], bytes]], fonts: dict[str, Font], resources: DictionaryObject) -> None:
        depth = len(self.saved)
        for operands, op in operations:
            self._operator(op, operands, fonts, resources)
        while len(self.saved) > depth:  # a stream that leaves its q open does not leak its state to the next
            self._restore()

    def _save(self) -> None:
        self.state.add_q()
        self.saved.append(self.now)
        self.now = _Graphics(self.now.render, self.now.white, self.now.space)

    def _restore(self) -> None:
        if self.saved:
            self.state.remove_q()
            self.now = self.saved.pop()

    def _operator(self, op: bytes, operands: list[Any], fonts: dict[str, Font], resources: DictionaryObject) -> None:
        state = self.state
        if op == b"q":
            self._save()
        elif op == b"Q":
            self._restore()
        elif op == b"cm":
            if self.saved or self.in_text:
                state.add_cm(*operands)
            else:
                # pypdf's layout mode applies a cm only inside q ... Q or a text object, and its fixed-width layout
                # (spaces from the gaps between strings, blank lines from the gaps between lines) is tuned to the
                # coordinates that gives, so they are kept for it. One outside is kept here, and every decision made on
                # where text lies on the page (off it, beneath what) reads the page's own coordinates through it.
                values = _numbers(operands)
                if len(values) == 6:
                    self.outer = _multiply(values, self.outer)
        elif op == b"BT":
            self.block += 1
            self.in_text = True
            state.reset_tm()
        elif op == b"ET":
            self.in_text = False
            state.reset_tm()
        elif op == b"Tj":
            self._show(operands[0])
        elif op == b"TJ":
            for item in operands[0]:
                if isinstance(item, bytes | str):
                    self._show(item)
                else:
                    self._advance(state.text_state_params().displacement_matrix(word="", td_offset=float(item))[4])
        elif op == b"'":
            state.reset_trm()
            state.add_tm([0, -state.TL])
            self._show(operands[0])
        elif op == b'"':
            state.reset_trm()
            state.set_state_param(b"Tw", operands[0])
            state.set_state_param(b"Tc", operands[1])
            state.add_tm([0, -state.TL])
            self._show(operands[2])
        elif op in (b"Td", b"Tm", b"TD", b"T*"):
            state.reset_trm()
            if op == b"Tm":
                state.reset_tm()
            elif op == b"TD":
                state.set_state_param(b"TL", -operands[1])
            elif op == b"T*":
                operands = [0, -state.TL]
            state.add_tm(operands)
        elif op == b"Tf":
            state.set_font(resolve_font(fonts, operands[0]), operands[1])
            self.named_glyphs = _draws_by_name(_dictionary(_dictionary(resources.get("/Font")).get(operands[0])))
        elif op == b"Tr":
            values = _numbers(operands)
            self.now.render = int(values[0]) if values else 0
        elif op in (b"Tc", b"Tw", b"Tz", b"TL", b"Ts"):
            state.set_state_param(op, operands)
        elif op in (b"g", b"rg", b"k"):
            self.now.white = _white(operands, {b"g": "/DeviceGray", b"rg": "/DeviceRGB", b"k": "/DeviceCMYK"}[op])
        elif op == b"cs":
            self.now.space = str(operands[0]) if operands else "/DeviceGray"
            self.now.white = False  # each space's initial colour is black
        elif op in (b"sc", b"scn"):
            self.now.white = _white(operands, self.now.space)
        elif op in (b"m", b"l", b"c", b"v", b"y"):
            values = _numbers(operands)
            self.path.extend(_point(state.effective_transform, values[i], values[i + 1]) for i in range(0, len(values) - 1, 2))
        elif op == b"re":
            values = _numbers(operands)
            if len(values) == 4:
                x, y, w, h = values
                matrix = state.effective_transform
                self.path.extend(_point(matrix, px, py) for px, py in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)))
        elif op in (b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"):
            if self.path and not self.now.white:
                self.painted.append(_bbox(self.path))
            self.path = []
        elif op in (b"n", b"S", b"s"):
            self.path = []
        elif op == b"sh":
            self.unknown_paint = True  # a shading fills the clip, wherever that is
        elif op == b"INLINE IMAGE":
            self._image()
        elif op == b"Do":
            self._xobject(operands[0], fonts, resources)

    def _image(self) -> None:
        box = _bbox([_point(self.state.effective_transform, x, y) for x, y in ((0, 0), (1, 0), (0, 1), (1, 1))])
        self.images.append(box)
        self.painted.append(box)

    def _xobject(self, name: object, fonts: dict[str, Font], resources: DictionaryObject) -> None:
        table = _dictionary(resources.get("/XObject"))
        if not isinstance(name, str) or name not in table:
            return
        form = table[name].get_object()
        if not isinstance(form, DictionaryObject):
            return
        subtype = form.get("/Subtype")
        if subtype == "/Image":
            self._image()
            return
        if subtype != "/Form" or len(self.forms) >= MAX_FORM_DEPTH or id(form) in self.forms:
            return
        own = _dictionary(form["/Resources"]) if "/Resources" in form else resources
        form_fonts = _fonts(own) or fonts
        matrix = _numbers(form.get("/Matrix", [1, 0, 0, 1, 0, 0])) or [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        self._save()
        self.state.add_cm(*matrix)
        self.forms.append(id(form))
        try:
            self.run(iter(ContentStream(form, self.page.pdf, "bytes").operations), form_fonts, own)
        finally:
            self.forms.pop()
            self._restore()

    # ---------------------------------------------------------------- strings

    def _show(self, value: bytes | str) -> None:
        params = self.state.text_state_params(value)
        self._check_text_layer(params)
        shown = Shown(params, self.block)
        shown.hidden, shown.over_image = self._hidden(params)
        self.shown.append(shown)
        # Placed after itself, as the page draws the next string: pypdf's layout mode leaves the position where it was.
        self._advance(params.displacement_matrix()[4])

    def _advance(self, dx: float) -> None:
        """Moves the text position along the line by ``dx``. A move is a translation, and translations add, so it is added
        to the move already on top of the text state rather than stacked: stacked, 26,000 strings on one line (a bounds
        fixture) cost a product of 26,000 matrices each, past any reading's time."""
        top = self.state.transform_stack.maps[0]
        if top["is_render"]:
            top[4] = float(top[4]) + dx
        else:
            self.state.add_trm([1.0, 0.0, 0.0, 1.0, dx, 0.0])

    def _check_text_layer(self, params: TextStateParams) -> None:
        font = params.font
        if not self.named_glyphs or isinstance(font.encoding, str) or not font.character_map:
            return
        if not isinstance(params.value, bytes):
            return
        # What the encoding names at each code, before the ToUnicode map: read here from the font, not from pypdf's private
        # _decoded_value, which pypdf 6.21 removed (the check then saw nothing to compare under the lock, 2026-10-30).
        decoded = "".join(font.encoding.get(code, chr(code)) for code in params.value)
        if len(decoded) != len(params.text):
            return
        chars = list(params.text)
        for i, glyph in enumerate(decoded):
            if glyph in GUARDED and chars[i] != glyph and chars[i] in GUARDED:
                chars[i] = REPLACEMENT
                self.disagreements += 1
        params.text = "".join(chars)

    def _hidden(self, params: TextStateParams) -> tuple[str | None, bool]:
        x0, x1 = sorted((params.tx, params.displaced_tx))
        y, height = params.ty, max(params.font_height, 0.0)
        left, bottom, right, top = self.crop
        xs, ys = zip(*(_point(self.outer, x, y + dy) for x in (x0, x1) for dy in (-height, height)), strict=True)
        if max(xs) < left or min(xs) > right or max(ys) < bottom or min(ys) > top:
            return "off_page", False
        if height * math.hypot(self.outer[1], self.outer[3]) <= TINY_POINTS:
            return "tiny", False
        middle = (x0 + min(x1, x0 + height)) / 2, y + height / 3
        over_image = any(_inside(box, *middle) for box in self.images)
        if self.now.render in INVISIBLE_MODES:
            return (None, True) if over_image else ("render", False)
        if self.now.white and self.now.render in FILL_MODES and not self.unknown_paint:
            if over_image:
                return None, True
            if not any(_inside(box, *middle) for box in self.painted):
                return "white", False
        return None, False


# -------------------------------------------------------------------------------------------- grouping, as pypdf


def _groups(block: Sequence[TextStateParams]) -> list[BTGroup]:
    """One BT block's strings grouped into lines exactly as pypdf's layout mode groups them at ET (a new line where the
    baseline moves more than a line, or the text moves back more than five spaces), but that a line whose strings are
    drawn out of order is read in the order of their positions: "on [(0) 1112 (9)] TJ" draws the 9 left of the 0, and the
    page shows "90", where pypdf's stream order read "09"."""
    runs: list[list[TextStateParams]] = []
    current: list[TextStateParams] = []
    last_displaced_tx = block[0].displaced_tx if block else 0.0
    last_ty = block[0].ty if block else 0.0

    def close() -> None:
        if current:
            runs.append(list(current))
            current.clear()

    for tj in block:
        if abs(tj.ty - last_ty) > tj.font_height:
            close()
        if last_displaced_tx - tj.tx > tj.space_tx * LAYOUT_NEW_BT_GROUP_SPACE_WIDTHS:
            close()
        current.append(tj)
        last_ty, last_displaced_tx = tj.ty, tj.displaced_tx
    close()
    groups: list[BTGroup] = []
    for number, run in enumerate(runs):
        if any(b.tx < a.tx - 0.01 for a, b in pairwise(run)):
            run = sorted(run, key=lambda tj: tj.tx)
        text, end = run[0].text, run[0].displaced_tx
        for tj in run[1:]:
            excess = round(tj.tx - end, 3)
            spaces = round(excess / tj.space_tx) if excess > 0 and tj.space_tx else 0
            text = f"{text}{' ' * min(spaces, 10_000)}{tj.text}"
            end = tj.displaced_tx
        # pypdf keeps a line of spaces only at a block's end.
        if text.strip() or (number == len(runs) - 1 and text):
            groups.append(bt_group(run[0], text, end))
    return groups


def _line_groups(shown: Sequence[Shown]) -> list[BTGroup]:
    blocks: dict[int, list[TextStateParams]] = {}
    for item in shown:
        blocks.setdefault(item.block, []).append(item.params)
    return [group for block in blocks.values() for group in _groups(block)]


def char_width(shown: Sequence[Shown]) -> float | None:
    """The fixed character width pypdf's layout mode sets a page in, from all the page's lines."""
    groups = _line_groups(shown)
    return fixed_char_width(groups, 1.25) if groups else None


def render(shown: Sequence[Shown], width: float | None = None) -> str:
    """The strings as pypdf's layout mode lays out a page: grouped by BT block into lines, sorted top to bottom and left
    to right, set in fixed width with blank lines for the vertical space between them. A part of a page is set in the
    whole page's ``width``, so that the spaces between its words come out as they do for the page."""
    groups = _line_groups(shown)
    if not groups:
        return ""
    low = min(g["tx"] for g in groups)
    ordered = [
        cast(BTGroup, dict(g, tx=g["tx"] - low, displaced_tx=g["displaced_tx"] - low))
        for g in sorted(groups, key=lambda g: (g["ty"] * g["flip_sort"], -g["tx"]), reverse=True)
    ]
    return fixed_width_page(y_coordinate_groups(ordered), width or fixed_char_width(ordered, 1.25), True, 1)


# -------------------------------------------------------------------------------------------- columns


@dataclass
class _Line:
    items: list[Shown]
    y: float
    height: float

    @cached_property
    def spans(self) -> list[tuple[float, float]]:
        """The x ranges the line's text covers, merged; read once the line is complete."""
        ranges = sorted((min(s.params.tx, s.params.displaced_tx), max(s.params.tx, s.params.displaced_tx)) for s in self.items if s.params.text.strip())
        merged: list[tuple[float, float]] = []
        for low, high in ranges:
            if merged and low <= merged[-1][1] + 0.1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], high))
            else:
                merged.append((low, high))
        return merged


def _lines(shown: Sequence[Shown]) -> list[_Line]:
    """The read strings clustered into lines by baseline, top first."""

    def key(s: Shown) -> float:
        return s.params.ty * (-1 if s.params.flip_vertical else 1)

    lines: list[_Line] = []
    for item in sorted((s for s in shown if s.params.text.strip()), key=key, reverse=True):
        y, height = key(item), max(item.params.font_height, 0.1)
        if lines and abs(lines[-1].y - y) <= 0.5 * min(height, lines[-1].height):
            lines[-1].items.append(item)
        else:
            lines.append(_Line([item], y, height))
    return lines


def _free(spans: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    out, at = [], float("-inf")
    for low, high in spans:
        if low > at:
            out.append((at, low))
        at = max(at, high)
    out.append((at, float("inf")))
    return out


def _intersect(a: Sequence[tuple[float, float]], b: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for low, high in a:
        for other_low, other_high in b:
            start, end = max(low, other_low), min(high, other_high)
            if end > start:
                out.append((start, end))
    return out


def _gutters(free: Sequence[tuple[float, float]], lines: Sequence[_Line]) -> list[tuple[float, float]]:
    """The clear bands inside the run's text, wide enough to be a gutter, with text on both sides on enough lines."""
    spans = [line.spans for line in lines]
    low = min(s[0][0] for s in spans if s)
    high = max(s[-1][1] for s in spans if s)
    height = statistics.median(line.height for line in lines)
    found = []
    for start, end in free:
        if start <= low or end >= high or end - start < MIN_GUTTER_HEIGHTS * height:
            continue
        left = sum(1 for s in spans if any(b <= start for _, b in s))
        right = sum(1 for s in spans if any(a >= end for a, _ in s))
        if left >= MIN_GUTTER_LINES and right >= MIN_GUTTER_LINES:
            found.append((start, end))
    return found


def _runs(lines: Sequence[_Line]) -> list[tuple[list[_Line], list[tuple[float, float]]]]:
    """Consecutive lines that share a clear band inside their text, each with the gutters it has (none for a run that
    is one column)."""
    runs: list[tuple[list[_Line], list[tuple[float, float]]]] = []
    run: list[_Line] = []
    free: list[tuple[float, float]] = []

    def close() -> None:
        if run:
            runs.append((list(run), _gutters(free, run)))

    for line in lines:
        own = _free(line.spans)
        if run:
            joint = _intersect(free, own)
            if any(_interior(joint, [*run, line])):
                run.append(line)
                free = joint
                continue
            close()
        run, free = [line], own
    close()
    return runs


def _interior(free: Sequence[tuple[float, float]], lines: Sequence[_Line]) -> Iterator[tuple[float, float]]:
    spans = [line.spans for line in lines]
    low = min(s[0][0] for s in spans if s)
    high = max(s[-1][1] for s in spans if s)
    height = min(line.height for line in lines)
    for start, end in free:
        if start > low and end < high and end - start >= MIN_GUTTER_HEIGHTS * height:
            yield start, end


def _column_of(item: Shown, gutters: Sequence[tuple[float, float]]) -> int:
    middle = (item.params.tx + item.params.displaced_tx) / 2
    return sum(1 for start, _ in gutters if middle > start)


def _words(items: Sequence[Shown], height: float) -> int:
    """How many words strings on one line make, read by position: a string drawn a character at a time ("Q", "u",
    "a" ... in many producers' tables) is one word with its neighbours unless a gap of a space or more parts them."""
    line = ""
    end: float | None = None
    for item in sorted(items, key=lambda s: s.params.tx):
        if end is not None and item.params.tx - end > WORD_GAP_HEIGHTS * height:
            line += " "
        line += item.params.text
        end = item.params.displaced_tx
    return len(line.split())


def _prose(lines: Sequence[_Line], gutters: Sequence[tuple[float, float]]) -> bool:
    """Whether every column of these lines holds prose: two lines or more, of four words or more a line on average where
    the column has text. One line side by side is a table's row, read the same either way, and the page is then set as
    pypdf sets it."""
    if len(lines) < 2:
        return False
    columns = len(gutters) + 1
    for column in range(columns):
        counts = [_words([s for s in line.items if _column_of(s, gutters) == column], line.height) for line in lines]
        counts = [c for c in counts if c]
        if not counts or sum(counts) / len(counts) < MIN_PROSE_WORDS:
            return False
    return True


def page_text(page: PageObject) -> PageText:
    """The page's text, columns read one after the other, with what was left out counted (module docstring)."""
    walk = _Walk(page)
    operations = iter(ContentStream(page["/Contents"].get_object(), page.pdf, "bytes").operations) if "/Contents" in page else iter([])
    resources = _dictionary(page.get("/Resources"))
    walk.run(operations, page._layout_mode_fonts(), resources)
    result = PageText(text="", disagreements=walk.disagreements, drawn=bool(walk.shown))
    read: list[Shown] = []
    for item in walk.shown:
        if item.params.rotated:
            result.rotated += len(item.params.text.strip())
        elif item.hidden is not None:
            result.hidden[item.hidden] = result.hidden.get(item.hidden, 0) + len(item.params.text.strip())
        elif not item.params.font.interpretable:
            result.unreadable += len(item.params.text.strip()) or 1
        else:
            read.append(item)
            result.image_text += len(item.params.text.strip()) if item.over_image else 0
    runs = _runs(_lines(read))
    prose = [(lines, gutters, [(band, _prose(band, gutters)) for band in _bands(lines)]) for lines, gutters in runs if gutters]
    result.side_by_side = any(not is_prose for _, _, bands in prose for _, is_prose in bands)
    if not any(is_prose for _, _, bands in prose for _, is_prose in bands):
        # No prose side by side: the page is read as pypdf reads it, a line at a time (a table, a signature block).
        result.text = render(read)
        return result
    pieces: list[str] = []
    plain: list[Shown] = []
    width = char_width(read)
    for lines, gutters in runs:
        if not gutters:
            plain.extend(item for line in lines for item in line.items)
            continue
        if plain:
            pieces.append(render(plain, width))
            plain = []
        for band in _bands(lines):
            if _prose(band, gutters):
                result.columns = True
                for column in range(len(gutters) + 1):
                    pieces.append(render([item for line in band for item in line.items if _column_of(item, gutters) == column], width))
            else:
                pieces.append(render([item for line in band for item in line.items], width))
    if plain:
        pieces.append(render(plain, width))
    result.text = "\n\n".join(piece for piece in pieces if piece.strip())
    return result


def _bands(lines: Sequence[_Line]) -> list[list[_Line]]:
    """A column run cut where a vertical gap of a line or more lies between two lines: a table's rows, or paragraphs
    of side-by-side text that end level."""
    bands: list[list[_Line]] = []
    for line in lines:
        if bands and bands[-1][-1].y - line.y - max(line.height, bands[-1][-1].height) < BAND_GAP_HEIGHTS * line.height:
            bands[-1].append(line)
        else:
            bands.append([line])
    return bands
