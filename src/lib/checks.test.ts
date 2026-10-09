import { describe, expect, it } from "vitest";
import { checkLedger, type CheckRow } from "./checks";
import type { FindingView, SectionView } from "./types";

const section = { id: "s5", number: "5.3", heading: "Termination", text: "" } as unknown as SectionView;
const sections = new Map([[section.id, section]]);

function finding(over: Partial<FindingView> = {}): FindingView {
  return {
    id: "f1",
    topic: "Late fee",
    status: "pass",
    statusSource: "model_hint",
    statusReason: null,
    evidenceKind: "passage",
    review: null,
    latestReviewId: 0,
    conclusion: "The late fee is 5% per month.",
    modelConclusion: "The late fee is 5% per month.",
    spans: [
      {
        sectionId: "s5",
        start: 0,
        end: 30,
        quote: "a late fee of 10% per month",
        verified: true,
        method: "exact",
        matchCount: 1,
        citedSectionLabel: "sec_1",
        clauseLabel: null,
      },
    ],
    guidanceReference: null,
    observed: null,
    required: null,
    suggestedPosition: null,
    ...over,
  } as FindingView;
}

const row = (rows: CheckRow[], key: CheckRow["key"]) => rows.find((r) => r.key === key);

describe("checkLedger: what was checked, and by whom", () => {
  it("never lets a located quote stand for a supported answer (quote 10%, answer 5%)", () => {
    const rows = checkLedger(finding(), true, sections, { text: "the model was handed 6 of this document's 123 sections", partial: true });
    expect(row(rows, "quote")).toMatchObject({ by: "code" });
    expect(row(rows, "quote")?.text).toMatch(/^Found in the document text at §5.3 · Termination, word for word/);
    expect(row(rows, "support")).toMatchObject({ by: "model" });
    expect(row(rows, "support")?.text).toMatch(/^Not checked by code/);
    expect(row(rows, "comparison")).toMatchObject({ by: "nobody" });
    expect(row(rows, "comparison")?.text).toMatch(/the status is the model's view/);
    // Policy v4 can leave a guidance period unread on purpose; the row never says the guidance has none.
    expect(row(rows, "comparison")?.text).toMatch(/no period it could read/);
    expect(row(rows, "context")?.text).toBe("The model was handed 6 of this document's 123 sections; the other sections were not read");
    expect(row(rows, "person")).toMatchObject({ text: "Not reviewed yet", by: "nobody" });
    // Nothing the code did not do is attributed to it.
    expect(rows.filter((r) => r.by === "code").map((r) => r.key)).toEqual(["quote"]);
  });

  it("says what code compared when code decided the status", () => {
    const rows = checkLedger(
      finding({
        status: "needs_review",
        statusSource: "computed_days",
        statusReason: "the contract provides 60 calendar days; the guidance requires at least 90 calendar days",
      }),
      true,
      sections,
      null,
    );
    expect(row(rows, "comparison")).toMatchObject({ by: "code" });
    expect(row(rows, "comparison")?.text).toBe(
      "Code found a conflict: the contract provides 60 calendar days; the guidance requires at least 90 calendar days",
    );
    expect(row(rows, "context")).toBeUndefined();
  });

  it.each([
    ["reference_check", "Code lowered it"],
    ["position_check", "Code lowered it"],
    ["ambiguous_fact", "Code lowered it"],
    ["confirmed_days", "Code confirmed"],
  ])("credits code for %s", (source, role) => {
    const rows = checkLedger(finding({ statusSource: source as FindingView["statusSource"], statusReason: null }), true, sections, null);
    expect(row(rows, "comparison")).toMatchObject({ by: "code" });
    expect(row(rows, "comparison")?.text.length).toBeGreaterThan(10);
    expect(role).toBeTruthy();
  });

  it("says nothing was compared without guidance, and when no passage was found", () => {
    expect(row(checkLedger(finding(), false, sections, null), "comparison")?.text).toMatch(/no guidance was given/);
    const none = checkLedger(finding({ statusSource: "no_evidence", spans: [] }), true, sections, null);
    expect(row(none, "quote")).toMatchObject({ text: "No passage cited", by: "nobody" });
    expect(row(none, "comparison")?.text).toMatch(/^Nothing: no passage was found/);
  });

  it("calls the provisions behind a not-found answer what they are: read, not relied on", () => {
    const rows = checkLedger(finding({ status: "missing", evidenceKind: "coverage" }), true, sections, null);
    expect(row(rows, "quote")).toMatchObject({ label: "Passages", by: "nobody" });
    expect(row(rows, "quote")?.text).toMatch(/^Read, not relied on: 1 provision the model looked at/);
    expect(row(rows, "support")?.text).toMatch(/that the point is absent is the model's reading/);
    expect(rows.some((r) => r.by === "code")).toBe(false);
  });

  it("counts withheld passages and does not call a typed match word for word", () => {
    const spans = [
      { ...finding().spans[0], method: "typed" },
      { ...finding().spans[0], verified: false, method: "none", sectionId: null },
    ];
    const text = row(checkLedger(finding({ spans }), true, sections, null), "quote")?.text;
    expect(text).toMatch(/spacing and punctuation aside/);
    expect(text).toMatch(/; 1 withheld$/);
    const allWithheld = row(checkLedger(finding({ spans: [spans[1]] }), true, sections, null), "quote");
    expect(allWithheld).toMatchObject({ by: "nobody" });
    expect(allWithheld?.text).toMatch(/^Not found in the document text/);
  });

  it("names the person who decided", () => {
    const rows = checkLedger(finding({ review: { verdict: "confirmed", reviewer: "Didier", at: "" } }), true, sections, null);
    expect(row(rows, "person")).toMatchObject({ text: "Confirmed by Didier", by: "person" });
  });

  it("credits code for a comparison it made even when it left the model's status standing (round 2, AD15)", () => {
    const reason =
      'the contract provides 120 calendar days; the guidance requires at least 90 calendar days, but code does not confirm that as a pass: the clause carries a condition or an exception ("except")';
    const rows = checkLedger(finding({ statusSource: "model_hint", statusReason: reason }), true, sections, null);
    expect(row(rows, "comparison")).toMatchObject({ by: "code" });
    expect(row(rows, "comparison")?.text).toBe(`Code compared: ${reason}. The status is still the model's view.`);
  });

  it("says when the model answered from part of the document", () => {
    const rows = checkLedger(finding(), true, sections, { text: "the model was handed 1 of this document's 4 sections", partial: true });
    expect(row(rows, "context")?.text).toBe("The model was handed 1 of this document's 4 sections; the other sections were not read");
    const whole = checkLedger(finding(), true, sections, { text: "the model was handed 4 of this document's 4 sections", partial: false });
    expect(row(whole, "context")?.text).toBe("The model was handed 4 of this document's 4 sections");
  });

  it("does not call a match that differs in case word for word without saying so", () => {
    const spans = [{ ...finding().spans[0], method: "casefold" }];
    expect(row(checkLedger(finding({ spans }), true, sections, null), "quote")?.text).toMatch(/word for word, case aside$/);
  });
});
