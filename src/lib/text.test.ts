import { describe, expect, it } from "vitest";
import { codePointLength, revealInvisible, splitByCodePoints } from "./text";

/** The API's offsets count code points; a character outside the Basic Multilingual Plane before a span must not shift it. */
describe("code-point slicing", () => {
  it("counts an astral character once, as Python does", () => {
    expect(codePointLength("a𝔸b")).toBe(3);
    expect("a𝔸b".length).toBe(4);
  });

  it("splits at the located text even after an astral character", () => {
    const text = "Clause 𝔸: thirty (30) days' notice.";
    const start = codePointLength("Clause 𝔸: ");
    const end = start + codePointLength("thirty (30) days");
    expect(splitByCodePoints(text, start, end)).toEqual(["Clause 𝔸: ", "thirty (30) days", "' notice."]);
  });

  it("is the plain slice when every character is one unit", () => {
    expect(splitByCodePoints("abcdef", 2, 4)).toEqual(["ab", "cd", "ef"]);
  });
});

describe("revealInvisible", () => {
  it("names each invisible format character instead of letting it act on the text", () => {
    expect(revealInvisible("terminate on \u202e09\u202c days")).toEqual([
      { text: "terminate on ", invisible: false },
      { text: "\u202e", invisible: true, codePoint: "U+202E" },
      { text: "09", invisible: false },
      { text: "\u202c", invisible: true, codePoint: "U+202C" },
      { text: " days", invisible: false },
    ]);
    expect(revealInvisible("9\u200b0").map((p) => p.invisible)).toEqual([false, true, false]);
  });

  it("leaves text without them, and the joiners and direction marks text needs, as they are", () => {
    for (const text of ["plain words", "שלום", "a\u200eb", "\u{1F468}\u200d\u{1F469}"]) {
      expect(revealInvisible(text)).toEqual([{ text, invisible: false }]);
    }
  });
});

describe("revealInvisible, the characters reader v10 also removes", () => {
  it("marks a joiner or selector between two ASCII letters or digits, as the reader removes it there", () => {
    for (const cp of [0x034f, 0xfe00, 0xfe0f, 0xe0100, 0x200d, 0x3164]) {
      const ch = String.fromCodePoint(cp);
      expect(revealInvisible(`9${ch}0 days`).map((p) => p.invisible)).toEqual([false, true, false]);
    }
  });

  it("leaves a keycap, an emoji form and a CJK variant as text", () => {
    for (const text of ["9\ufe0f\u20e3", "\u2764\ufe0f", "\u6f22\ufe00", "a\ufe0f b"]) {
      expect(revealInvisible(text)).toEqual([{ text, invisible: false }]);
    }
  });
});
