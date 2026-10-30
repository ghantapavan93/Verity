import { describe, expect, it } from "vitest";
import {
  stageAnnouncement,
  codeRole,
  decidedByCode,
  evidenceJump,
  partOf,
  passageLabel,
  retrievalNote,
  sectionsReadNote,
  statusLabel,
  type FindingView,
  type SectionView,
  type SpanView,
} from "./types";

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
    expect(statusLabel("missing", false)).toBe("Not found in the sections read (model's view)");
  });

  it("gives a caller that does not say who decided the weaker claim", () => {
    expect(statusLabel("pass", true)).toBe("Within guidance (model's view)");
  });

  it("gives a source it does not know the weaker claim", () => {
    expect(statusLabel("pass", true, "a_source_added_later")).toBe("Within guidance (model's view)");
    expect(statusLabel("pass", true, "confirmed_days")).toBe("Within guidance (confirmed by code)");
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
    // Only a day comparison finds a conflict; the other checks lower a finding for their own named reason.
    for (const source of ["reference_check", "position_check", "ambiguous_fact"]) expect(codeRole(source)).toBe("Code lowered it");
    expect(codeRole("a_source_added_later")).toBe("Code did not decide");
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

describe("passageLabel", () => {
  const section = { id: "s5", number: "5", heading: "Intellectual Property (part 3)", text: "" } as SectionView;
  const span = { sectionId: "s5", start: 10, end: 40, quote: "q", verified: true, method: "exact", citedSectionLabel: "sec_8" } as SpanView;

  it("names the clause the passage sits in when the API read one from the document's own text", () => {
    expect(passageLabel({ ...span, clauseLabel: "§13.2 Governing Law" }, section)).toBe("§13.2 Governing Law");
  });

  it("falls back to the section, as before, when the text names no clause before the passage", () => {
    expect(passageLabel({ ...span, clauseLabel: null }, section)).toBe("§5 · Intellectual Property (part 3)");
    expect(passageLabel(span, section)).toBe("§5 · Intellectual Property (part 3)");
  });
});

describe("partOf", () => {
  // The same cases as the backend's part_heading / PART_HEADING (backend/app/ingest/sections.py).
  it("reads the part a heading names, and nothing else", () => {
    expect(partOf("Fees and Milestones (part 3)")).toEqual({ base: "Fees and Milestones", index: 3 });
    expect(partOf("Intellectual Property (part 1)")).toEqual({ base: "Intellectual Property", index: 1 });
    expect(partOf("Fees (part 2) and more")).toBeNull();
    expect(partOf("Fees and Milestones")).toBeNull();
  });
});

/** Where the document goes when the evidence drawer opens (release readiness, 2026-10-10, and its review). */
describe("evidenceJump", () => {
  const span = (sectionId: string | null, verified: boolean) => ({ sectionId, verified, start: 0, end: 5 }) as SpanView;
  const finding = (...spans: SpanView[]) => ({ spans }) as FindingView;
  const wide = { shown: true, narrow: false };

  it("goes to the first passage the API located", () => {
    expect(evidenceJump(finding(span(null, false), span("s2", true), span("s3", true)), wide)?.sectionId).toBe("s2");
  });

  it("does not mark a withheld finding's passage as evidence", () => {
    expect(evidenceJump(finding(span("s2", true)), { shown: false, narrow: false })).toBeNull();
  });

  it("does not move a document a phone does not show", () => {
    expect(evidenceJump(finding(span("s2", true)), { shown: true, narrow: true })).toBeNull();
  });

  it("control: a finding with no located passage goes nowhere", () => {
    expect(evidenceJump(finding(span("s2", false), span(null, false)), wide)).toBeNull();
  });
});

describe("stageAnnouncement", () => {
  it("says, on a hosted model, that checking may wait for the model to wake", () => {
    // War room UX-06: the live region said "Checking" and then nothing for up to three minutes.
    expect(stageAnnouncement("checking", true)).toBe("Checking. The model may be waking, which adds one and a half to three minutes to the first answer.");
  });

  it("control: other stages, and a model that does not sleep, say the stage alone", () => {
    expect(stageAnnouncement("checking", false)).toBe("Checking");
    expect(stageAnnouncement("reading", true)).toBe("Reading contract");
  });
});
