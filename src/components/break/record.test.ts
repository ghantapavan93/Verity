import { describe, expect, it } from "vitest";

import { charDiff, partyCheckScore, sharedRun, whyMissed, wordsOf } from "./record";
import record from "./break-record.json";
import type { BreakRecord } from "./record";

const data = record as unknown as BreakRecord;

describe("sharedRun: the words a quote shares with the passage the expected answer relies on", () => {
  it("finds the longest run the two strings share", () => {
    expect(
      sharedRun("so the Representative notifies Buyer within 45 days, and more", ["Unless the Representative notifies Buyer within 45 days after"]),
    ).toEqual({
      start: 3,
      end: 51,
    });
  });

  it("ignores a run too short to mean anything", () => {
    expect(sharedRun("the Buyer may", ["the Seller may"])).toBeNull();
  });

  it("marks the headline's quote where the pre-registered passage says who objects", () => {
    const quote = data.headline.sessions[0].finding.spans[0].quote;
    const run = sharedRun(
      quote,
      data.headline.decisivePassages.map((p) => p.quote),
    );
    expect(run).not.toBeNull();
    expect(quote.slice(run!.start, run!.end)).toMatch(/^the Stockholders. Representative notifies Buyer/);
  });
});

describe("charDiff: what a browser can check about a quote and the text at its offsets", () => {
  it("reports no difference for identical strings", () => {
    const diff = charDiff("abc", "abc");
    expect(diff.same).toBe(true);
    expect(diff.left.every((c) => !c.changed)).toBe(true);
  });

  it("marks only the characters that differ", () => {
    const diff = charDiff("Buyer’s delivery", "Buyer's delivery");
    expect(diff.same).toBe(false);
    expect(diff.left.filter((c) => c.changed).map((c) => c.text)).toEqual(["’"]);
    expect(diff.right.filter((c) => c.changed).map((c) => c.text)).toEqual(["'"]);
  });

  it("finds the headline's quote and its text to hold the same words, apart from punctuation", () => {
    const span = data.headline.sessions[0].finding.spans[0];
    const text = data.headline.sections[span.sectionId].text.slice(span.start, span.end);
    expect(wordsOf(text)).toEqual(wordsOf(span.quote));
    const diff = charDiff(text, span.quote);
    expect(diff.left.filter((c) => c.changed).every((c) => /[^\p{L}\p{N}]/u.test(c.text))).toBe(true);
  });
});

describe("partyCheckScore: the numbers the rejected fix is judged by, counted from the verdicts", () => {
  it("counts per set and session", () => {
    expect(partyCheckScore(data.rejectedFix.rows, "diagnostic", "s1")).toEqual({ caught: 4, wrong: 6, lowered: 0, correct: 13 });
    expect(partyCheckScore(data.rejectedFix.rows, "unseen", "v2")).toEqual({ caught: 0, wrong: 4, lowered: 0, correct: 16 });
  });
});

describe("whyMissed", () => {
  it("says what the check saw, from the verdict's own fields", () => {
    const q1 = data.rejectedFix.rows.find((r) => r.case === "Q-1" && r.session === "v1")!;
    expect(whyMissed(q1)).toBe("It read Buyer as acting in the answer, and Buyer as acting in the quote too, so the two agreed.");
    const none = { ...q1, why: "no_actor_in_answer", actingInAnswer: [] };
    expect(whyMissed(none)).toBe("It found no party of the opening acting in the answer, so it had nothing to compare.");
  });
});
