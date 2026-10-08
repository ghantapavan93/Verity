/**
 * The story page tells only what the record holds: the funnel, one certificate, one arrival's trace, the predecessor,
 * the failed gate and the scopes, each from the committed record (three of its arrivals, trimmed for the test).
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ContractStateView } from "@/lib/types";

import record from "./__fixtures__/contract-state.json";
import { StateStory } from "./StateStory";

const VIEW = record as unknown as ContractStateView;

beforeEach(() => window.history.replaceState(null, "", "/state"));
afterEach(cleanup);

describe("StateStory", () => {
  it("opens on the funnel: every derived object, the envelope, the plan, the delta, and nothing changed outside", () => {
    render(<StateStory initial={VIEW} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("One contract changes. What doesn’t need to move?");
    const funnel = screen.getByRole("list", { name: "From every derived object to what one arrival changed" });
    expect(within(funnel).getByText("57,121")).toBeTruthy();
    expect(within(funnel).getByText("295")).toBeTruthy();
    expect(within(funnel).getByText("27.3")).toBeTruthy();
    expect(within(funnel).getByText("2.9")).toBeTruthy();
    expect(screen.getByText("0 observed changes outside the envelope.")).toBeTruthy();
  });

  it("shows one real relationship with its support, guard and scope, and what it reads against the predecessor", () => {
    render(<StateStory initial={VIEW} />);
    const cert = screen.getByRole("article", { name: "Derivation certificate" });
    expect(within(cert).getByText("Exactly 1 visible text satisfies this reference.")).toBeTruthy();
    expect(within(cert).getByText(/Reference: Credit Agreement, February 11, 2022/)).toBeTruthy();
    expect(within(cert).getByText(/This edge depends on 11 keys\. The predecessor read 88\./)).toBeTruthy();
    expect(screen.getByText(/Relationship established: AMENDS → Credit Agreement, February 11, 2022/)).toBeTruthy();
    const quote = within(screen.getByRole("article", { name: "Source" })).getByText("Credit Agreement, dated as of February 11, 2022");
    expect(quote.tagName).toBe("MARK");
  });

  it("marks the agreement's name only where its year is the reference's own, never the source's own date", () => {
    const view = structuredClone(VIEW) as unknown as { arrivals: { edge?: { evidence?: string } }[] };
    // A recorded snippet that names the agreement only with the amendment's own date (a 2023 date for a 2022 reference).
    view.arrivals[0].edge = {
      ...view.arrivals[0].edge,
      evidence: "Amendment No. 3 to the Credit Agreement is made as of March 1, 2023, by and among the parties.",
    };
    render(<StateStory initial={view as unknown as ContractStateView} />);
    const source = screen.getByRole("article", { name: "Source" });
    expect(source.querySelector("mark")).toBeNull();
    expect(source.textContent).toContain("made as of March 1, 2023");
  });

  it("traces one recorded arrival, and a chosen arrival is named in the URL", () => {
    render(<StateStory initial={VIEW} />);
    const trace = screen.getByRole("list", { name: "The recorded trace of this arrival" });
    expect(within(trace).getByText("412 objects")).toBeTruthy();
    expect(within(trace).getByText("41 objects")).toBeTruthy();
    expect(within(trace).getByText("3 objects changed")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Recorded arrival"), { target: { value: "1" } });
    expect(window.location.search).toBe("?arrival=2");
    expect(screen.getByText("This arrival established no relationship.")).toBeTruthy();
  });

  it("reads the arrival from a shared URL", () => {
    window.history.replaceState(null, "", "/state?arrival=3");
    render(<StateStory initial={VIEW} />);
    expect((screen.getByLabelText("Recorded arrival") as HTMLSelectElement).value).toBe("2");
  });

  it("compares with the real predecessor and keeps the failed gate", () => {
    render(<StateStory initial={VIEW} />);
    const comparison = screen.getByRole("table", { name: "Certificate-aware engine against the bucket-guard predecessor" });
    expect(within(comparison).getByText("238")).toBeTruthy();
    expect(within(comparison).getByText("874")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "We preregistered 0.85 recall. The system reached 0.836, so this run failed." })).toBeTruthy();
    const gate = screen.getByRole("table", { name: "The preregistered gate on set 4" });
    expect(within(gate).getByText("NOT PASSED")).toBeTruthy();
    expect(within(gate).getAllByText("FAIL")).toHaveLength(1);
    expect(screen.getByText("12 missed relationships")).toBeTruthy();
    expect(screen.getByText(/Timing side channels were not tested\./)).toBeTruthy();
  });

  it("says when the record is not connected and never invents a page", () => {
    render(<StateStory initial={{ available: false, source: null, detail: "contract-state.json not found", evidence: {}, arrivals: [] }} />);
    expect(screen.getByRole("alert").textContent).toContain("The contract-state record is not connected.");
    expect(screen.queryByRole("heading", { level: 1, name: /One contract changes/ })).toBeNull();
  });
});
