import type { RunDetailView, RunSummary } from "@/lib/types";

/** A run's record in the shape the first screen's receipt reads. */
function summaryOf(run: RunDetailView): RunSummary {
  return {
    id: run.id,
    question: run.question,
    stage: run.stage,
    shared: run.shared,
    model: run.model,
    promptVersion: run.promptVersion,
    promptHash: run.promptHash,
    latencyMs: run.latencyMs,
    reason: run.reason,
    findings: run.findings.length,
    hasGuidance: run.hasGuidance,
    documentId: run.documentId,
    documentName: run.documentName,
    createdAt: run.createdAt,
  };
}

/**
 * The run the first screen shows as "a finished review". A configured proof run (NEXT_PUBLIC_PROOF_RUN) is that run or
 * nothing: it is read by id, because the runs list holds the newest 200 and an open site pushes it out within a day, and
 * the story told beside it (the quote found in another section, the days compared) is true of that run only. Release
 * review, 2026-10-08: the fallback showed another visitor's contract under that story. Without a configured run (a
 * laptop, a sandbox), the latest finished run with findings.
 */
export async function chooseProof(
  configured: string,
  list: () => Promise<RunSummary[]>,
  read: (id: string) => Promise<RunDetailView>,
): Promise<RunSummary | null> {
  if (configured) {
    try {
      const run = await read(configured);
      return run.stage === "complete" && run.findings.length > 0 ? summaryOf(run) : null;
    } catch {
      return null;
    }
  }
  const rows = await list();
  return rows.find((r) => r.stage === "complete" && r.findings > 0) ?? null;
}
