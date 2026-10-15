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

describe("UnclaimedRelations", () => {
  it("lists the run's statements no shown answer accounts for, and only those", () => {
    render(<UnclaimedRelations relations={[REPLACES, PRECEDENCE]} claimed={new Set([relationKey(PRECEDENCE)])} onJump={vi.fn()} />);
    expect(screen.getByText(/The contract's own statements in the sections chosen for this question/)).toBeTruthy();
    expect(screen.getByText("RECITALS replaces clause 3.2 in full, in effect from 2025-09-18.")).toBeTruthy();
    expect(screen.queryByText(/ranks these clauses/)).toBeNull();
  });
});
