/** The backend as the interface sees it. Every function throws an Error with a readable message. */

import type {
  BatchSummary,
  BatchView,
  CitationRecord,
  DocumentSummary,
  DocumentView,
  ExperimentsView,
  FamiliesView,
  FindingRecord,
  FindingReviewOut,
  GoldensView,
  GuidanceRecord,
  Health,
  MemoRecord,
  ReviewIn,
  RunDetailView,
  RunStage,
  RunSummary,
  RunView,
} from "./types";

export type { GuidanceRecord, Health, MemoRecord } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

/** The one place a thrown error becomes a sentence for the interface. */
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg ?? "").join("; ");
  } catch {
    // fall through to the status line
  }
  return `${response.status} ${response.statusText}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new Error(`The workbench API at ${API_URL} is not reachable.`);
  }
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as T;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export function health(): Promise<Health> {
  return request<Health>("/api/health");
}

export function uploadDocument(file: File): Promise<DocumentView> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request<DocumentView>("/api/documents", {
    method: "POST",
    body: form,
  });
}

export function listDocuments(): Promise<DocumentSummary[]> {
  return request<DocumentSummary[]>("/api/documents");
}

export function getDocument(id: string): Promise<DocumentView> {
  return request<DocumentView>(`/api/documents/${id}`);
}

export function createGuidance(text: string): Promise<GuidanceRecord> {
  return request<GuidanceRecord>("/api/guidance", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ text }),
  });
}

export function getGuidance(id: string): Promise<GuidanceRecord> {
  return request<GuidanceRecord>(`/api/guidance/${id}`);
}

export function createRun(input: { documentId: string; guidanceId: string | null; question: string }): Promise<RunView> {
  return request<RunView>("/api/runs", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  });
}

export function getRun(id: string): Promise<RunView> {
  return request<RunView>(`/api/runs/${id}`);
}

export function listRuns(): Promise<RunSummary[]> {
  return request<RunSummary[]>("/api/runs");
}

export function getRunDetail(id: string): Promise<RunDetailView> {
  return request<RunDetailView>(`/api/runs/${id}/detail`);
}

export function listFindings(documentId?: string): Promise<FindingRecord[]> {
  const query = documentId ? `?documentId=${encodeURIComponent(documentId)}` : "";
  return request<FindingRecord[]>(`/api/findings${query}`);
}

export function getExperiments(): Promise<ExperimentsView> {
  return request<ExperimentsView>("/api/engineering/experiments");
}

export function getGoldens(): Promise<GoldensView> {
  return request<GoldensView>("/api/engineering/goldens");
}

export function getCitations(): Promise<CitationRecord> {
  return request<CitationRecord>("/api/engineering/citations");
}

export function getFamilies(): Promise<FamiliesView> {
  return request<FamiliesView>("/api/engineering/families");
}

export function listBatches(): Promise<BatchSummary[]> {
  return request<BatchSummary[]>("/api/batches");
}

export function getBatch(id: string): Promise<BatchView> {
  return request<BatchView>(`/api/batches/${encodeURIComponent(id)}`);
}

/** Record a person's decision on a finding; `cleared` undoes. The API decides whether it changed anything. */
export function reviewFinding(findingId: string, body: ReviewIn): Promise<FindingReviewOut> {
  return request<FindingReviewOut>(`/api/findings/${encodeURIComponent(findingId)}/review`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function createMemo(runId: string): Promise<MemoRecord> {
  return request<MemoRecord>("/api/memos", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ runId }),
  });
}

export function absolute(url: string): string {
  return url.startsWith("http") ? url : `${API_URL}${url}`;
}

/**
 * Follow a run's stages. Uses the SSE stream, and falls back to polling if the stream drops.
 * `onDone` receives the final run once, after the terminal stage.
 */
export function followRun(
  id: string,
  onStage: (stage: RunStage, detail?: string | null) => void,
  onDone: (run: RunView) => void,
  onError: (message: string) => void,
): () => void {
  let finished = false;
  let source: EventSource | null = null;
  let pollTimer: number | null = null;

  const finish = async () => {
    if (finished) return;
    finished = true;
    source?.close();
    if (pollTimer) window.clearTimeout(pollTimer);
    try {
      onDone(await getRun(id));
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error));
    }
  };

  const poll = async () => {
    if (finished) return;
    try {
      const run = await getRunDetail(id);
      for (const row of run.stages) onStage(row.stage, row.detail);
      onStage(run.stage);
      if (run.stage === "complete" || run.stage === "unresolved" || run.stage === "failed") {
        await finish();
        return;
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error));
      return;
    }
    pollTimer = window.setTimeout(poll, 3000);
  };

  if (typeof EventSource !== "undefined") {
    source = new EventSource(`${API_URL}/api/runs/${id}/events`);
    source.addEventListener("stage", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as {
        stage: RunStage;
        detail?: string | null;
        final?: boolean;
      };
      onStage(data.stage, data.detail);
      if (data.final) void finish();
    });
    source.onerror = () => {
      source?.close();
      source = null;
      if (!finished) void poll();
    };
  } else {
    void poll();
  }

  return () => {
    finished = true;
    source?.close();
    if (pollTimer) window.clearTimeout(pollTimer);
  };
}
