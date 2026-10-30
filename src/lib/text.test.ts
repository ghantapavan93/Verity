import { describe, expect, it } from "vitest";
import { aroundCodePoints, clipCodePoints, codePointLength, revealInvisible, shownText, splitByCodePoints } from "./text";

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

/** A stretch of a text, read in the context of the whole: the edges of a highlight are not the edges of the text. */
describe("revealInvisible over a stretch", () => {
  it("judges a selector at the stretch's edge by its neighbours in the whole text", () => {
    const text = "9\ufe0f0 days";
    // As the paper splits it at a highlight ending after the "9": the selector is the first character after the mark.
    expect(revealInvisible(text, 1).map((p) => p.invisible)).toEqual([true, false]);
    expect(revealInvisible(text, 0, 1)).toEqual([{ text: "9", invisible: false }]);
  });

  it("control: the whole text read whole is read as before", () => {
    expect(revealInvisible("plain words", 0)).toEqual(revealInvisible("plain words"));
    expect(revealInvisible("ab\u202ecd", 1, 4).map((p) => p.text)).toEqual(["b", "\u202e", "c"]);
  });
});

describe("shownText", () => {
  it("writes each invisible character as its name, for a label or an attribute", () => {
    expect(shownText("fifteen \u202e(15)\u202c days")).toBe("fifteen [U+202E](15)[U+202C] days");
    expect(shownText("\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u062f")).toBe("\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u062f"); // control
  });
});

const LONE_SURROGATE = /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/;

/**
 * The text around a located span, and an excerpt, in code points: for random texts mixing astral characters before,
 * inside and after a span placed by code-point offsets, the stretch inside is the located text exactly, and no cut
 * splits a surrogate pair (stress test, 2026-10-30).
 */
describe("aroundCodePoints and clipCodePoints", () => {
  const ALPHABET = ["a", "b", " ", ".", "\u{1F600}", "\u{20B9F}", "\u{1D412}", "\u00e9", "\u6f22"];

  function random(seed: number) {
    let state = seed;
    return () => {
      state = (state * 1103515245 + 12345) % 2 ** 31;
      return state / 2 ** 31;
    };
  }

  it("keeps the located text exact and every cut whole", () => {
    for (let seed = 1; seed <= 200; seed++) {
      const next = random(seed);
      const chars = Array.from({ length: 20 + Math.floor(next() * 400) }, () => ALPHABET[Math.floor(next() * ALPHABET.length)]);
      const start = Math.floor(next() * (chars.length - 1));
      const end = start + 1 + Math.floor(next() * (chars.length - start - 1));
      const text = chars.join("");
      const around = aroundCodePoints(text, start, end, 40)!;
      expect(around, `seed ${seed}`).not.toBeNull();
      const [lead, located, trail] = [chars.slice(around.from, start), chars.slice(start, end), chars.slice(end, around.to)].map((c) => c.join(""));
      expect(located).toBe(chars.slice(start, end).join(""));
      expect(around.from).toBeLessThanOrEqual(start);
      expect(around.to).toBeGreaterThanOrEqual(end);
      expect(LONE_SURROGATE.test(lead + located + trail), `seed ${seed}`).toBe(false);
      expect(LONE_SURROGATE.test(clipCodePoints(text, 30)), `seed ${seed}`).toBe(false);
    }
  });

  it("refuses offsets that do not fit the text in code points, though they fit its UTF-16 length", () => {
    const text = "\u{1F600}\u{1F600}ab"; // 4 code points, 6 UTF-16 units
    expect(aroundCodePoints(text, 2, 4, 10)).not.toBeNull();
    expect(aroundCodePoints(text, 2, 6, 10)).toBeNull();
    expect(aroundCodePoints(text, 3, 3, 10)).toBeNull();
  });

  it("control: ASCII text is cut between words, as before", () => {
    const text = "one two three four five six seven";
    const start = text.indexOf("four");
    expect(aroundCodePoints(text, start, start + 4, 8)).toEqual({ from: text.indexOf("three"), to: text.indexOf(" six"), cutBefore: true, cutAfter: true });
    expect(clipCodePoints("short", 10)).toBe("short");
    expect(clipCodePoints("a longer sentence here", 10)).toBe("a longer…");
  });
});

/**
 * The class, not the example: the API's span and passage offsets count code points, so nothing outside this module slices
 * or bounds a text by them with String.slice or .length, which count UTF-16 units. The paper and the spine did it here;
 * the phone's quote context and the /break paper did it themselves, and moved off the located text after an astral
 * character (stress test, 2026-10-30). A new surface that does it fails here.
 */
describe("every surface reads the API's offsets in code points", () => {
  it("slices and bounds no text by a span's offsets except through this module", async () => {
    const { readdirSync, readFileSync, statSync } = await import("node:fs");
    const { join } = await import("node:path");
    const files = (dir: string): string[] =>
      readdirSync(dir).flatMap((name) => {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) return files(path);
        return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !path.endsWith(join("lib", "text.ts")) ? [path] : [];
      });
    const offset = String.raw`[\w?.!\]]*\b(?:span|s|sp|passage|p|m|match|located)\.(?:start|end)\b`;
    const sliced = new RegExp(String.raw`\.(?:slice|substring|substr)\([^)]*${offset}`);
    const bounded = new RegExp(String.raw`${offset}\s*[<>]=?\s*[\w.]+\.length|\.length\s*[<>]=?\s*${offset}`);
    const found = files(join(process.cwd(), "src")).flatMap((path) =>
      readFileSync(path, "utf8")
        .split("\n")
        .flatMap((line, i) => (sliced.test(line) || bounded.test(line) ? [`${path.split("src")[1]}:${i + 1}`] : [])),
    );
    expect(found).toEqual([]);
  });
});
