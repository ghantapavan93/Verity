/**
 * The evidence pack downloads from the page it is asked on: the wait shows, the file keeps the name the API gave it, and a
 * refusal is said in place instead of replacing the workbench with the API's error (exports audit, 2026-10-15).
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { attachment } from "@/lib/api";

const api = vi.hoisted(() => ({ attachment: vi.fn<typeof attachment>() }));

vi.mock("@/lib/api", () => ({
  absolute: (url: string) => `http://api.test${url}`,
  attachment: api.attachment,
  errorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
}));

import { PackLink } from "./PackLink";

describe("PackLink", () => {
  let saved: string[];
  beforeEach(() => {
    saved = [];
    URL.createObjectURL = vi.fn(() => "blob:pack");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(this.download);
    });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("keeps a real address, says what the zip holds, and saves the file under the API's name", async () => {
    api.attachment.mockResolvedValue({ blob: new Blob(["zip"]), name: "evidence-run1.zip" });
    render(<PackLink runId="run1" className="link" />);
    const link = screen.getByRole("link", { name: "Download evidence pack" });
    expect(link.getAttribute("href")).toBe("http://api.test/api/runs/run1/evidence-pack");
    expect(screen.getByRole("status").textContent).toMatch(/verify\.py/);
    fireEvent.click(link);
    expect(await screen.findByText(/verify\.py/)).toBeTruthy();
    await vi.waitFor(() => expect(saved).toEqual(["evidence-run1.zip"]));
    expect(api.attachment).toHaveBeenCalledWith("/api/runs/run1/evidence-pack", "evidence-run1.zip");
  });

  it("shows the wait while the zip is made", async () => {
    let finish: (value: { blob: Blob; name: string }) => void = () => {};
    api.attachment.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    render(<PackLink runId="run1" className="link" />);
    fireEvent.click(screen.getByRole("link", { name: "Download evidence pack" }));
    expect((await screen.findByRole("status")).textContent).toMatch(/Preparing/);
    finish({ blob: new Blob(["zip"]), name: "evidence-run1.zip" });
    await vi.waitFor(() => expect(screen.getByRole("status").textContent).not.toMatch(/Preparing/));
  });

  it("says a refusal in place and saves nothing", async () => {
    api.attachment.mockRejectedValue(new Error("run not found"));
    render(<PackLink runId="run1" className="link" />);
    fireEvent.click(screen.getByRole("link", { name: "Download evidence pack" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The evidence pack could not be made: run not found");
    expect(saved).toEqual([]);
  });
});
