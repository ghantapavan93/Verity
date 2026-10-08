/**
 * The first screen says what the API says its door is, and nothing before it has said: it used to read "Private
 * preview … readable through your invite and no other" for the first seconds of an open site (QA review, 2026-10-08).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Health } from "@/lib/types";

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

function renderLanding(apiHealth: Health | null, accessKnown: boolean) {
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
      proof={null}
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
