/**
 * The first screen says what the API says its door is, and nothing before it has said: it used to read "Private
 * preview … readable through your invite and no other" for the first seconds of an open site (QA review, 2026-10-08).
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Health, RunSummary } from "@/lib/types";

import { AccessModeKnown, PublicDemo } from "../access/PublicDemo";
import { INDEPENDENCE } from "@/lib/independence";
import { Landing } from "./Landing";

// The proof run's lead finding, as its record holds it: the story is told only from the record (m7 audit, 2026-10-10).
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getRun: vi.fn(async () => ({
    findings: [
      {
        id: "f1",
        status: "needs_review",
        statusSource: "computed_days",
        statusReason: "the contract provides 60 calendar days; the guidance requires at least 90 calendar days",
        observed: "60 days' written notice",
        required: "at least 90 days",
        review: null,
        spans: [{ method: "relocated:exact", verified: true }],
      },
    ],
  })),
}));

afterEach(cleanup);
// jsdom has no IntersectionObserver; the landing's scroll reveals ask for one.
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

function renderLanding(
  apiHealth: Health | null,
  accessKnown: boolean,
  proof: RunSummary | null = null,
  proofStory = false,
  uploadError: { name: string | null; reason: string } | null = null,
  onLoadSample: (kind: "standard" | "amended") => void = vi.fn(),
) {
  return render(
    <Landing
      stage="empty"
      processingLabel=""
      pendingName=""
      composerText=""
      setComposerText={vi.fn()}
      onHome={vi.fn()}
      onPickFile={vi.fn()}
      onLoadSample={onLoadSample}
      proof={proof}
      proofStory={proofStory}
      onOpenProof={vi.fn()}
      uploadError={uploadError}
      apiHealth={apiHealth}
      accessKnown={accessKnown}
      recent={[]}
      onOpenDocument={vi.fn()}
      onAllDocuments={vi.fn()}
      viewError={null}
      reduceMotion
    />,
  );
}

const health = (access: Health["access"]): Health => ({ ok: true, provider: "ollama", model: "qwen3:8b", detail: "", access }) as Health;

describe("Landing: the door", () => {
  it.each([
    ["while the API has not answered", null, false],
    ["when the API could not be asked", { ...health("off"), ok: false }, false],
  ])("claims neither open nor private %s", (_when, apiHealth, known) => {
    renderLanding(apiHealth as Health | null, known as boolean);
    expect(screen.getByText("Preview")).toBeTruthy();
    expect(screen.queryByText(/Private preview|Open preview/)).toBeNull();
    expect(document.body.textContent).not.toMatch(/readable through your invite|anyone with this address/);
  });

  it("says an open site is open", () => {
    renderLanding(health("off"), true);
    expect(screen.getByText("Open preview")).toBeTruthy();
    expect(document.body.textContent).toContain("anyone with this address can open it");
  });

  it.each(["required", "entered"] as const)("says a gated site (%s) is private", (access) => {
    renderLanding(health(access), true);
    expect(screen.getByText("Private preview")).toBeTruthy();
    expect(document.body.textContent).toContain("readable through your invite and no other");
  });
});

describe("Landing: where the model runs", () => {
  const at = (location: Health["modelLocation"], host = ""): Health => ({ ...health("off"), modelLocation: location, modelHost: host }) as Health;

  it("says in its footer that the project is independent and not affiliated with Ivo, whatever the door", () => {
    renderLanding(null, false);
    expect(document.body.textContent).toContain(INDEPENDENCE);
  });

  it("names the hosted model and says what is sent to it", () => {
    renderLanding(at("hosted", "a Modal GPU in the US"), true);
    const text = document.body.textContent ?? "";
    expect(text).toContain("run on a Modal GPU in the US");
    expect(text).toContain("The question, any guidance, the contract's file name and the sections it reads are sent there to be answered.");
    expect(text).not.toMatch(/No contract is sent to a hosted model|does not send the contract anywhere|this machine/);
  });

  it("says a model on the server keeps the contract there", () => {
    renderLanding(at("server"), true);
    const text = document.body.textContent ?? "";
    expect(text).toContain("run on the Verity server. No contract is sent to a hosted model.");
    expect(text).not.toContain("this machine");
  });

  it("hosted, names every handler of the contract: Cloudflare, the server and the model", () => {
    // War room F-06, 2026-10-13: the hosted sentence said "to its model and nowhere else", leaving out the edge and the server.
    renderLanding(at("hosted", "a Modal GPU in the US"), true);
    const text = document.body.textContent ?? "";
    expect(text).toContain("It sends its model nothing beyond the question, guidance, file name and the sections retrieval hands over.");
    // Everything a question sends is listed, the file's name and the guidance included, and the opening sections when
    // retrieval ranks none: "only the sections a question needs" said less than the model receives (counter-review).
    expect(text).toContain("is sent the question, any guidance, the contract's file name and the sections retrieval ranked for the question");
    expect(text).toContain("when it ranks none, the opening six go instead");
    expect(text).not.toMatch(/only the sections/);
    expect(text).toMatch(/reaches the Verity server through Cloudflare, which serves this site and so handles its traffic/);
    expect(text).not.toContain("to its model and nowhere else");
  });

  it("names the path an upload takes, Cloudflare included, and claims no more", () => {
    // Release trust review, 2026-10-11: "It does not send the contract anywhere" left out that HTTPS ends at Cloudflare,
    // which serves the site and so handles its traffic before the tunnel to the server.
    renderLanding(at("server"), true);
    const text = document.body.textContent ?? "";
    expect(text).toContain("It sends the contract to no model provider.");
    expect(text).toMatch(/through Cloudflare, which serves this site and so handles its traffic/);
    expect(text).not.toMatch(/does not send the contract anywhere/);
  });

  it("control: claims no place before the API has said", () => {
    renderLanding(null, false);
    expect(document.body.textContent).not.toMatch(/this machine|No contract is sent|sent there|does not send the contract anywhere/);
  });
});

describe("Landing: the finished review it shows", () => {
  const run = {
    id: "run1",
    question: "Which law governs?",
    stage: "complete",
    shared: false,
    model: "qwen3:8b",
    promptVersion: "answer-v2",
    promptHash: "h",
    latencyMs: 1000,
    reason: null,
    findings: 1,
    hasGuidance: false,
    documentId: "doc1",
    documentName: "agreement.docx",
    createdAt: "2026-10-09T00:00:00+00:00",
  } as RunSummary;

  it("tells the four-step story only of the proof run it was written for, from its record", async () => {
    renderLanding({ ...health("off"), modelLocation: "server", modelHost: "" } as Health, true, run, true);
    expect(await screen.findByText("Code checks the quote, then what it can compare")).toBeTruthy();
    expect(document.body.textContent).toContain("in a different section from the one cited");
    expect(document.body.textContent).toContain("60 days' written notice");
  });

  it("shows another run's receipt without a story that is not its own", () => {
    // Release rehearsal, 2026-10-09: with no proof run configured, the latest run took the story's place, and the story
    // says the quote was found in another section and the days were compared, true only of the proof run.
    renderLanding({ ...health("off"), modelLocation: "server", modelHost: "" } as Health, true, run, false);
    expect(document.body.textContent).toContain("Which law governs?");
    expect(document.body.textContent).not.toContain("Code checks the quote, then what it can compare");
  });
});

describe("Landing: the way to the research", () => {
  it("links the recorded research and the source from the first screen", () => {
    renderLanding(health("entered"), true);
    const links = screen.getByRole("navigation", { name: "Elsewhere" });
    expect(links.querySelector('a[href="/state"]')?.textContent).toBe("Research");
    expect(links.querySelector('a[href="https://github.com/ghantapavan93/Verity"]')?.textContent).toBe("Source");
  });

  it("offers the recorded failure, and claims no verification of legal meaning", () => {
    renderLanding(health("entered"), true);
    const links = screen.getByRole("navigation", { name: "Elsewhere" });
    expect(links.querySelector('a[href="/break"]')?.textContent).toBe("Break it");
    expect(screen.getByRole("link", { name: /passed every check and still gave a right to the wrong party/ }).getAttribute("href")).toBe("/break");
    expect(document.body.textContent).not.toMatch(/verifies (the )?(legal )?meaning|verified interpretation|proves the answer/i);
  });
});

describe("Landing: a public demo", () => {
  it("says it is a public demo, what to upload, and when what is added is deleted", () => {
    render(
      <PublicDemo.Provider value={{ retentionDays: 7 }}>
        <Landing
          stage="empty"
          processingLabel=""
          pendingName=""
          composerText=""
          setComposerText={vi.fn()}
          onHome={vi.fn()}
          onPickFile={vi.fn()}
          onLoadSample={vi.fn()}
          proof={null}
          proofStory={false}
          onOpenProof={vi.fn()}
          uploadError={null}
          apiHealth={health("entered")}
          accessKnown
          recent={[]}
          onOpenDocument={vi.fn()}
          onAllDocuments={vi.fn()}
          viewError={null}
          reduceMotion
        />
      </PublicDemo.Provider>,
    );
    expect(screen.getByText("Public demo")).toBeTruthy();
    expect(screen.queryByText("Private preview")).toBeNull();
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/public, synthetic or non-sensitive/);
    expect(text).toMatch(/deleted automatically 7 days after your first visit/);
    expect(text).toMatch(/[Cc]learing (your )?cookies/);
    expect(text).not.toMatch(/invite/i);
    // What deleted covers, and where to check it. Review of 8037873: the database overwrites what its rows held, but a
    // removed file is not overwritten and a copy made by hand is not the code's to delete, so neither is promised.
    expect(text).toMatch(/its rows and files are removed, and the database overwrites the text the rows held/);
    expect(text).not.toMatch(/bytes on disk|backup|no copy/i);
    const tests = [...document.querySelectorAll("a")].map((a) => a.getAttribute("href") ?? "");
    expect(tests).toContain("https://github.com/ghantapavan93/Verity/blob/main/backend/tests/test_anonymous.py");
    expect(tests).toContain("https://github.com/ghantapavan93/Verity/blob/main/backend/tests/test_retention.py");
  });
});

describe("Landing: a file that could not be added", () => {
  // Release readiness, 2026-10-10: the refusal was printed below the demo notice, under the fold on a phone, without
  // the file's name, starting mid-sentence ("the PDF has no text layer…").
  it("names the file and says why, directly under the drop zone", () => {
    renderLanding(health("entered"), true, null, false, { name: "scan.pdf", reason: "the PDF has no text layer on any page" });
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toBe("scan.pdf was not added: the PDF has no text layer on any page");
    const sample = screen.getByText(/Or open a real standard agreement/);
    expect(alert.compareDocumentPosition(sample) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("control: a refusal with no file to name says only why", () => {
    renderLanding(health("entered"), true, null, false, { name: null, reason: "The sample agreement is missing from this build." });
    expect(screen.getByRole("alert").textContent).toBe("The sample agreement is missing from this build.");
  });
});

describe("Landing: the samples", () => {
  it("offers the real standard agreement and a synthetic amended one, each loading its own", () => {
    const load = vi.fn();
    renderLanding(health("off"), true, null, false, null, load);
    fireEvent.click(screen.getByRole("button", { name: "try a sample agreement" }));
    fireEvent.click(screen.getByRole("button", { name: /Try the amendment challenge/ }));
    expect(load.mock.calls).toEqual([["standard"], ["amended"]]);
  });
});

describe("Landing: when the workbench cannot be reached", () => {
  it("says the workbench is unreachable in a sentence, and offers nothing that would fail", () => {
    renderLanding({ ok: false, provider: "", model: "", detail: "The workbench API answered 502", access: "off" } as Health, false);
    expect(screen.getByText(/The workbench is not reachable right now/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Model offline: /);
    expect((screen.getByRole("button", { name: "Add a contract" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "try a sample agreement" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Try the amendment challenge/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("a store that cannot take a write is not called a model outage, and says adding or asking may fail", () => {
    renderLanding({ ok: false, provider: "ollama", model: "qwen3:8b", detail: "the store is read-only", access: "entered", fault: "store" } as Health, true);
    expect(screen.getByText(/storage reports a problem \(the store is read-only\), so adding a contract or asking a question may fail/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/The model is offline/);
  });

  it("control: a reachable workbench whose model is offline still reads documents", () => {
    renderLanding({ ok: false, provider: "ollama", model: "qwen3:8b", detail: "Ollama not reachable", access: "entered", fault: "model" } as Health, true);
    expect(screen.getByText(/The model is offline/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Add a contract" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("Landing: how long a run is kept", () => {
  it("in a public demo, says the runs go with the workspace after its days, never that every run is kept", () => {
    // War room F-18, 2026-10-13: the footer said "Every run is kept" on a site that deletes every run after seven days.
    render(
      <PublicDemo.Provider value={{ retentionDays: 7 }}>
        <Landing
          stage="empty"
          processingLabel=""
          pendingName=""
          composerText=""
          setComposerText={vi.fn()}
          onHome={vi.fn()}
          onPickFile={vi.fn()}
          onLoadSample={vi.fn()}
          proof={null}
          proofStory={false}
          onOpenProof={vi.fn()}
          uploadError={null}
          apiHealth={health("off")}
          accessKnown
          recent={[]}
          onOpenDocument={vi.fn()}
          onAllDocuments={vi.fn()}
          viewError={null}
          reduceMotion
        />
      </PublicDemo.Provider>,
    );
    const text = document.body.textContent ?? "";
    expect(text).toContain("until this browser's workspace is deleted, 7 days after its first visit");
    expect(text).not.toContain("Every run is kept: what the model saw");
    expect(text).not.toMatch(/kept for 7 days/);
  });

  it("control: by invitation, every run is kept", () => {
    renderLanding(health("entered"), true);
    expect(document.body.textContent).toContain("Every run is kept: what the model saw");
  });

  it("claims no door when the API could not say which it is, though its health answered", () => {
    // Counter-review, 2026-10-13: with /api/access failed once, a public demo's visitor read "Private preview",
    // "readable through your invite and no other" and "Every run is kept".
    render(
      <AccessModeKnown.Provider value={false}>
        <Landing
          stage="empty"
          processingLabel=""
          pendingName=""
          composerText=""
          setComposerText={vi.fn()}
          onHome={vi.fn()}
          onPickFile={vi.fn()}
          onLoadSample={vi.fn()}
          proof={null}
          proofStory={false}
          onOpenProof={vi.fn()}
          uploadError={null}
          apiHealth={health("entered")}
          accessKnown
          recent={[]}
          onOpenDocument={vi.fn()}
          onAllDocuments={vi.fn()}
          viewError={null}
          reduceMotion
        />
      </AccessModeKnown.Provider>,
    );
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/Private preview|Public demo|Open preview/);
    expect(text).not.toContain("readable through your invite");
    expect(text).not.toContain("Every run is kept");
  });
});
