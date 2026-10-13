/**
 * While a run waits on the model, the note under the stages says what the wait can hold: for a hosted model that
 * sleeps when idle, waking it; for a model on the server itself, nothing of the kind.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StageList } from "./StageList";

afterEach(cleanup);

const note = () => screen.getByText(/the stages above are the API/i).textContent ?? "";

describe("what the wait for the model can hold", () => {
  it("a hosted model that sleeps: waking it adds one and a half to three minutes to the first answer", () => {
    render(<StageList current="checking" details={{}} checkingLabel="Checking" reduceMotion modelPlace="Modal (US)" modelSleeps />);
    expect(note()).toContain("The model runs on Modal (US).");
    expect(note()).toContain("waking it adds one and a half to three minutes to the first answer");
    expect(note()).not.toContain("under two minutes");
  });

  it("control: a model on the server itself never sleeps, and the note says nothing of waking", () => {
    render(<StageList current="checking" details={{}} checkingLabel="Checking" reduceMotion modelPlace="the Verity server" />);
    expect(note()).toContain("Most answers take under two minutes");
    expect(note()).not.toMatch(/sleep|wak/i);
  });
});
