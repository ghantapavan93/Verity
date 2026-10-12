/**
 * /break as a visitor uses it: the failure is legible at once, every control does what it says, and the page asks no
 * server anything. Every value asserted here is read from the record, never typed into the test.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { STATUS_SOURCE_LABELS } from "@/lib/types";

import { BreakStory, unseenSummary } from "./BreakStory";
import { definedParties, fixScore } from "./record";
import raw from "./break-record.json";
import { forPage, type BreakRecord } from "./record";

const record = raw as unknown as BreakRecord;
const headline = record.headline;

afterEach(cleanup);

function renderPage() {
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  render(<BreakStory record={forPage(record)} />);
  return fetchSpy;
}

describe("the failure", () => {
  it("shows the question, the passing answer, the verified quote and the AI-assisted verdict", () => {
    renderPage();
    const exhibit = screen.getByRole("figure", { name: /the question, the answer and the quote/i });
    const text = exhibit.textContent ?? "";
    expect(text).toContain(headline.question);
    expect(text).toContain(headline.sessions[0].finding.conclusion);
    expect(text).toContain("status: pass");
    expect(text).toContain(headline.sessions[0].finding.spans[0].quote.slice(0, 60));
    expect(text).toContain("Wrong party");
    expect(text).toContain("AI-assisted adjudication");
    expect(
      within(exhibit)
        .getByText(/Who holds the right\./)
        .closest("li")?.textContent,
    ).toContain("Not checked by the released code (policy-v6)");
  });

  it("says who is who from the recorded definitions, and that the boxes are this page's text search, not a check", () => {
    renderPage();
    const key = screen.getByRole("group", { name: "Who is who in this clause" });
    const parties = definedParties(headline, headline.sessions[0].finding.spans[0].sectionId);
    expect(parties.length).toBe(2);
    for (const p of parties) expect(key.textContent).toContain(p.definition);
    expect(key.textContent).toContain("Boxes drawn by this page, by searching the text for each defined term.");
    expect(key.textContent).toContain("no released code checks it");
    const exhibit = screen.getByRole("figure", { name: /the question, the answer and the quote/i });
    // The model's answer reads out verbatim: a box changes how it looks, not what it says.
    expect(exhibit.textContent).toContain(headline.sessions[0].finding.conclusion);
    // Each defined term is boxed once in the quote.
    const quote = exhibit.querySelector("blockquote") as HTMLElement;
    for (const p of parties) expect(within(quote).getByText(p.term, { selector: "span" })).toBeTruthy();
  });

  it("says the question carried a planted false premise, with the pre-registered answer's own words", () => {
    renderPage();
    const exhibit = screen.getByRole("figure", { name: /the question, the answer and the quote/i });
    expect(headline.family).toBe("false_premise");
    expect(exhibit.textContent).toContain("Planted false premise");
    expect(exhibit.textContent).toContain(
      headline.expectedAnswer
        .split(/(?<=\.)\s+/)
        .slice(0, 2)
        .join(" "),
    );
  });

  it("says what a found quote means, and states the value rule's result only as the tests establish it", () => {
    renderPage();
    const exhibit = (screen.getByRole("figure", { name: /the question, the answer and the quote/i }).textContent ?? "").replace(/\s+/g, " ");
    expect(exhibit).toContain("Found means the words are there. It does not mean they support the answer.");
    expect(exhibit).toContain("run again on this answer by the page's tests, decides it as recorded");
    expect(exhibit).toContain(`recorded under ${String(headline.sessions[0].options.policy_version)}, policy-v6 plus the rejected party check`);
    expect(document.body.textContent).not.toContain("here it found nothing to lower");
  });

  it("links the contract to its SEC filing", () => {
    renderPage();
    const link = screen.getByRole("link", { name: "the filing on SEC EDGAR" });
    expect(link.getAttribute("href")).toBe(headline.source.url);
  });

  it("never calls the adjudication a human's or a lawyer's", () => {
    renderPage();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/lawyer-certified|certified by|human-adjudicated|reviewed by a lawyer/i);
    expect(text).toMatch(/Not a lawyer.s review/);
  });
});

describe("why it matters", () => {
  it("says what acting on the answer would get wrong, from the pre-registered conditions, labelled as a reading", () => {
    // Release trust review, 2026-10-11: the hero showed the wrong party but not what a reader would do with the answer.
    renderPage();
    const block = screen.getByRole("region", { name: "Why it matters" });
    const text = block.textContent ?? "";
    // Which conditions, found in the record by what they say rather than by position, so a re-export in another order
    // cannot swap in the delivery deadline (review of 8037873).
    const condition = (about: RegExp) => headline.requiredConditions.find((c) => about.test(c)) ?? "";
    for (const about of [/objection right belongs/, /final and binding/, /delivery deadline/]) expect(condition(about)).not.toBe("");
    expect(text).toContain(condition(/objection right belongs/));
    expect(text).toContain(condition(/final and binding/));
    expect(text).not.toContain(condition(/delivery deadline/));
    expect(text).toMatch(/Illustrative/);
    expect(text).not.toMatch(/customer|incident occurred|lost|damages/i);
    // A reading of what could happen, not a claim about every reader.
    expect(text).toMatch(/a quick triage may not escalate it/);
    expect(text).not.toMatch(/nothing about it/);
  });
});

describe("the masking note", () => {
  const note = () => screen.getByText(/the hash covers the record as stored/).textContent ?? "";
  const withMasking = (masking: Partial<BreakRecord["masking"]>) =>
    render(<BreakStory record={forPage({ ...record, masking: { ...record.masking, ...masking } })} />);

  it("says what is masked when names are masked and no email address is", () => {
    withMasking({ inInput: 0, names: 3 });
    expect(note()).toMatch(/^The names of its notice contacts and signatories are masked here/);
    expect(note()).not.toMatch(/Email/);
  });

  it("says only email addresses are masked when no name is", () => {
    withMasking({ inInput: 4, names: 0 });
    expect(note()).toMatch(/^Email addresses in the contract's notice clause \(4 places\) are masked here/);
    expect(note()).not.toMatch(/names/);
  });

  it("says nothing is masked when nothing is", () => {
    withMasking({ inInput: 0, names: 0 });
    expect(screen.queryByText(/are masked here/)).toBeNull();
  });
});

describe("the investigation", () => {
  it("moves between the record's steps with the arrow keys", () => {
    renderPage();
    const input = screen.getByRole("tab", { name: /Input/ });
    expect(input.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(input, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: /Retrieved/ }).getAttribute("aria-selected")).toBe("true");
    const slices = screen.getByRole("list", { name: /Sections handed to the model/ });
    expect(within(slices).getAllByRole("button")).toHaveLength(headline.sessions[0].retrieval.length);
  });

  it("says once, in words, who set the status", () => {
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /What code checked/ }));
    const line = screen.getByText(/Who set the status\./).closest("li")?.textContent ?? "";
    expect(line).toBe(`Who set the status. ${STATUS_SOURCE_LABELS[headline.sessions[0].finding.statusSource]}.`);
    expect(line).not.toContain(headline.sessions[0].finding.policy.summary);
  });

  it("shows the exact input and its recorded hash", () => {
    renderPage();
    expect(screen.getByLabelText("The user message").textContent).toBe(headline.input.user);
    expect(document.body.textContent).toContain(headline.input.sha256);
  });

  it("opens a retrieved section with the quote marked at its offsets", () => {
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Retrieved/ }));
    const span = headline.sessions[0].finding.spans[0];
    const section = headline.sections[span.sectionId];
    const paper = screen.getByLabelText(`Section text: ${section.heading}`);
    expect(paper.querySelector("mark")?.textContent).toBe(section.text.slice(span.start, span.end));
  });

  it("checks the quote against the contract in the browser, and says what differs", () => {
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /What code checked/ }));
    fireEvent.click(screen.getByRole("button", { name: "Check it in your browser" }));
    expect(screen.getByText(/^Same \d+ words in the same order\./).textContent).toMatch(/characters differ, all punctuation\.$/);
  });

  it("switches between the two recorded sessions", () => {
    renderPage();
    expect(document.body.textContent).toContain(headline.sessions[0].runId);
    fireEvent.click(within(screen.getByRole("group", { name: "Model session" })).getByRole("button", { name: "Session 2" }));
    expect(document.body.textContent).toContain(headline.sessions[1].runId);
  });
});

describe("the rejected fix", () => {
  const side = (name: string) => (screen.getByRole("region", { name }).textContent ?? "").replace(/\s+/g, " ");

  it("shows both sets side by side, counted in questions first and in findings second", () => {
    renderPage();
    const built = fixScore(record.rejectedFix.rows, "diagnostic");
    const unseen = fixScore(record.rejectedFix.rows, "unseen");
    expect(document.body.textContent).toContain(
      `Built on: ${built.caughtEverySession} of ${built.questions} questions caught. Unseen: ${unseen.caughtEverySession} of ${unseen.questions}.`,
    );
    expect(side("Cases it was built on")).toContain(`${built.caughtEverySession} of ${built.questions} wrong-party questions caught in every session`);
    expect(side("Cases it was built on")).toContain(`${built.caughtFindings} of ${built.findings} wrong-party findings caught across both sessions`);
    expect(side("Cases it was built on")).toContain(`Correct findings it lowered: ${built.loweredFindings} of ${built.correctFindings}`);
    expect(side("Unseen cases")).toContain(`${unseen.caughtEverySession} of ${unseen.questions} wrong-party questions caught in every session`);
    expect(side("Unseen cases")).toContain(`Correct findings it lowered: ${unseen.loweredFindings} of ${unseen.correctFindings}`);
    // Nothing to switch: both sets are on screen.
    expect(screen.queryByRole("button", { name: "Unseen cases" })).toBeNull();
  });

  it("titles the section with the counts, not a claim that it worked", () => {
    renderPage();
    const heading = screen.getByRole("heading", { name: /A check that caught/ }).textContent ?? "";
    expect(heading).toBe("A check that caught 4 of 5 cases it was built on, and missed every new one.");
  });

  it("counts the unseen score in questions, each asked in both sessions, not in findings", () => {
    renderPage();
    const unseen = record.rejectedFix.rows.filter((r) => r.set === "unseen" && r.label === "wrong_party");
    const questions = new Set(unseen.map((r) => r.case)).size;
    expect(unseen.some((r) => r.flagged)).toBe(false);
    expect(side("Unseen cases")).toContain(`It caught none of the ${questions} wrong-party questions, in either session.`);
    expect(side("Unseen cases")).not.toContain(`0 of ${unseen.length} caught`);
  });

  it("explains the unseen misses in cases, each case with one reason", () => {
    renderPage();
    const missed = record.rejectedFix.rows.filter((r) => r.set === "unseen" && r.label === "wrong_party" && !r.flagged);
    const cases = (why?: string) => new Set(missed.filter((r) => why === undefined || r.why === why).map((r) => r.case)).size;
    // One reason per case, or the two counts below would overlap.
    expect(cases("no_actor_in_answer") + cases("actor_also_in_quote")).toBe(cases());
    const why = (screen.getByRole("heading", { name: "Why it did not generalise" }).parentElement?.textContent ?? "").replace(/\s+/g, " ");
    expect(why).toContain(`${cases("no_actor_in_answer")} of ${cases()} missed cases had no party of the opening acting in the answer`);
    expect(why).toContain(`In the other ${cases("actor_also_in_quote")}, the party the answer wrongly names`);
    expect(why).toContain("which is the model's job and a reviewer's to check");
  });

  it("states a partial unseen score in findings and questions alike", () => {
    expect(unseenSummary(0, 8, 4)).toBe("It caught none of the 4 wrong-party questions, in either session.");
    expect(unseenSummary(3, 8, 4)).toBe("It caught 3 of 8 wrong-party findings across both sessions, over 4 questions.");
    expect(unseenSummary(0, 2, 1)).toBe("It missed the one wrong-party question, in both sessions.");
    expect(unseenSummary(1, 2, 1)).toBe("It caught 1 of 2 wrong-party findings across both sessions, over 1 question.");
  });

  it("opens a missed case to say what the check saw", () => {
    renderPage();
    const list = screen.getByRole("list", { name: /Unseen cases: each question and the check's verdict/ });
    const q1 = within(list)
      .getAllByRole("button")
      .find((b) => new RegExp(`^${headline.id}(?![0-9])`).test(b.textContent ?? ""));
    fireEvent.click(q1!);
    expect(list.textContent).toContain("It read Buyer as acting in the answer, and Buyer as acting in the quote too");
  });
});

describe("the counterexample", () => {
  it("shows the correct answer kept in the session whose quote states the figure, and flagged in the other", () => {
    renderPage();
    const group = screen.getByRole("group", { name: "Model session for this question" });
    const card = group.closest("article")!;
    expect(card.textContent).toContain("A correct answer, flagged");
    fireEvent.click(within(group).getByRole("button", { name: "Session 1" }));
    expect(card.textContent).toContain("Kept: its quote states the figure");
    expect(card.textContent).toContain("$1,500,000");
  });
});

describe("your turn", () => {
  it("links to the workbench and warns without claiming detection", () => {
    const fetchSpy = renderPage();
    expect(screen.getByRole("link", { name: "Open the workbench" }).getAttribute("href")).toBe("/");
    const warning = screen.getByRole("complementary", { name: "Before you upload" }).textContent ?? "";
    expect(warning).toMatch(/Do not upload confidential, privileged or personal documents/);
    expect(warning).toMatch(/does not detect sensitive content and does not refuse it/);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
