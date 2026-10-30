import { expect } from "vitest";

/**
 * Invisible characters a model can write into any string it returns (hostile-model review, 2026-10-30): overrides,
 * embeddings, isolates, a zero-width space, a word joiner, a byte-order mark and a tag character. The record keeps them
 * as written; no surface may let one act on the page.
 */
export const HOSTILE = ["\u202e", "\u202c", "\u202b", "\u2067", "\u2069", "\u200b", "\u2060", "\ufeff", "\u{e0041}"];

/** Words, then every hostile character, then the override that displayed "fifteen (15)" as "fifteen (51)". */
export const hostile = (text: string) => `${text} ${HOSTILE.join("x")} fifteen \u202e(15)\u202c days`;

/** No invisible character acts on the page: each is shown by name, and the words around it are still there. */
export function expectShownByName(container: HTMLElement, words: string) {
  const text = container.textContent ?? "";
  for (const ch of HOSTILE) expect(text, `U+${ch.codePointAt(0)!.toString(16).toUpperCase()} acts unmarked`).not.toContain(ch);
  expect(text).toContain("U+202E");
  expect(text).toContain("U+E0041");
  expect(text).toContain(words);
}
