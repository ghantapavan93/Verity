/**
 * In a public demo the corpus tools (golden set, batch extraction, document families) are the owner's: the API says
 * they do not exist for a visitor, so the Runs surface neither asks for them nor offers a tab that leads to "could not
 * be loaded". An invited reader still sees them.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getExperiments: vi.fn(),
  getContractState: vi.fn(),
  getCitations: vi.fn(),
  listBatches: vi.fn(),
  getFamilies: vi.fn(),
  getGoldens: vi.fn(),
  getRunDetail: vi.fn(),
  getBatch: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ ...api, absolute: (path: string) => path }));

import { PublicDemo } from "../access/PublicDemo";
import { RunsView } from "./RunsView";

const never = () => new Promise(() => undefined);

describe("RunsView in a public demo", () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset();
    api.listRuns.mockResolvedValue([]);
    api.getExperiments.mockImplementation(never);
    api.getContractState.mockImplementation(never);
    api.getCitations.mockImplementation(never);
    api.listBatches.mockResolvedValue([]);
    api.getFamilies.mockImplementation(never);
    api.getGoldens.mockRejectedValue(new Error("not found"));
  });
  afterEach(cleanup);

  it("asks for none of the owner's corpus tools and offers no tab to them", async () => {
    render(
      <PublicDemo.Provider value={{ retentionDays: 7 }}>
        <RunsView notice={null} onOpenRun={vi.fn()} />
      </PublicDemo.Provider>,
    );
    await screen.findByRole("link", { name: "Runs" });
    expect(api.getGoldens).not.toHaveBeenCalled();
    expect(api.listBatches).not.toHaveBeenCalled();
    expect(api.getFamilies).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: "Golden set" })).toBeNull();
    expect(screen.queryByText(/could not be loaded/)).toBeNull();
  });

  it("control: an invited reader still has them", async () => {
    render(<RunsView notice={null} onOpenRun={vi.fn()} />);
    expect(await screen.findByRole("link", { name: "Golden set" })).toBeTruthy();
    expect(api.getGoldens).toHaveBeenCalled();
  });
});
