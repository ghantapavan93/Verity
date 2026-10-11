/**
 * /break as a visitor uses it: the failure is legible at once, every control does what it says, and the page asks no
 * server anything. Every value asserted here is read from the record, never typed into the test.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BreakStory } from "./BreakStory";
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
  it("shows its score on the cases it was built on, then on unseen ones", () => {
    renderPage();
    const scores = () => (document.querySelector('[aria-live="polite"]')?.textContent ?? "").replace(/\s+/g, " ");
    expect(scores()).toContain("4 of 6 wrong-party answers caught, session 1");
    fireEvent.click(screen.getByRole("button", { name: "Unseen cases" }));
    expect(scores()).toContain("0 of 4 wrong-party answers caught, session 1");
    expect(scores()).toContain("0 of 32 correct answers lowered");
  });

  it("opens a missed case to say what the check saw", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Unseen cases" }));
    const list = screen.getByRole("list", { name: /Wrong-party answers and the check's verdict/ });
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
