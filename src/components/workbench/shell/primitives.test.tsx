/**
 * The status chip's colour is a claim too: the pass colour is for a pass code stood behind (a record made under policy
 * v2), never for the model's own pass, which is labelled and coloured as the model's.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StatusChip } from "./primitives";

afterEach(cleanup);

describe("StatusChip", () => {
  it("names a pass without guidance as the model's answer, plain, and never dresses an absence as an answer", () => {
    render(<StatusChip status="pass" hasGuidance={false} source="model_hint" />);
    const modelPass = screen.getByText("Model's answer");
    render(<StatusChip status="needs_review" hasGuidance={false} source="model_hint" />);
    render(<StatusChip status="missing" hasGuidance={false} source="model_hint" />);
    const missing = screen.getByText("Not found in the sections read");
    // Until 2026-10-09 the two shared one chip: a reader could not tell "the model answered" from "the model found nothing".
    expect(missing.className).not.toBe(modelPass.className);
    expect(modelPass.className).not.toBe(screen.getByText("Needs review").className);
  });

  it("keeps the pass colour for a pass code confirmed, and gives a caller that names no source the weaker claim", () => {
    render(<StatusChip status="pass" hasGuidance source="confirmed_days" />);
    render(<StatusChip status="pass" hasGuidance source="model_hint" />);
    render(<StatusChip status="pass" hasGuidance />);
    const confirmed = screen.getByText("Within guidance (confirmed by code)");
    const [modelView, unnamed] = screen.getAllByText("Within guidance (model's view)");
    expect(confirmed.className).not.toBe(modelView.className);
    expect(unnamed.className).toBe(modelView.className);
  });
});
