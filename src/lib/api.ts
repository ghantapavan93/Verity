/** The backend as the interface sees it. Every function throws an Error with a readable message. */

import type {
  AccessView,
  BatchSummary,
  BatchView,
  CitationRecord,
  DocumentSummary,
  DocumentVersionView,
  DocumentView,
  ExperimentsView,
  FamiliesView,
  FindingRecord,
  FindingReviewOut,
  GoldensView,
  GuidanceRecord,
  Health,
  LineageView,
  MemoRecord,
  ReviewIn,
  RunDetailView,
  RunExplanationView,
  RunStage,
  RunSummary,
  RunView,
  TrustDiffView,
  TrustManifestView,
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

/**
 * What a request that failed outright says. Behind an access gate (an https origin) the usual cause is not the
 * network: the gate answers an expired sign-in with a redirect to its own origin, the browser refuses to follow it
 * for a data request, and the request simply fails. Saying only "not reachable" sent the reader looking at the
 * wrong thing (2026-10-02).
 */
export function unreachable(apiUrl: string): string {
  const base = `The workbench API at ${apiUrl} is not reachable.`;
  return apiUrl.startsWith("https://") ? `${base} If this page has been open for a long time, your sign-in may have expired: reload the page.` : base;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

/** Fired on the window when the API refuses a request for want of a session; the access gate listens for it. */
export const ACCESS_REQUIRED_EVENT = "verity:access-required";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    // The session cookie travels with every request. Through the tunnel the API is the page's own origin; on a
    // laptop it is another port, and the API allows credentials from the interface's origins only.
    response = await fetch(`${API_URL}${path}`, { credentials: "include", ...init });
  } catch {
    throw new Error(unreachable(API_URL));
  }
  if (response.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event(ACCESS_REQUIRED_EVENT));
  if (!response.ok) throw new Error(await readError(response));
  if (!(response.headers.get("content-type") ?? "").includes("json")) {
    // A sign-in page in place of data: the session in front of the API has expired.
    throw new Error("The workbench API answered with a page instead of data; your sign-in may have expired. Reload the page.");
  }
  return (await response.json()) as T;
}

export function health(): Promise<Health> {
  return request<Health>("/api/health");
}

/** Whether the API has a gate and whether this browser is through it (the API decides both). */
export function getAccess(): Promise<AccessView> {
  return request<AccessView>("/api/access");
}

/** Exchange an invite, the token or the whole link, for a session cookie. The API answers with who entered. */
export function enterWithInvite(invite: string): Promise<AccessView> {
  return request<AccessView>("/api/access/session", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ invite }) });
}

export function uploadDocument(file: File): Promise<DocumentView> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request<DocumentView>("/api/documents", {
    method: "POST",
    body: form,
  });
}

/** Say that a document is the version after another. The statement is this workspace's own and is never edited. */
export function recordSupersedes(documentId: string, previousDocumentId: string): Promise<DocumentVersionView> {
  return request<DocumentVersionView>(`/api/documents/${documentId}/supersedes`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ previousDocumentId }),
  });
}

/** What each finding of a finished run stands on. Derived from the record by the API; nothing is stored or changed. */
export function getRunTrust(runId: string): Promise<TrustManifestView> {
  return request<TrustManifestView>(`/api/runs/${runId}/trust`);
}

/** What a later version of the document does to a run's findings. The run is not changed by asking. */
export function getRunTrustDiff(runId: string, documentId: string): Promise<TrustDiffView> {
  return request<TrustDiffView>(`/api/runs/${runId}/trust/diff?documentId=${encodeURIComponent(documentId)}`);
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

/** Why this answer: the run explained from its record, assembled by the API; the interface renders it and decides nothing. */
export function getRunExplanation(id: string): Promise<RunExplanationView> {
  return request<RunExplanationView>(`/api/runs/${id}/explanation`);
}

export function listFindings(documentId?: string): Promise<FindingRecord[]> {
  const query = documentId ? `?documentId=${encodeURIComponent(documentId)}` : "";
  return request<FindingRecord[]>(`/api/findings${query}`);
}

export function getExperiments(): Promise<ExperimentsView> {
  return request<ExperimentsView>("/api/engineering/experiments");
}

export function getLineage(): Promise<LineageView> {
  return request<LineageView>("/api/engineering/lineage");
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

const POLL_FAILURES_BEFORE_GIVING_UP = 5;

/**
 * Follow a run's stages. Uses the SSE stream, and falls back to polling if the stream drops; polling
 * retries a few times before it reports, because the run's record outlives any one request.
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
  let failures = 0; // consecutive poll failures; the record is truth, so a blip is retried before anyone is told

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
      failures += 1;
      if (failures >= POLL_FAILURES_BEFORE_GIVING_UP) {
        onError(error instanceof Error ? error.message : String(error));
        return;
      }
      pollTimer = window.setTimeout(poll, 3000);
      return;
    }
    failures = 0;
    pollTimer = window.setTimeout(poll, 3000);
  };

  if (typeof EventSource !== "undefined") {
    source = new EventSource(`${API_URL}/api/runs/${id}/events`, { withCredentials: true });
    source.addEventListener("stage", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as {
        stage: RunStage;
        detail?: string | null;
        final?: boolean;
      };
      onStage(data.stage, data.detail);
      if (data.final) void finish();
    });
    // The server's own `event: error` (an unknown run) carries data; the browser's transport error does not.
    source.addEventListener("error", (event) => {
      if (!(event instanceof MessageEvent) || finished) return;
      finished = true;
      source?.close();
      let detail = "run not found";
      try {
        detail = (JSON.parse(event.data) as { detail?: string }).detail ?? detail;
      } catch {
        // the message is the detail
      }
      onError(detail);
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
