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
