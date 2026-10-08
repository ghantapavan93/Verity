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

/** The text in pieces: ordinary text, and each character the reader would remove on its own, named by its code point. */
export function revealInvisible(text: string): VisiblePiece[] {
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
  chars.forEach((ch, i) => {
    if (!hidden[i]) {
      run += ch;
      return;
    }
    if (run) pieces.push({ text: run, invisible: false });
    run = "";
    pieces.push({ text: ch, invisible: true, codePoint: `U+${ch.codePointAt(0)!.toString(16).toUpperCase().padStart(4, "0")}` });
  });
  if (run) pieces.push({ text: run, invisible: false });
  return pieces;
}
