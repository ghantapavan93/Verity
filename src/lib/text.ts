/**
 * The API's span offsets count Unicode code points (Python). JavaScript strings count UTF-16 units, so a
 * character outside the Basic Multilingual Plane before a span (an emoji, a mathematical letter) would shift
 * a naive slice by one. These helpers slice by code points so the highlight is the located text, exactly.
 */

export function codePointLength(text: string): number {
  return Array.from(text).length;
}

/** The text split at code-point offsets [start, end): before, inside, after. */
export function splitByCodePoints(text: string, start: number, end: number): [string, string, string] {
  const chars = Array.from(text);
  return [chars.slice(0, start).join(""), chars.slice(start, end).join(""), chars.slice(end).join("")];
}

/** Whether a span's code-point offsets fit the text it was located in: checked in code points, as they count. */
export function fitsCodePoints(text: string, start: number, end: number): boolean {
  return Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start && end <= codePointLength(text);
}

const SPACE = /^\s$/u;

/**
 * The stretch of text around a located span, in code points: up to `radius` on each side, cut between words (the
 * partial word at a cut, and the space beside it, are left out), with whether each side was cut. Null when the span does
 * not fit the text. Counted in code points, so the cut never falls inside a surrogate pair and the span inside is the
 * located text, exactly: QuoteContext sliced the API's code-point offsets as UTF-16 units, and on a phone bolded text one
 * character off for each astral character before the quote (stress test, 2026-10-30).
 */
export function aroundCodePoints(text: string, start: number, end: number, radius: number) {
  if (!fitsCodePoints(text, start, end)) return null;
  const chars = Array.from(text);
  let from = Math.max(0, start - radius);
  let to = Math.min(chars.length, end + radius);
  const cutBefore = from > 0;
  const cutAfter = to < chars.length;
  if (cutBefore) {
    const space = chars.slice(from, start).findIndex((ch) => SPACE.test(ch));
    if (space >= 0) from += space + 1;
  }
  if (cutAfter) {
    const after = chars.slice(end, to);
    let space = after.length - 1;
    while (space >= 0 && !SPACE.test(after[space])) space--;
    if (space >= 0) to = end + space;
  }
  return { from, to, cutBefore, cutAfter };
}

/**
 * At most `max` code points of the text, else its first `keep` and an ellipsis: an excerpt that never ends inside a
 * surrogate pair (a UTF-16 cut left U+FFFD at the end of a quote whose 150th unit was half an emoji).
 */
export function clipCodePoints(text: string, max: number, keep = max - 1): string {
  const chars = Array.from(text);
  return chars.length > max ? `${chars.slice(0, keep).join("").trimEnd()}…` : text;
}

/**
 * Invisible format characters (Unicode Cf) a stored reading may still hold: readings made before reader v9 kept them,
 * and they make the text on screen differ from the text that was checked ("\u202e09\u202c days" displays as "90 days").
 * Reader v9 removes them (v10 also the joiners and selectors between ASCII letters or digits); for an older reading the
 * screen shows each one as a visible marker instead of letting it act.
 * Kept as text, as the reader keeps them: joiners and non-joiners, and the left-to-right, right-to-left and Arabic marks.
 */
const INVISIBLE = /^\p{Cf}$/u;
/** Direction marks: they order neutral characters and cannot reverse a run, so the reader keeps them anywhere. */
const KEPT = new Set(["\u200e", "\u200f", "\u061c"]);
/**
 * Joiners, variation selectors and the other default-ignorable characters that are not Cf (ingest/invisible.IGNORABLE):
 * kept where they shape or vary a character, invisible and marked between two ASCII letters or digits, where the reader
 * removes them ("9\ufe0f0 days" displays as "90 days").
 */
const SHAPING = /^[\u200c\u200d\u034f\u115f\u1160\u17b4\u17b5\u180b-\u180d\u180f\u3164\ufe00-\ufe0f\uffa0\u{e0100}-\u{e01ef}]$/u;
const ASCII_WORD = /^[A-Za-z0-9]$/;

export type VisiblePiece = { text: string; invisible: false } | { text: string; invisible: true; codePoint: string };

/**
 * The text in pieces: ordinary text, and each character the reader would remove on its own, named by its code point.
 * With `start` and `end` (code points), only that stretch, read in the context of the whole text: the paper revealed the
 * text before a mark, the mark and the text after it each on its own, so a selector at the mark's edge had no neighbour
 * and acted unmarked (stress test, 2026-10-30).
 *
 * The one display primitive for text a model or a file wrote, on every surface of the interface: a model's quote, topic,
 * conclusion and readings are never cleaned on their way in (the record keeps what the model wrote), so a direction
 * override in a quote displayed "fifteen (51) days" under "found in the document text" (hostile-model review, 2026-10-30).
 * Rendered as React by shell/primitives Visible, and as a string, for an attribute or a label, by `shownText`.
 */
export function revealInvisible(text: string, start = 0, end?: number): VisiblePiece[] {
  const chars = Array.from(text);
  const hidden = chars.map((ch) => INVISIBLE.test(ch) && !KEPT.has(ch) && !SHAPING.test(ch));
  // As the reader does it: format characters first, then a run of shaping characters between two ASCII letters or digits.
  const skipped = (i: number) => hidden[i] || SHAPING.test(chars[i]);
  const neighbour = (from: number, step: number) => {
    let i = from;
    while (i >= 0 && i < chars.length && skipped(i)) i += step;
    return i >= 0 && i < chars.length ? chars[i] : "";
  };
  chars.forEach((ch, i) => {
    if (SHAPING.test(ch) && ASCII_WORD.test(neighbour(i - 1, -1)) && ASCII_WORD.test(neighbour(i + 1, 1))) hidden[i] = true;
  });
  const pieces: VisiblePiece[] = [];
  let run = "";
  for (let i = Math.max(0, start); i < Math.min(chars.length, end ?? chars.length); i++) {
    const ch = chars[i];
    if (!hidden[i]) {
      run += ch;
      continue;
    }
    if (run) pieces.push({ text: run, invisible: false });
    run = "";
    pieces.push({ text: ch, invisible: true, codePoint: `U+${ch.codePointAt(0)!.toString(16).toUpperCase().padStart(4, "0")}` });
  }
  if (run) pieces.push({ text: run, invisible: false });
  return pieces;
}

/** `revealInvisible` as one string, each marked character written as its name in brackets: for an attribute, a label. */
export function shownText(text: string): string {
  return revealInvisible(text)
    .map((piece) => (piece.invisible ? `[${piece.codePoint}]` : piece.text))
    .join("");
}
