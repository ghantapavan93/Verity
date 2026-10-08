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
 * Reader v9 removes them; for an older reading the screen shows each one as a visible marker instead of letting it act.
 * Kept as text, as the reader keeps them: joiners and non-joiners, and the left-to-right, right-to-left and Arabic marks.
 */
const INVISIBLE = /[\p{Cf}]/gu;
const KEPT = new Set(["\u200c", "\u200d", "\u200e", "\u200f", "\u061c"]);

export type VisiblePiece = { text: string; invisible: false } | { text: string; invisible: true; codePoint: string };

/** The text in pieces: ordinary text, and each invisible format character on its own, named by its code point. */
export function revealInvisible(text: string): VisiblePiece[] {
  const pieces: VisiblePiece[] = [];
  let last = 0;
  for (const match of text.matchAll(INVISIBLE)) {
    const ch = match[0];
    if (KEPT.has(ch)) continue;
    const at = match.index ?? 0;
    if (at > last) pieces.push({ text: text.slice(last, at), invisible: false });
    pieces.push({ text: ch, invisible: true, codePoint: `U+${ch.codePointAt(0)!.toString(16).toUpperCase().padStart(4, "0")}` });
    last = at + ch.length;
  }
  if (last < text.length) pieces.push({ text: text.slice(last), invisible: false });
  return pieces;
}
