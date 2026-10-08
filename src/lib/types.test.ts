import { describe, expect, it } from "vitest";
import { codeRole, decidedByCode, retrievalNote, sectionsReadNote, statusLabel } from "./types";

/** The chip a lawyer reads most: "Within guidance" is a comparison code made, or it says it is the model's view. */
describe("statusLabel", () => {
  it("calls a pass without guidance an answer", () => {
    expect(statusLabel("pass", false)).toBe("Model's answer");
    expect(statusLabel("pass", false, "model_hint")).toBe("Model's answer");
  });

  it("calls a computed pass within guidance", () => {
    expect(statusLabel("pass", true, "computed_days")).toBe("Within guidance");
  });

  it("marks a pass the model hinted as the model's view", () => {
    expect(statusLabel("pass", true, "model_hint")).toBe("Within guidance (model's view)");
  });

  it("leaves the other statuses as they are", () => {
    expect(statusLabel("needs_review", true, "model_hint")).toBe("Needs review");
    expect(statusLabel("missing", false)).toBe("Not found in the sections read");
  });

  it("gives a caller that does not say who decided the weaker claim", () => {
    expect(statusLabel("pass", true)).toBe("Within guidance (model's view)");
  });

  it("knows which sources mean code decided", () => {
    for (const source of ["computed_days", "position_check", "ambiguous_fact", "reference_check"]) expect(decidedByCode(source)).toBe(true);
    for (const source of ["confirmed_days", "model_hint", "no_evidence", "", null, undefined]) expect(decidedByCode(source)).toBe(false);
  });

  it("never says code decided a pass the model had to propose", () => {
    expect(statusLabel("pass", true, "confirmed_days")).toBe("Within guidance (confirmed by code)");
    expect(codeRole("confirmed_days")).toBe("Code confirmed");
    expect(codeRole("computed_days")).toBe("Code found a conflict");
    expect(codeRole("model_hint")).toBe("Code did not decide");
    expect(codeRole("no_evidence")).toBe("Code withheld");
    expect(codeRole(undefined)).toBe("Code did not decide");
  });
});

/** Sections handed over because nothing ranked are never described as retrieval's choice. */
describe("how the sections were chosen", () => {
  it("says a ranking is a ranking", () => {
    expect(retrievalNote("lexical_match")).toContain("in rank order");
    expect(sectionsReadNote("lexical_match", 6, 123)).toBe("the model was handed 6 of this document's 123 sections");
  });

  it("says opening sections were not chosen for the question", () => {
    expect(retrievalNote("opening_fallback")).toContain("not ones chosen for it");
    expect(retrievalNote("opening_fallback")).not.toContain("rank order");
    expect(sectionsReadNote("opening_fallback", 6, 123)).toBe(
      "retrieval ranked no section for this question, so the model was handed the opening 6 of this document's 123 sections",
    );
  });

  it("claims nothing for a run recorded before the mode was a field", () => {
    expect(retrievalNote(null)).toContain("was not recorded");
    expect(retrievalNote(undefined)).not.toContain("rank order");
    expect(sectionsReadNote(null, 6, 123)).toBe("the model was handed 6 of this document's 123 sections");
  });
});
