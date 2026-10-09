/**
 * The first screen says what the API says its door is, and nothing before it has said: it used to read "Private
 * preview … readable through your invite and no other" for the first seconds of an open site (QA review, 2026-10-08).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Health, RunSummary } from "@/lib/types";

import { PublicDemo } from "../access/PublicDemo";
import { Landing } from "./Landing";

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

function renderLanding(apiHealth: Health | null, accessKnown: boolean, proof: RunSummary | null = null, proofStory = false) {
  return render(
    <Landing
      stage="empty"
      processingLabel=""
      pendingName=""
      composerText=""
      setComposerText={vi.fn()}
      onHome={vi.fn()}
      onPickFile={vi.fn()}
      onLoadSample={vi.fn()}
      proof={proof}
      proofStory={proofStory}
      onOpenProof={vi.fn()}
      uploadError={null}
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

  it("names the hosted model and says what is sent to it", () => {
    renderLanding(at("hosted", "a Modal GPU in the US"), true);
    const text = document.body.textContent ?? "";
    expect(text).toContain("run on a Modal GPU in the US");
    expect(text).toContain("are sent there to be answered");
    expect(text).not.toMatch(/No contract is sent to a hosted model|does not send the contract anywhere|this machine/);
  });

  it("says a model on the server keeps the contract there", () => {
    renderLanding(at("server"), true);
    const text = document.body.textContent ?? "";
    expect(text).toContain("run on the Verity server. No contract is sent to a hosted model.");
    expect(text).not.toContain("this machine");
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

  it("tells the four-step story only of the proof run it was written for", () => {
    renderLanding({ ...health("off"), modelLocation: "server", modelHost: "" } as Health, true, run, true);
    expect(document.body.textContent).toContain("Code checks the quote, then the arithmetic");
  });

  it("shows another run's receipt without a story that is not its own", () => {
    // Release rehearsal, 2026-10-09: with no proof run configured, the latest run took the story's place, and the story
    // says the quote was found in another section and the days were compared, true only of the proof run.
    renderLanding({ ...health("off"), modelLocation: "server", modelHost: "" } as Health, true, run, false);
    expect(document.body.textContent).toContain("Which law governs?");
    expect(document.body.textContent).not.toContain("Code checks the quote, then the arithmetic");
  });
});

describe("Landing: the way to the research", () => {
  it("links the recorded research and the source from the first screen", () => {
    renderLanding(health("entered"), true);
    const links = screen.getByRole("navigation", { name: "Elsewhere" });
    expect(links.querySelector('a[href="/state"]')?.textContent).toBe("Research");
    expect(links.querySelector('a[href="https://github.com/ghantapavan93/Verity"]')?.textContent).toBe("Source");
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
  });
});
