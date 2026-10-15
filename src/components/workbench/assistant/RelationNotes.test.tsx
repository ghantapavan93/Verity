/**
 * The contract's own replacement and precedence statements beside an answer (runs.relations, policy-v11). The words are
 * code's and come from the record; every end is a passage code located, and opens the document there with the same
 * highlight a quote gets. A statement no shown answer accounts for (a withheld answer grounds none) is still listed for
 * the run, and one an answer already shows is not listed twice.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RelationNoteView, RelationView } from "@/lib/types";

import { RelationNotes, UnclaimedRelations, relationKey, relationSummary } from "./RelationNotes";

afterEach(cleanup);

const REPLACES: RelationView = {
  kind: "replaces",
  statement: {
    sectionId: "amend",
    label: "RECITALS",
    start: 10,
    end: 120,
    text: "clause 3.2 of the Agreement is deleted in its entirety and replaced with the following:",
  },
  target: "3.2",
  replaced: { sectionId: "s3", label: "§3", start: 40, end: 200, text: "3.2 Notice not earlier than 210 days and not later than 150 days before expiry." },
  replacement: {
    sectionId: "amend",
    label: "RECITALS",
    start: 122,
    end: 260,
    text: "3.2 Notice not earlier than 120 days and not later than 45 days before expiry.",
  },
  scope: null,
  effective: "2025-09-18, the Amendment Date",
  parts: [],
};
const PRECEDENCE: RelationView = {
  kind: "precedence",
  statement: {
    sectionId: "s19",
    label: "§19",
    start: 0,
    end: 90,
    text: "19.2 If there is any conflict, (a) these clauses; (b) Schedule 2; and (c) Schedule 1.",
  },
  target: null,
  replaced: null,
  replacement: null,
  scope: null,
  effective: null,
  parts: ["these clauses", "Schedule 2", "Schedule 1"],
};

describe("RelationNotes", () => {
  it("says what the statement means for the answer, and opens both ends where code located them", () => {
    const onJump = vi.fn();
    const note: RelationNoteView = { effect: "replaced", sentence: "code's whole sentence", relation: REPLACES };
    render(<RelationNotes notes={[note]} onJump={onJump} />);
    expect(screen.getByText(/RECITALS replaces clause 3\.2 in full, in effect from 2025-09-18\. The answer quotes the replaced wording/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Original clause 3\.2 · §3/ }));
    expect(onJump).toHaveBeenLastCalledWith("s3", expect.objectContaining({ sectionId: "s3", start: 40, end: 200, verified: true, method: "located" }));
    fireEvent.click(screen.getByRole("button", { name: /Replacement · RECITALS/ }));
    expect(onJump).toHaveBeenLastCalledWith("amend", expect.objectContaining({ start: 122, end: 260 }));
  });

  it("where the document cannot be opened, shows each end and offers no button for it", () => {
    render(<RelationNotes notes={[{ effect: "replaced", sentence: "code's whole sentence", relation: REPLACES }]} full />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByText(/Original clause 3\.2 · §3/)).toBeTruthy();
    expect(screen.getByText(/Replacement · RECITALS/)).toBeTruthy();
  });

  it("shows code's whole sentence where the drawer asks for it", () => {
    render(
      <RelationNotes notes={[{ effect: "precedence", sentence: "code's whole sentence about the ranking", relation: PRECEDENCE }]} full onJump={vi.fn()} />,
    );
    expect(screen.getByText("code's whole sentence about the ranking")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Order of precedence · §19/ })).toBeTruthy();
  });

  it("never says a limited change or a ranking settles the answer", () => {
    const scoped = relationSummary({ effect: "scoped", sentence: "", relation: { ...REPLACES, scope: "for the second Contract Year only" } });
    expect(scoped).toMatch(/only within a stated limit \(for the second Contract Year only\)\. Whether the limit applies here is not settled by code\./);
    expect(relationSummary({ effect: "precedence", sentence: "", relation: PRECEDENCE })).toMatch(/which applies here is not settled by code/);
  });

  it("says a time the question names, or an answer quoting the replacement with the old values, is not settled by code", () => {
    expect(relationSummary({ effect: "dated", sentence: "", relation: REPLACES })).toMatch(/The question names a time; which wording applied then is not settled by code\./);
    expect(relationSummary({ effect: "old_value", sentence: "", relation: REPLACES })).toMatch(/quotes the replacement but states only values of the replaced wording\./);
  });

  it("says only what code saw in the answer: what it quotes and states, never what it uses or rests on", () => {
    const effects: RelationNoteView["effect"][] = ["replaced", "scoped", "precedence", "dated", "old_value", "context"];
    for (const effect of effects) {
      expect(relationSummary({ effect, sentence: "", relation: effect === "precedence" ? PRECEDENCE : REPLACES })).not.toMatch(/\b(uses?|relies|rests?|follows?)\b/);
    }
  });

  it("renders nothing for an answer the contract's statements do not touch", () => {
    const { container } = render(<RelationNotes notes={[]} onJump={vi.fn()} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("RelationNotes: the difference first, the whole text kept", () => {
  // The synthetic amended sample's clause 7.2 and its replacement: the same opening, the notice window changed late.
  const OPENING =
    '7.2 This Agreement renews automatically at the end of the Initial Term and at the end of each Renewal Term for a further term of twelve (12) months (each a "Renewal Term") unless either party gives the other written notice of non-renewal not less than';
  const LONG: RelationView = {
    ...REPLACES,
    target: "7.2",
    replaced: { sectionId: "s7", label: "§7", start: 0, end: 300, text: `${OPENING} ninety (90) days before the end of the then-current Term.` },
    replacement: {
      sectionId: "amend",
      label: "AMENDMENT NO. 1 TO LINEN AND LAUNDRY SERVICES AGREEMENT",
      start: 0,
      end: 400,
      text: `${OPENING} one hundred fifty (150) days, and not more than two hundred ten (210) days, before the end of the then-current Term. A notice of non-renewal given outside that period has no effect.`,
    },
  };
  const row = (name: RegExp) => screen.getByRole("button", { name });

  it("shows on the card the words each side differs in, wherever they sit in the clause", () => {
    render(<RelationNotes notes={[{ effect: "replaced", sentence: "", relation: LONG }]} onJump={vi.fn()} />);
    expect(row(/^Original clause 7\.2/).textContent).toContain("ninety (90)");
    expect(row(/^Replacement/).textContent).toContain("one hundred fifty (150)");
    expect(row(/^Replacement/).textContent).toContain("two hundred ten (210)");
    expect(row(/^Original clause 7\.2/).querySelector("mark")?.textContent).toContain("ninety (90)");
    expect(screen.getByText(/Marked: the words in which the original and the replacement differ/)).toBeTruthy();
  });

  it("keeps both complete texts, qualifications included, where the sheet shows them in full", () => {
    render(<RelationNotes notes={[{ effect: "replaced", sentence: "code's whole sentence", relation: LONG }]} full />);
    expect(screen.getByText(/Replacement · AMENDMENT NO\. 1/).parentElement?.textContent).toContain(LONG.replacement!.text);
    expect(screen.getByText(/Original clause 7\.2 · §7/).parentElement?.textContent).toContain(LONG.replaced!.text);
  });

  it("offers no comparison where the statement gives only one text", () => {
    const deletion = { ...LONG, replacement: null };
    const { container } = render(
      <RelationNotes
        notes={[
          { effect: "replaced", sentence: "", relation: deletion },
          { effect: "precedence", sentence: "", relation: PRECEDENCE },
        ]}
        onJump={vi.fn()}
      />,
    );
    expect(container.querySelectorAll("mark")).toHaveLength(0);
    expect(screen.queryByText(/Marked: the words/)).toBeNull();
  });

  it("does not give the original agreement's wording the concern a replaced answer gets", () => {
    const historical = relationSummary({ effect: "context", sentence: "", relation: LONG });
    const replaced = relationSummary({ effect: "replaced", sentence: "", relation: LONG });
    expect(historical).toMatch(/Context only: code raised no concern/);
    expect(historical).not.toMatch(/not decided|not settled/);
    expect(replaced).toMatch(/Which wording governs is not decided by code\./);
    const scoped = relationSummary({ effect: "scoped", sentence: "", relation: { ...LONG, scope: "for the second Contract Year only" } });
    expect(scoped).toMatch(/only within a stated limit \(for the second Contract Year only\)/);
  });
});

describe("UnclaimedRelations", () => {
  it("lists the run's statements no shown answer accounts for, and only those", () => {
    render(<UnclaimedRelations relations={[REPLACES, PRECEDENCE]} claimed={new Set([relationKey(PRECEDENCE)])} onJump={vi.fn()} />);
    expect(screen.getByText(/The contract's own statements in the sections chosen for this question/)).toBeTruthy();
    expect(screen.getByText("RECITALS replaces clause 3.2 in full, in effect from 2025-09-18.")).toBeTruthy();
    expect(screen.queryByText(/ranks these clauses/)).toBeNull();
  });
});
