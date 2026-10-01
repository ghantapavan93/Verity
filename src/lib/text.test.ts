import { describe, expect, it } from "vitest";
import { codePointLength, splitByCodePoints } from "./text";

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
