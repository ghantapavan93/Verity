/**
 * In a public demo the corpus tools (golden set, batch extraction, document families) are the owner's: the API says
 * they do not exist for a visitor, so the Runs surface neither asks for them nor offers a tab that leads to "could not
 * be loaded". An invited reader still sees them.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getExperiments: vi.fn(),
  getContractState: vi.fn(),
  getCitations: vi.fn(),
  listBatches: vi.fn(),
  getFamilies: vi.fn(),
  getGoldens: vi.fn(),
  getRunDetail: vi.fn(),
  getBatch: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ ...api, absolute: (path: string) => path, errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)) }));

import { PublicDemo } from "../access/PublicDemo";
import { runOutcome } from "@/lib/checks";
import { RunsView } from "./RunsView";

const never = () => new Promise(() => undefined);

describe("RunsView in a public demo", () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset();
    api.listRuns.mockResolvedValue([]);
    api.getExperiments.mockImplementation(never);
    api.getContractState.mockImplementation(never);
    api.getCitations.mockImplementation(never);
    api.listBatches.mockResolvedValue([]);
    api.getFamilies.mockImplementation(never);
    api.getGoldens.mockRejectedValue(new Error("not found"));
  });
  afterEach(cleanup);

  it("asks for none of the owner's corpus tools and offers no tab to them", async () => {
    render(
      <PublicDemo.Provider value={{ retentionDays: 7 }}>
        <RunsView notice={null} onOpenRun={vi.fn()} />
      </PublicDemo.Provider>,
    );
    await screen.findByRole("link", { name: "Runs" });
    expect(api.getGoldens).not.toHaveBeenCalled();
    expect(api.listBatches).not.toHaveBeenCalled();
    expect(api.getFamilies).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: "Golden set" })).toBeNull();
    expect(screen.queryByText(/could not be loaded/)).toBeNull();
  });

  it("control: an invited reader still has them", async () => {
    render(<RunsView notice={null} onOpenRun={vi.fn()} />);
    expect(await screen.findByRole("link", { name: "Golden set" })).toBeTruthy();
    expect(api.getGoldens).toHaveBeenCalled();
  });

  it("says the batch record could not be read, rather than that there is no batch", async () => {
    // m7 audit, 2026-10-10: any failure to list batches read "No batch recorded yet", a claim about the record.
    api.listBatches.mockRejectedValue(new Error("The workbench API is not reachable."));
    render(<RunsView notice={null} onOpenRun={vi.fn()} />);
    expect(await screen.findByText(/The batch record could not be read: The workbench API is not reachable\./)).toBeTruthy();
    expect(screen.queryByText("No batch recorded yet.")).toBeNull();
  });
});

describe("runOutcome", () => {
  it("says what a run concluded, not only that it finished", () => {
    expect(runOutcome({ needs_review: 1, missing: 1 }, true)).toBe("1 needs review · 1 not found");
    expect(runOutcome({ pass: 2 }, true)).toBe("2 within guidance (model's view)");
    expect(runOutcome({ pass: 1 }, false)).toBe("1 answered");
    expect(runOutcome({}, true)).toBe("no finding");
    expect(runOutcome(undefined, true)).toBe("no finding");
  });
});

/**
 * The golden report labels each prompt's recording with its reader and rules, and says when none is under today's rules
 * (backend goldens.report, stress test EVL-2): the panel showed that sentence only when there was no recording at all,
 * so a table judged on recordings older than today's rules read as today's.
 */
describe("RunsView, the golden set's recordings", () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset();
    api.listRuns.mockResolvedValue([]);
    for (const fn of [api.getExperiments, api.getContractState, api.getCitations, api.getFamilies]) fn.mockImplementation(never);
    api.listBatches.mockResolvedValue([]);
  });
  afterEach(cleanup);

  const LABEL =
    "Shown for each prompt version, its most complete recording: answer-v4 · qwen3:8b · reader v14 · policy-v15 · k 6. None is under today's rules (policy-v17, verifier v12, reader v16), so a question asked today is answered anew.";

  it("says, beside the table, which recording each prompt is judged on and that it predates today's rules", async () => {
    api.getGoldens.mockResolvedValue({
      available: true,
      detail: LABEL,
      setSha256: "a".repeat(64),
      documentName: "sample.docx",
      documentSha256: "b".repeat(64),
      rules: "Each golden names the passage it expects.",
      categories: {},
      goldens: [],
      prompts: [{ version: "answer-v4", hash: "c".repeat(64), runs: [], passes: 37, recorded: 44, byCategory: [] }],
      compare: null,
    });
    render(<RunsView notice={null} onOpenRun={vi.fn()} />);
    expect(await screen.findByText(/answer-v4: 37 of 44 pass/)).toBeTruthy();
    expect(screen.getByText(LABEL)).toBeTruthy();
  });
});

/**
 * A finished run hashes the record it finished on as the input of its last stage (backend runs.service finished_record,
 * K42): the pack's checker recomputes it. The stage list names that hash for what it is, a record hash; a run finished
 * before 2026-10-30 has none, and nothing is claimed for it.
 */
describe("RunsView, the hash a finished run recorded", () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset();
    for (const fn of [api.getExperiments, api.getContractState, api.getCitations, api.getFamilies, api.getGoldens]) fn.mockImplementation(never);
    api.listBatches.mockResolvedValue([]);
    api.listRuns.mockResolvedValue([
      {
        id: "run1",
        question: "Which law governs?",
        stage: "complete",
        findings: 1,
        outcomes: { pass: 1 },
        documentName: "a.txt",
        createdAt: "2026-10-30T10:00:00Z",
        model: "m",
        hasGuidance: false,
        latencyMs: 1000,
      },
    ]);
  });
  afterEach(cleanup);

  async function stagesOf(last: Record<string, unknown>) {
    api.getRunDetail.mockResolvedValue({
      id: "run1",
      question: "Which law governs?",
      stage: "complete",
      findings: [],
      withheld: [],
      candidates: [],
      options: {},
      stages: [
        { stage: "reading", at: "2026-10-30T10:00:00Z", detail: "4 sections", outputHash: "1".repeat(64) },
        { stage: "complete", at: "2026-10-30T10:00:09Z", detail: null, ...last },
      ],
    });
    render(<RunsView notice={null} onOpenRun={vi.fn()} />);
    (await screen.findByText("Which law governs?")).closest("button")!.click();
    return (await screen.findByText("Stages")).closest("section")!.textContent ?? "";
  }

  it("names the last stage's hash as the record's", async () => {
    const text = await stagesOf({ inputHash: "f".repeat(64) });
    expect(text).toMatch(/record ffffffff/);
  });

  it("control: a run finished before the record was hashed claims no record hash", async () => {
    expect(await stagesOf({ inputHash: null })).not.toMatch(/record/);
  });
});
