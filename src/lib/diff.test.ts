/**
 * Where a replaced clause and its replacement differ (lib/diff). The texts are the synthetic amended sample's clause
 * 7.2 and its replacement, as the reader stores them; the expectations come from reading the two clauses, not the code.
 */

import { describe, expect, it } from "vitest";

import { aroundChanges, wordContrast, type DiffPiece } from "./diff";

const ORIGINAL =
  '7.2 This Agreement renews automatically at the end of the Initial Term and at the end of each Renewal Term for a further term of twelve (12) months (each a "Renewal Term") unless either party gives the other written notice of non-renewal not less than ninety (90) days before the end of the then-current Term.';
const REPLACEMENT =
  '7.2 This Agreement renews automatically at the end of the Initial Term and at the end of each Renewal Term for a further term of twelve (12) months (each a "Renewal Term") unless either party gives the other written notice of non-renewal not less than one hundred fifty (150) days, and not more than two hundred ten (210) days, before the end of the then-current Term. A notice of non-renewal given outside that period has no effect.';

const text = (pieces: readonly DiffPiece[]) => pieces.map((p) => p.text).join("");
const marked = (pieces: readonly DiffPiece[]) => pieces.filter((p) => p.changed).map((p) => p.text).join(" | ");

describe("wordContrast", () => {
  it("marks the words the two clauses differ in, and nothing they share", () => {
    const contrast = wordContrast(ORIGINAL, REPLACEMENT);
    expect(contrast).not.toBeNull();
    const { original, replacement } = contrast!;
    expect(marked(original)).toContain("ninety (90)");
    expect(marked(replacement)).toContain("one hundred fifty (150)");
    expect(marked(replacement)).toContain("two hundred ten (210)");
    expect(marked(replacement)).toContain("A notice of non-renewal given outside that period has no effect.");
    // The shared opening is not marked on either side.
    expect(marked(original)).not.toContain("renews automatically");
    expect(marked(replacement)).not.toContain("renews automatically");
  });

  it("gives back each text exactly, so nothing is invented or lost", () => {
    const seeded = (seed: number) => () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
    const random = seeded(7);
    const words = ["notice", "days", "(90)", "the", "Term.", "not", "less", "than", "  ", "\n"];
    for (let round = 0; round < 200; round++) {
      const make = () => Array.from({ length: 1 + Math.floor(random() * 30) }, () => words[Math.floor(random() * words.length)]).join(" ");
      const a = make();
      const b = make();
      const contrast = wordContrast(a, b);
      if (contrast === null) continue;
      expect(text(contrast.original)).toBe(a);
      expect(text(contrast.replacement)).toBe(b);
    }
  });

  it("marks nothing between identical texts, and declines texts too long to compare at a bounded cost", () => {
    expect(wordContrast(ORIGINAL, ORIGINAL)).toBeNull();
    const long = (prefix: string) => Array.from({ length: 700 }, (_, i) => `${prefix}${i}`).join(" ");
    expect(wordContrast(long("a"), long("b"))).toBeNull();
  });
});

describe("aroundChanges", () => {
  it("shows each side around its change, not the opening both sides share", () => {
    const { original, replacement } = wordContrast(ORIGINAL, REPLACEMENT)!;
    const first = text(aroundChanges(original));
    const second = text(aroundChanges(replacement));
    expect(first).toContain("ninety (90)");
    expect(second).toContain("one hundred fifty (150)");
    expect(first.startsWith("…")).toBe(true);
    expect(first).not.toContain("renews automatically");
    expect(second.length).toBeLessThanOrEqual(361);
  });
});
