import { describe, expect, it } from "vitest";

import { charDiff, definedParties, firstOccurrences, fixScore, sharedRun, whyMissed, wordsOf } from "./record";
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

describe("whyMissed", () => {
  it("says what the check saw, from the verdict's own fields", () => {
    const q1 = data.rejectedFix.rows.find((r) => r.case === "Q-1" && r.session === "v1")!;
    expect(whyMissed(q1)).toBe("It read Buyer as acting in the answer, and Buyer as acting in the quote too, so the two agreed.");
    const none = { ...q1, why: "no_actor_in_answer", actingInAnswer: [] };
    expect(whyMissed(none)).toBe("It found no party of the opening acting in the answer, so it had nothing to compare.");
  });
});

describe("fixScore: the rejected check counted in questions and in findings", () => {
  it("counts the questions caught in every session apart from the findings, from the record's rows", () => {
    const built = fixScore(data.rejectedFix.rows, "diagnostic");
    const unseen = fixScore(data.rejectedFix.rows, "unseen");
    expect([built.caughtEverySession, built.questions, built.caughtFindings, built.findings]).toEqual([4, 5, 8, 12]);
    expect([unseen.caughtEverySession, unseen.caughtAnySession, unseen.questions, unseen.caughtFindings, unseen.findings]).toEqual([0, 0, 4, 0, 8]);
    expect([built.loweredFindings, built.correctFindings, unseen.loweredFindings, unseen.correctFindings]).toEqual([0, 26, 0, 32]);
  });

  it("a question caught in one session only is caught in some sessions, not every one", () => {
    const rows = [
      { set: "unseen", case: "X", session: "v1", label: "wrong_party", flagged: true },
      { set: "unseen", case: "X", session: "v2", label: "wrong_party", flagged: false },
    ] as unknown as BreakRecord["rejectedFix"]["rows"];
    expect(fixScore(rows, "unseen")).toMatchObject({ questions: 1, caughtEverySession: 0, caughtAnySession: 1, findings: 2, caughtFindings: 1 });
  });
});

describe("definedParties: who is who, from the passages the expected answer cites outside the quoted clause", () => {
  it("reads Buyer and the Stockholders' Representative from the agreement's opening, not from the clause", () => {
    const headline = data.headline;
    const parties = definedParties(headline, headline.sessions[0].finding.spans[0].sectionId);
    expect(parties.map((p) => [p.term, p.name])).toEqual([
      ["Buyer", "Axogen"],
      ["Stockholders’ Representative", "Michelle Jarrard"],
    ]);
    expect(parties.every((p) => headline.decisivePassages.some((d) => d.quote === p.definition))).toBe(true);
  });

  it("names no party for a passage without a defined term", () => {
    const c = { ...data.headline, decisivePassages: [{ sectionId: "elsewhere", heading: "H", quote: "Buyer shall cause to be prepared" }] };
    expect(definedParties(c, "cited")).toEqual([]);
  });
});

describe("firstOccurrences: where each phrase first appears, without overlaps", () => {
  it("finds each phrase once, in text order", () => {
    expect(
      firstOccurrences("the Representative notifies Buyer; Buyer pays", [
        { phrase: "Buyer", kind: 0 },
        { phrase: "Representative", kind: 1 },
      ]),
    ).toEqual([
      { start: 4, end: 18, kind: 1 },
      { start: 28, end: 33, kind: 0 },
    ]);
  });

  it("drops a phrase that is not there, and one that overlaps an earlier find", () => {
    expect(
      firstOccurrences("Stockholders’ Representative", [
        { phrase: "Representative", kind: 1 },
        { phrase: "Stockholders’ Representative", kind: 0 },
        { phrase: "Axogen", kind: 2 },
      ]),
    ).toEqual([{ start: 0, end: 28, kind: 0 }]);
  });

  it("keeps no box overlapping a kept one, even past a dropped one (review of e239ea5)", () => {
    expect(
      firstOccurrences("abcdefgh", [
        { phrase: "abcdefg", kind: 0 },
        { phrase: "bc", kind: 1 },
        { phrase: "de", kind: 2 },
      ]),
    ).toEqual([{ start: 0, end: 7, kind: 0 }]);
    expect(firstOccurrences("Buyer", [{ phrase: "", kind: 0 }])).toEqual([]);
  });

  it("returns boxes in text order that never overlap and each hold their phrase, for any phrases", () => {
    const text = "the Stockholders’ Representative notifies Buyer; Buyer (Axogen) pays the Representative";
    const words = text.split(/\s+/);
    let seed = 7;
    const next = (n: number) => (seed = (seed * 1103515245 + 12345) % 2147483648) % n;
    for (let trial = 0; trial < 500; trial++) {
      const phrases = Array.from({ length: 1 + next(5) }, (_, kind) => {
        const from = next(words.length);
        return {
          phrase: words
            .slice(from, from + 1 + next(3))
            .join(" ")
            .slice(0, 1 + next(40)),
          kind,
        };
      });
      const boxes = firstOccurrences(text, phrases);
      boxes.forEach((b, i) => {
        expect(text.slice(b.start, b.end)).toBe(phrases[b.kind].phrase);
        if (i > 0) expect(b.start).toBeGreaterThanOrEqual(boxes[i - 1].end);
      });
    }
  });
});
