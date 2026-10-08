/**
 * The first screen's "finished review" is the configured proof run or nothing. Release review, 2026-10-08: the runs list
 * holds the newest 200, an open site pushes the proof run out of it within a day, and the fallback then showed another
 * visitor's contract under a story that is true of the proof run only.
 */

import { describe, expect, it, vi } from "vitest";
import type { RunDetailView, RunSummary } from "@/lib/types";
import { chooseProof } from "./proofRun";

function summary(id: string, findings = 2, stage: RunSummary["stage"] = "complete"): RunSummary {
  return {
    id,
    question: `question ${id}`,
    stage,
    shared: true,
    model: "qwen3:8b",
    promptVersion: "answer-v2",
    promptHash: "h",
    latencyMs: 1000,
    reason: null,
    findings,
    hasGuidance: true,
    documentId: "doc",
    documentName: "agreement.docx",
    createdAt: "2026-10-01T00:00:00+00:00",
  } as RunSummary;
}

function detail(id: string): RunDetailView {
  return {
    ...summary(id),
    findings: [{ id: "f1" }, { id: "f2" }],
    withheld: [],
    documentId: "doc",
    documentName: "agreement.docx",
  } as unknown as RunDetailView;
}

describe("chooseProof", () => {
  it("reads a configured proof run by id, though it is no longer in the newest runs", async () => {
    const list = vi.fn(async () => [summary("stranger")]);
    const read = vi.fn(async (id: string) => detail(id));
    const proof = await chooseProof("proof1", list, read);
    expect(proof?.id).toBe("proof1");
    expect(proof?.findings).toBe(2);
    expect(read).toHaveBeenCalledWith("proof1");
    expect(list).not.toHaveBeenCalled(); // the list cannot substitute for the configured run
  });

  it("shows nothing when the configured run cannot be read, never another run in its place", async () => {
    const list = vi.fn(async () => [summary("stranger")]);
    const read = vi.fn(async () => {
      throw new Error("run not found");
    });
    expect(await chooseProof("proof1", list, read)).toBeNull();
    const unfinished = vi.fn(async (id: string) => ({ ...detail(id), stage: "failed" }) as RunDetailView);
    expect(await chooseProof("proof1", list, unfinished)).toBeNull();
  });

  it("counts the findings shown, as the runs list does: a withheld finding is not one with a found quote", async () => {
    const read = vi.fn(
      async (id: string) =>
        ({
          ...detail(id),
          findings: [
            { id: "f1", status: "pass" },
            { id: "f2", status: "unresolved" },
          ],
        }) as unknown as RunDetailView,
    );
    expect((await chooseProof("proof1", vi.fn(), read))?.findings).toBe(1);
    const onlyWithheld = vi.fn(async (id: string) => ({ ...detail(id), findings: [{ id: "f2", status: "unresolved" }] }) as unknown as RunDetailView);
    expect(await chooseProof("proof1", vi.fn(), onlyWithheld)).toBeNull();
  });

  it("control: without a configured run, the latest finished run with findings", async () => {
    const list = vi.fn(async () => [summary("empty", 0), summary("running", 2, "checking"), summary("latest"), summary("older")]);
    const read = vi.fn();
    expect((await chooseProof("", list, read))?.id).toBe("latest");
    expect(read).not.toHaveBeenCalled();
  });
});
