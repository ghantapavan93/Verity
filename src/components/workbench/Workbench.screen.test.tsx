/**
 * The workbench end to end in jsdom: the real api.ts, hooks and components, with only fetch and EventSource faked. The
 * invariant under test is the screen's own: the answer on screen is an answer about the contract on screen, and what is on
 * screen is what the reader asked for last. The stress test of 2026-10-30 put a verified quote from one contract over
 * another, by four paths: the record read after a run's terminal event landing after the reader left; a question typed on
 * the first screen asked of the uploaded contract after the reader pressed Back; a slow open landing over a newer one; and
 * a recorded run's open landing over a contract opened after it. Each is a case below, beside a control that the same
 * flow, left alone, still lands; then a seeded walk over random interleavings of every intent and every answer.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Workbench } from "./Workbench";

class FakeSource {
  static all: FakeSource[] = [];
  closed = false;
  onerror: (() => void) | null = null;
  private listeners: Record<string, ((event: MessageEvent) => void)[]> = {};
  constructor(readonly url: string) {
    FakeSource.all.push(this);
  }
  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(listener);
  }
  removeEventListener() {}
  close() {
    this.closed = true;
  }
  emit(type: string, data: unknown) {
    for (const listener of this.listeners[type] ?? []) listener(new MessageEvent(type, { data: JSON.stringify(data) }));
  }
  get runId(): string {
    return /\/api\/runs\/([^/]+)\/events/.exec(this.url)?.[1] ?? "";
  }
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const settle = (ms = 30) => act(() => sleep(ms));

// ---- the record the fake API serves ------------------------------------------------------------

const TEXT = "Either party may terminate on ninety (90) days' written notice.";

function contract(id: string) {
  return {
    id,
    name: `${id}.txt`,
    sha256: id.padEnd(64, "0"),
    createdAt: "2026-10-30T00:00:00Z",
    pages: null,
    parseMs: 1,
    parserVersion: "v15",
    reused: false,
    trackedChanges: 0,
    hiddenRuns: 0,
    coverage: null,
    sections: [
      { id: `${id}-s1`, number: "1", heading: "Term", text: `This Agreement (${id}) runs for one year.` },
      { id: `${id}-s2`, number: "2", heading: "Termination", text: TEXT },
    ],
  };
}

interface FakeRun {
  id: string;
  documentId: string;
  question: string;
  done: boolean;
}

let runs: Map<string, FakeRun>;
let posts: { documentId: string; question: string }[];

function runRecord(run: FakeRun) {
  const finding = {
    id: `${run.id}-f1`,
    topic: `Answer about ${run.documentId}`,
    status: "needs_review",
    statusSource: "model_hint",
    conclusion: `The contract ${run.documentId} allows termination on 90 days' notice.`,
    spans: [
      {
        sectionId: `${run.documentId}-s2`,
        start: 0,
        end: TEXT.length,
        quote: TEXT,
        verified: true,
        method: "exact",
        matchCount: 1,
        citedSectionLabel: "§2",
        clauseLabel: null,
        sectionLabel: "§2 Termination",
      },
    ],
    guidanceReference: null,
    observed: null,
    required: null,
    suggestedPosition: null,
    relations: [],
    evidenceKind: "passage",
    latestReviewId: 0,
    review: null,
    decidedBy: "model",
  };
  return {
    id: run.id,
    question: run.question,
    stage: run.done ? "complete" : "checking",
    findings: run.done ? [finding] : [],
    withheld: [],
    model: "qwen3:8b",
    promptVersion: "answer-v4",
    promptHash: "h".repeat(64),
    latencyMs: run.done ? 9000 : null,
    note: null,
    error: null,
    reason: null,
    reused: false,
    shared: false,
    hasGuidance: false,
    reviewHead: "",
    guidanceText: null,
    relations: [],
    sectionsRead: 2,
    retrievalMode: "lexical_match",
  };
}

// ---- requests: answered at once, or held until the test lets them through ----------------------------

interface Held {
  key: string;
  release: () => void;
}
let held: Held[];
let holding: (key: string) => boolean;

function answer(method: string, path: string, body: BodyInit | null | undefined): Response {
  if (path === "/api/access") return json({ required: false, entered: true, anonymous: false });
  if (path === "/api/health")
    return json({ ok: true, provider: "replay", model: "m", detail: "", access: "off", modelLocation: "server", modelHost: "", fault: "" });
  if (path === "/api/documents" && method === "POST") return json(contract("docU"), 201);
  if (path === "/api/documents" || path === "/api/findings") return json([]);
  if (path === "/api/runs" && method === "POST") {
    const asked = JSON.parse(String(body)) as { documentId: string; question: string };
    posts.push({ documentId: asked.documentId, question: asked.question });
    const run = { id: `run${posts.length}`, documentId: asked.documentId, question: asked.question, done: false };
    runs.set(run.id, run);
    return json(runRecord(run), 202);
  }
  if (path === "/api/runs") return json([]);
  const doc = /^\/api\/documents\/(doc[XYZU])$/.exec(path); // docQ, and any other, is not in this workspace
  if (doc) return json(contract(doc[1]));
  const run = /^\/api\/runs\/([^/]+)(\/detail)?$/.exec(path);
  if (run && runs.has(run[1])) {
    const record = runs.get(run[1])!;
    return json(run[2] ? { ...runRecord(record), documentId: record.documentId, guidanceId: null, stages: [], ahead: null } : runRecord(record));
  }
  return json({ detail: "not found" }, 404);
}

function route(url: string, init?: RequestInit): Promise<Response> {
  const method = init?.method ?? "GET";
  const path = new URL(url).pathname;
  const key = `${method} ${path}`;
  if (!holding(key)) return Promise.resolve(answer(method, path, init?.body));
  // A held request is answered from the record as it stands when it is let through, as a slow server would.
  return new Promise<Response>((resolve) => held.push({ key, release: () => resolve(answer(method, path, init?.body)) }));
}

async function release(key: string) {
  const index = held.findIndex((h) => h.key === key);
  if (index < 0) throw new Error(`nothing held for ${key}; held: ${held.map((h) => h.key).join(", ")}`);
  const [request] = held.splice(index, 1);
  await act(async () => {
    request.release();
    await sleep(20);
  });
}

/** The run's terminal event on its stream: the follower then reads the record. */
async function finishOnStream(runId: string) {
  runs.get(runId)!.done = true;
  const stream = [...FakeSource.all].reverse().find((s) => s.runId === runId && !s.closed);
  await act(async () => {
    stream?.emit("stage", { stage: "complete", final: true });
    await sleep(10);
  });
}

async function go(search: string) {
  await act(async () => {
    window.history.pushState(null, "", `/${search}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
    await sleep(10);
  });
}

async function upload(container: HTMLElement) {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
  await act(async () => {
    fireEvent.change(input, { target: { files: [new File(["Confidential Information means..."], "docU.txt", { type: "text/plain" })] } });
    await sleep(10);
  });
}

// ---- what is on screen --------------------------------------------------------------------------

function contractOnScreen(): string | null {
  const heading = screen.queryAllByRole("heading", { level: 1 }).find((h) => /^doc[A-Z]\.txt$/.test(h.textContent ?? ""));
  return heading ? heading.textContent!.replace(".txt", "") : null;
}

/** Every contract the answer side speaks of: a question asked of it, or an answer about it. */
function contractsAnswered(): string[] {
  const pane = document.querySelector("[class*='assistantPane']");
  const text = pane?.textContent ?? "";
  return [...new Set([...text.matchAll(/(?:about|of) (doc[A-Z])\b/g)].map((m) => m[1]))];
}

/** The invariant, checked at every step: nothing answered beside a contract is about another one, nor named in the URL. */
function expectPaired(step: string) {
  const shown = contractOnScreen();
  const answered = contractsAnswered();
  expect(
    answered.filter((d) => d !== shown),
    `${step}: answers about another contract beside ${shown}`,
  ).toEqual([]);
  const params = new URLSearchParams(window.location.search);
  const run = params.get("run");
  if (run && params.get("document")) {
    expect(runs.get(run)?.documentId, `${step}: the address pairs ${params.get("document")} with run ${run}`).toBe(params.get("document"));
  }
}

beforeEach(() => {
  runs = new Map([["runA", { id: "runA", documentId: "docX", question: "What notice is needed, of docX?", done: false }]]);
  posts = [];
  held = [];
  holding = () => false;
  FakeSource.all = [];
  vi.stubGlobal("EventSource", FakeSource);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => route(String(url), init)),
  );
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("reduce"),
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    onchange: null,
    dispatchEvent: () => false,
  }));
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    },
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  Element.prototype.scrollTo = function () {} as never;
  Element.prototype.scrollIntoView = function () {} as never;
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function mount(search: string) {
  window.history.replaceState(null, "", `/${search}`);
  const view = render(<Workbench />);
  await settle(60);
  return view;
}

describe("the answer on screen is about the contract on screen", () => {
  it("a run's record that lands after the reader went Back to another contract is not shown beside it", async () => {
    await mount("?run=runA");
    expect(contractOnScreen()).toBe("docX");
    holding = (key) => key === "GET /api/runs/runA";
    await finishOnStream("runA"); // the record read after the terminal event: held
    await go("?document=docY");
    expect(contractOnScreen()).toBe("docY");
    await release("GET /api/runs/runA");
    await settle();
    expect(contractOnScreen()).toBe("docY");
    expect(screen.queryByText("Answer about docX")).toBeNull();
    expect(screen.queryByText(/every passage shown was found in the document text/)).toBeNull();
    expect(new URLSearchParams(window.location.search).get("run")).toBeNull();
  });

  it("control: the record lands on its own contract when the reader stays", async () => {
    await mount("?run=runA");
    holding = (key) => key === "GET /api/runs/runA";
    await finishOnStream("runA");
    await release("GET /api/runs/runA");
    await settle();
    expect(contractOnScreen()).toBe("docX");
    expect(screen.getByText("Answer about docX")).toBeTruthy();
    expect(screen.getByText(/every passage shown was found in the document text/)).toBeTruthy();
  });

  it("a question typed on the first screen is not asked once the reader went Back to another contract", async () => {
    const { container } = await mount("");
    fireEvent.change(await screen.findByLabelText("Your question, asked once the contract is added"), { target: { value: "What is the term of docU?" } });
    await upload(container); // the upload lands; the ready pause starts
    await go("?document=docY"); // inside the pause
    await settle(600);
    expect(contractOnScreen()).toBe("docY");
    expect(posts).toEqual([]);
    // Not shown as asked; the words stay the reader's, unsent, in the composer.
    expect(screen.queryAllByText("What is the term of docU?").filter((el) => el.tagName !== "TEXTAREA")).toEqual([]);
  });

  it("control: the first screen's question is asked of the contract added, once it is open", async () => {
    const { container } = await mount("");
    fireEvent.change(await screen.findByLabelText("Your question, asked once the contract is added"), { target: { value: "What is the term of docU?" } });
    await upload(container);
    await settle(600);
    expect(contractOnScreen()).toBe("docU");
    expect(posts).toEqual([{ documentId: "docU", question: "What is the term of docU?" }]);
  });

  it("an upload that lands after the reader opened another contract does not replace it", async () => {
    const { container } = await mount("");
    holding = (key) => key === "POST /api/documents";
    await upload(container);
    await go("?document=docY");
    expect(contractOnScreen()).toBe("docY");
    await release("POST /api/documents");
    await settle(600);
    expect(contractOnScreen()).toBe("docY");
  });

  it("an open that fails after an upload it came after ends on the first screen, with the reason", async () => {
    const { container } = await mount("");
    holding = (key) => key === "POST /api/documents";
    await upload(container);
    await go("?document=docQ"); // no such contract: 404
    await release("POST /api/documents");
    await settle(600);
    expect(contractOnScreen()).toBeNull();
    expect(screen.getByText(/This contract cannot be opened in this workspace/)).toBeTruthy();
    expect(screen.getByLabelText("Your question, asked once the contract is added")).toBeTruthy();
  });

  it("a slow open does not replace a contract opened after it", async () => {
    await mount("?document=docX");
    holding = (key) => key === "GET /api/documents/docY";
    await go("?document=docY");
    await go("?document=docZ");
    expect(contractOnScreen()).toBe("docZ");
    await release("GET /api/documents/docY");
    expect(contractOnScreen()).toBe("docZ");
    expect(new URLSearchParams(window.location.search).get("document")).toBe("docZ");
  });

  it("a recorded run's slow open does not replace a contract opened after it", async () => {
    runs.get("runA")!.done = true;
    await mount("?document=docY");
    holding = (key) => key === "GET /api/runs/runA/detail";
    await go("?run=runA");
    await go("?document=docZ");
    expect(contractOnScreen()).toBe("docZ");
    await release("GET /api/runs/runA/detail");
    await settle();
    expect(contractOnScreen()).toBe("docZ");
    expect(screen.queryByText("Answer about docX")).toBeNull();
  });

  it("control: an open nothing came after still lands", async () => {
    await mount("?document=docX");
    holding = (key) => key === "GET /api/documents/docY";
    await go("?document=docY");
    await release("GET /api/documents/docY");
    expect(contractOnScreen()).toBe("docY");
  });
});

/**
 * Random interleavings of what a reader does (open a contract or a recorded run, upload, ask) and of what the API answers
 * (each held request let through in any order, each run's terminal event). After every step, nothing answered beside a
 * contract is about another one, and the address never pairs a contract with another contract's run; once everything has
 * answered, the screen shows what the reader asked for last. Seeded, so a failure names its sequence.
 */
describe("every interleaving of intents and answers", () => {
  function random(seed: number) {
    let state = seed;
    return () => {
      state = (state * 1103515245 + 12345) % 2 ** 31;
      return state / 2 ** 31;
    };
  }

  for (const seed of [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]) {
    it(`seed ${seed}`, async () => {
      const next = random(seed);
      const pick = <T,>(items: readonly T[]): T => items[Math.floor(next() * items.length)];
      runs.set("runB", { id: "runB", documentId: "docY", question: "Which law governs, of docY?", done: true });
      runs.set("runC", { id: "runC", documentId: "docZ", question: "Is there a cap, of docZ?", done: false });
      const { container } = await mount("?document=docX");
      // Everything a step can wait on is held: opens, records, uploads, questions.
      holding = (key) => !/\/api\/(access|health|documents$|findings|runs$)/.test(key) || key.startsWith("POST");
      let last: string | null = "docX";
      const log: string[] = [];
      for (let step = 0; step < 14; step++) {
        const roll = next();
        if (roll < 0.2) {
          const id = pick(["docX", "docY", "docZ"]);
          log.push(`open ${id}`);
          await go(`?document=${id}`);
          last = id;
        } else if (roll < 0.35) {
          const id = pick(["runA", "runB", "runC"]);
          log.push(`open ${id}`);
          await go(`?run=${id}`);
          last = runs.get(id)!.documentId;
        } else if (roll < 0.45) {
          log.push("upload");
          await upload(container);
          last = "docU";
        } else if (roll < 0.55) {
          const send = screen.queryByLabelText("Send") as HTMLButtonElement | null;
          const box = screen.queryByPlaceholderText("Ask a question about this contract");
          const shown = contractOnScreen();
          if (send && box && !send.disabled && shown) {
            log.push(`ask of ${shown}`);
            await act(async () => {
              fireEvent.change(box, { target: { value: `Question ${step} of ${shown}` } });
              fireEvent.click(send);
              await sleep(10);
            });
          }
        } else if (roll < 0.7) {
          const open = [...runs.values()].filter((r) => !r.done && FakeSource.all.some((s) => s.runId === r.id && !s.closed));
          if (open.length) {
            const run = pick(open);
            log.push(`terminal ${run.id}`);
            await finishOnStream(run.id);
          }
        } else if (held.length) {
          const request = pick(held);
          log.push(`answer ${request.key}`);
          await release(request.key);
        }
        expectPaired(`seed ${seed}, after ${log.join(" > ")}`);
      }
      // Everything answers, in the order it was asked.
      holding = () => false;
      while (held.length) {
        const [request] = held.splice(0, 1);
        await act(async () => {
          request.release();
          await sleep(20);
        });
        expectPaired(`seed ${seed}, draining after ${log.join(" > ")}`);
      }
      await settle(600);
      expectPaired(`seed ${seed}, settled after ${log.join(" > ")}`);
      expect(contractOnScreen(), `seed ${seed}: the last intent was ${last} (${log.join(" > ")})`).toBe(last);
    });
  }
});
