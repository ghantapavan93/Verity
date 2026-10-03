/**
 * The gauge draws only what code wrote. Its parse is of code's own sentence template (backend/app/policy/durations.py,
 * `evaluate`), exact or nothing: a sentence the model wrote, or a comparison across units, draws no gauge.
 */

import { describe, expect, it } from "vitest";
import { readComparison } from "./DayGauge";

describe("readComparison", () => {
  it("reads a shortfall against a floor", () => {
    expect(readComparison("the contract provides 60 calendar days; the guidance requires at least 90 calendar days")).toEqual({
      provided: 60,
      required: 90,
      ceiling: null,
      operator: "at least",
      unit: "calendar day",
      met: false,
    });
  });

  it("reads a pass that meets the floor exactly, and a ceiling that is exceeded", () => {
    expect(readComparison("the contract provides 30 calendar days; the guidance requires at least 30 calendar days")?.met).toBe(true);
    expect(readComparison("the contract provides 45 calendar days; the guidance requires at most 30 calendar days")?.met).toBe(false);
    expect(readComparison("the contract provides 10 business days; the guidance requires exactly 10 business days")?.met).toBe(true);
  });

  it("reads a range", () => {
    const range = readComparison("the contract provides 45 calendar days; the guidance requires between 30 and 60 calendar days");
    expect(range).toMatchObject({ operator: "between", required: 30, ceiling: 60, met: true });
    expect(readComparison("the contract provides 75 calendar days; the guidance requires between 30 and 60 calendar days")?.met).toBe(false);
  });

  it("draws nothing for a sentence that is not code's, for mixed units, or for no reason at all", () => {
    expect(readComparison("The notice period looks fine to me.")).toBeNull();
    expect(readComparison("the contract provides 60 calendar days; the guidance requires at least 3 months")).toBeNull();
    expect(readComparison("the model asked for review, but code does not confirm that as a pass: the quote refers to a section it was not handed")).toBeNull();
    expect(readComparison(null)).toBeNull();
    expect(readComparison("")).toBeNull();
  });
});
