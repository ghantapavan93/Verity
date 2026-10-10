/**
 * A refused guidance says why, where it was entered. The error used to be handed to the run's error slot, which keeps
 * it only while no run is in progress and is not shown beside a finished run's findings: a guidance over the length
 * limit, or refused by the public write bound, closed nothing and explained nothing (m7 audit, 2026-10-10).
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { useGuidance } from "../hooks/useGuidance";
import { GuidanceScope } from "./GuidanceScope";

const createGuidance = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), createGuidance: (text: string) => createGuidance(text) }));

afterEach(() => {
  cleanup();
  createGuidance.mockReset();
});

function Harness() {
  const guidance = useGuidance();
  return <GuidanceScope documentName="agreement.pdf" guidance={guidance} reduceMotion />;
}

it("shows why a guidance was refused inside the popover, and keeps the popover open", async () => {
  createGuidance.mockRejectedValue(new Error("the guidance is longer than 20,000 characters"));
  render(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: /Add guidance/ }));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Use" }));
  });
  expect(screen.getByRole("alert").textContent).toContain("longer than 20,000 characters");
  expect(screen.getByLabelText("Legal guidance")).toBeTruthy();
});

it("clears the reason once a guidance is accepted", async () => {
  createGuidance.mockRejectedValueOnce(new Error("too many writes this hour")).mockResolvedValueOnce({ id: "g1", text: "At least 30 days." });
  render(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: /Add guidance/ }));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Use" }));
  });
  expect(screen.getByRole("alert")).toBeTruthy();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Use" }));
  });
  expect(screen.queryByRole("alert")).toBeNull();
});
