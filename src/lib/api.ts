/** The backend as the interface sees it. Every function throws an Error with a readable message. */

import type {
  AccessView,
  ModelWake,
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
  ContractStateView,
  MemoRecord,
  ReviewIn,
  RunDetailView,
  RunExplanationView,
  RunStage,
  RunSummary,
  RunView,
  TrustDiffView,
} from "./types";

export type { GuidanceRecord, Health, MemoRecord } from "./types";

/**
 * Where the interface finds the API. A production build reaches it on its own origin (relative URLs, behind a proxy that
 * sends /api to the API) unless the build names one; a development build keeps the API's local port. Release review,
 * 2026-10-08: the live build was made without NEXT_PUBLIC_API_URL and sent every remote browser to its own loopback.
 */
export function apiBase(configured: string | undefined, production: boolean): string {
  const base = configured ?? (production ? "" : "http://127.0.0.1:8000");
  return base.replace(/\/$/, "");
}

export const API_URL = apiBase(process.env.NEXT_PUBLIC_API_URL, process.env.NODE_ENV === "production");

/** The one place a thrown error becomes a sentence for the interface. */
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** A request the API answered with an error: its sentence, and the status, so a caller can tell a conflict from a failure. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** The API refused the request because the record changed since it was read (409). */
export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
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
  // An empty base is this site's own origin: the deployment that serves the page also serves the API, behind its gate.
  const base = apiUrl ? `The workbench API at ${apiUrl} is not reachable.` : "The workbench API on this site is not reachable.";
  return !apiUrl || apiUrl.startsWith("https://")
    ? `${base} If this page has been open for a long time, your sign-in may have expired: reload the page.`
    : base;
}

/** A record id as the API issues them (models.new_id, within the 32 characters of its column): letters, digits, _ and -. */
const RECORD_ID = /^[A-Za-z0-9_-]{1,32}$/;

/** A value that is not a record id where one was expected: from a damaged or crafted link, never from the API. */
export class RecordIdError extends Error {
  readonly value: string;

  constructor(value: string) {
    super("This link does not name a record: it is damaged, or it was not made by Verity.");
    this.name = "RecordIdError";
    this.value = value;
  }
}

/**
 * The one way a path is built from ids, as a template tag: route`/api/runs/${id}/detail`. Each id must be a record id,
 * and is encoded besides. Whatever the address carries, an id names one record and never chooses a route: ids from
 * ?run and ?document were pasted in raw, so "R/evidence-pack?" or "../runs/R/evidence-pack?" made the reader's own
 * browser build a pack and spend a pack download (stress test, 2026-10-30). Encoding alone would not have done: ".."
 * and "%2e%2e" are dot segments to a URL.
 */
export function route(parts: TemplateStringsArray, ...ids: string[]): string {
  return parts.reduce((path, part, i) => `${path}${encodeURIComponent(recordId(ids[i - 1]))}${part}`);
}

/** The value, when it is a record id; otherwise a RecordIdError. For an id that travels in a body, not a path. */
export function recordId(value: string): string {
  if (typeof value !== "string" || !RECORD_ID.test(value)) throw new RecordIdError(String(value));
  return value;
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
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("json")) {
    // A sign-in page in place of data: the session in front of the API has expired. Anything else that is not data (a
    // file) is not blamed on the sign-in: a crafted link that reached the pack route was told the sign-in had expired.
    if (type.includes("html") || !type)
      throw new Error("The workbench API answered with a page instead of data; your sign-in may have expired. Reload the page.");
    throw new Error(`The workbench API answered with ${type.split(";")[0].trim()}, not data. Reload the page.`);
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
/** A public demo: a browser with no session is handed one of its own, in a workspace no one else can read. */
export function visit(): Promise<AccessView> {
  return request<AccessView>("/api/access/visit", { method: "POST" });
}

/** Ask the API to wake a hosted model that sleeps when idle, before the question (backend api/model.py). Never waits. */
export function wakeModel(): Promise<ModelWake> {
  return request<ModelWake>("/api/model/wake", { method: "POST" });
}

/**
 * Exchange an invite for a session. The API refuses (409) an invite for another reader while this browser holds a working
 * session, unless the person chose to switch: `replace` says they did (backend api/access.enter).
 */
export function enterWithInvite(invite: string, { replace = false }: { replace?: boolean } = {}): Promise<AccessView> {
  const path = replace ? "/api/access/session?replace=true" : "/api/access/session";
  return request<AccessView>(path, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ invite }) });
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
export async function recordSupersedes(documentId: string, previousDocumentId: string): Promise<DocumentVersionView> {
  return request<DocumentVersionView>(route`/api/documents/${documentId}/supersedes`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ previousDocumentId: recordId(previousDocumentId) }),
  });
}

/** What a later version of the document does to a run's findings. The run is not changed by asking. */
export async function getRunTrustDiff(runId: string, documentId: string): Promise<TrustDiffView> {
  return request<TrustDiffView>(route`/api/runs/${runId}/trust/diff?documentId=${documentId}`);
}

export function listDocuments(): Promise<DocumentSummary[]> {
  return request<DocumentSummary[]>("/api/documents");
}

export async function getDocument(id: string): Promise<DocumentView> {
  return request<DocumentView>(route`/api/documents/${id}`);
}

export function createGuidance(text: string): Promise<GuidanceRecord> {
  return request<GuidanceRecord>("/api/guidance", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ text }),
  });
}

export async function getGuidance(id: string): Promise<GuidanceRecord> {
  return request<GuidanceRecord>(route`/api/guidance/${id}`);
}

export function createRun(input: { documentId: string; guidanceId: string | null; question: string }): Promise<RunView> {
  return request<RunView>("/api/runs", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  });
}

export async function getRun(id: string): Promise<RunView> {
  return request<RunView>(route`/api/runs/${id}`);
}

export function listRuns(): Promise<RunSummary[]> {
  return request<RunSummary[]>("/api/runs");
}

export async function getRunDetail(id: string): Promise<RunDetailView> {
  return request<RunDetailView>(route`/api/runs/${id}/detail`);
}

/** Why this answer: the run explained from its record, assembled by the API; the interface renders it and decides nothing. */
export async function getRunExplanation(id: string): Promise<RunExplanationView> {
  return request<RunExplanationView>(route`/api/runs/${id}/explanation`);
}

export async function listFindings(documentId?: string): Promise<FindingRecord[]> {
  return request<FindingRecord[]>(documentId ? route`/api/findings?documentId=${documentId}` : "/api/findings");
}

export function getExperiments(): Promise<ExperimentsView> {
  return request<ExperimentsView>("/api/engineering/experiments");
}

/** The public artifact is a static site: its record is a file beside the page, written from the committed experiment
 * record by backend/scripts/export_state.py through the same loader the API uses. */
export const STATE_RECORD_FILE = "/contract-state.json";

export async function getContractState(): Promise<ContractStateView> {
  if (process.env.NEXT_PUBLIC_EXPORT !== "state") return request<ContractStateView>("/api/engineering/contract-state");
  let response: Response;
  try {
    response = await fetch(STATE_RECORD_FILE);
  } catch {
    throw new Error("The recorded experiment could not be loaded.");
  }
  if (!response.ok) throw new Error(`The recorded experiment could not be loaded (${response.status}).`);
  return (await response.json()) as ContractStateView;
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

export async function getBatch(id: string): Promise<BatchView> {
  return request<BatchView>(route`/api/batches/${id}`);
}

/** Record a person's decision on a finding; `cleared` undoes. The API decides whether it changed anything. */
export async function reviewFinding(findingId: string, body: ReviewIn): Promise<FindingReviewOut> {
  return request<FindingReviewOut>(route`/api/findings/${findingId}/review`, {
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

/**
 * A file the API sends as an attachment (an evidence pack), read here so that a refusal is shown on the page instead of
 * replacing it, and saved under the name the API gave it (the fallback when the header cannot be read cross-origin).
 */
export async function attachment(path: string, fallbackName: string): Promise<{ blob: Blob; name: string }> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { credentials: "include" });
  } catch {
    throw new Error(unreachable(API_URL));
  }
  if (response.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event(ACCESS_REQUIRED_EVENT));
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  const named = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "");
  return { blob: await response.blob(), name: named?.[1] ?? fallbackName };
}

export function absolute(url: string): string {
  return url.startsWith("http") ? url : `${API_URL}${url}`;
}

const POLL_FAILURES_BEFORE_GIVING_UP = 5;
// A poll every 3 s while the run moves; each poll that finds nothing new doubles the wait, up to 12 s. A run queued
// behind others for minutes was asked for its whole record every 3 s by every page that followed it (audit, 2026-10-19).
export const POLL_MS = 3000;
export const POLL_MAX_MS = 12000;

/**
 * Follow a run's stages. Uses the SSE stream, and falls back to polling if the stream drops; polling
 * retries a few times before it reports, because the run's record outlives any one request, and waits while the
 * page is hidden: the run goes on without it, and the page asks again when it is shown.
 * `onDone` receives the final run once, after the terminal stage. `onAhead` receives how many runs are ahead of
 * this one on the model, as the stream or the record says it. Once the returned function is called, none of the
 * callbacks is called again, whatever was on its way.
 */
export function followRun(
  id: string,
  onStage: (stage: RunStage, detail?: string | null) => void,
  onDone: (run: RunView) => void,
  onError: (message: string) => void,
  onAhead?: (ahead: number | null) => void,
): () => void {
  // Two different facts. `finished`: the stream has ended, and the record is being read. `cancelled`: whoever followed
  // the run wants nothing more of it. They were one flag, so stopping a follower whose record read was already on its
  // way changed nothing, and the record of the run left behind was handed over after the reader had opened another
  // contract, and shown beside it (stress test, 2026-10-30). Every callback below is called only while not cancelled.
  let finished = false;
  let cancelled = false;
  let source: EventSource | null = null;
  let pollTimer: number | null = null;
  let failures = 0; // consecutive poll failures; the record is truth, so a blip is retried before anyone is told
  let delay = POLL_MS;
  let seen = "";

  const onShown = () => {
    if (document.visibilityState !== "visible") return;
    document.removeEventListener("visibilitychange", onShown);
    void poll();
  };

  const stopPolling = () => {
    if (pollTimer) window.clearTimeout(pollTimer);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onShown);
  };

  const finish = async () => {
    if (finished) return;
    finished = true;
    source?.close();
    stopPolling();
    try {
      const run = await getRun(id);
      if (!cancelled) onDone(run);
    } catch (error) {
      if (!cancelled) onError(error instanceof Error ? error.message : String(error));
    }
  };

  const next = (wait: number) => {
    pollTimer = window.setTimeout(() => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") document.addEventListener("visibilitychange", onShown);
      else void poll();
    }, wait);
  };

  const poll = async () => {
    if (finished) return;
    try {
      const run = await getRunDetail(id);
      if (finished || cancelled) return; // stopped while the record was on its way: it is no longer this page's to show
      for (const row of run.stages) onStage(row.stage, row.detail);
      onStage(run.stage);
      onAhead?.(run.ahead ?? null);
      if (run.stage === "complete" || run.stage === "unresolved" || run.stage === "failed") {
        await finish();
        return;
      }
      const now = `${run.stages.length}:${run.stage}:${run.ahead ?? ""}`;
      delay = now === seen ? Math.min(POLL_MAX_MS, delay * 2) : POLL_MS;
      seen = now;
    } catch (error) {
      if (cancelled) return;
      failures += 1;
      if (failures >= POLL_FAILURES_BEFORE_GIVING_UP) {
        onError(error instanceof Error ? error.message : String(error));
        return;
      }
      next(POLL_MS);
      return;
    }
    failures = 0;
    next(delay);
  };

  if (typeof EventSource !== "undefined") {
    source = new EventSource(`${API_URL}${route`/api/runs/${id}/events`}`, { withCredentials: true });
    source.addEventListener("stage", (event) => {
      if (cancelled) return;
      const data = JSON.parse((event as MessageEvent).data) as {
        stage: RunStage;
        detail?: string | null;
        final?: boolean;
      };
      onStage(data.stage, data.detail);
      if (data.final) void finish();
    });
    source.addEventListener("queue", (event) => {
      if (cancelled) return;
      onAhead?.((JSON.parse((event as MessageEvent).data) as { ahead: number | null }).ahead);
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
    cancelled = true;
    finished = true;
    source?.close();
    stopPolling();
  };
}
