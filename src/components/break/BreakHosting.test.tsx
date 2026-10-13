/**
 * What /break says about where the live workbench runs, and where its workbench links lead, follow the build: the
 * cloud images (NEXT_PUBLIC_HOSTING=cloud) never claim a laptop, the workstation's build keeps it, and the static mirror
 * (NEXT_PUBLIC_EXPORT=state) links to the live workbench by its full address. Oracle staging review, 2026-10-12: the
 * hand-off said "one laptop with one GPU" on every host.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import raw from "./break-record.json";
import { forPage, type BreakRecord } from "./record";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function renderBuiltWith(env: Record<string, string>) {
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value);
  vi.resetModules();
  const { BreakStory } = await import("./BreakStory");
  render(<BreakStory record={forPage(raw as unknown as BreakRecord)} />);
}

const handOff = () => (document.getElementById("your-turn")?.textContent ?? "").replace(/\s+/g, " ");

describe("where the live workbench runs, as the build says", () => {
  it("a cloud build names a cloud server and a GPU that starts when asked, never a laptop", async () => {
    await renderBuiltWith({ NEXT_PUBLIC_HOSTING: "cloud" });
    expect(handOff()).toContain("one small cloud server");
    expect(handOff()).toContain("a GPU that starts when a question arrives");
    expect(handOff()).toContain("This page is a recording and works either way.");
    expect(handOff()).not.toMatch(/laptop/);
  });

  it("the workstation's build keeps the laptop", async () => {
    await renderBuiltWith({});
    expect(handOff()).toContain("runs live on one laptop with one GPU");
    expect(screen.getByRole("link", { name: "Open the workbench" }).getAttribute("href")).toBe("/");
  });

  it("the static mirror links to the live workbench by its full address", async () => {
    await renderBuiltWith({ NEXT_PUBLIC_EXPORT: "state", NEXT_PUBLIC_WORKBENCH_URL: "https://workbench.example.org" });
    expect(screen.getByRole("link", { name: "Open the workbench" }).getAttribute("href")).toBe("https://workbench.example.org");
    expect(screen.getByRole("link", { name: "Workbench" }).getAttribute("href")).toBe("https://workbench.example.org");
    expect(screen.getByRole("link", { name: "Research" }).getAttribute("href")).toBe("/state");
  });
});
