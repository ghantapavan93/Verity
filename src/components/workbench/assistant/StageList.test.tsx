/**
 * While a run waits on the model, the note under the stages says what the wait can hold: for a hosted model that
 * sleeps when idle, waking it; for a model on the server itself, nothing of the kind.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StageList } from "./StageList";

afterEach(cleanup);

const note = () => screen.getByText(/these stages are the server's own reports/i).textContent ?? "";

describe("what the wait for the model can hold", () => {
  it("a hosted model that sleeps: waking it adds 1.5 to 3 minutes to the first answer", () => {
    render(<StageList current="checking" details={{}} checkingLabel="Checking" reduceMotion modelPlace="Modal (US)" modelSleeps />);
    expect(note()).toContain("The model runs on Modal (US).");
    expect(note()).toContain("Waking it adds 1.5 to 3 minutes to the first answer");
    expect(note()).not.toContain("under two minutes");
  });

  it("control: a model on the server itself never sleeps, and the note says nothing of waking", () => {
    render(<StageList current="checking" details={{}} checkingLabel="Checking" reduceMotion modelPlace="the Verity server" />);
    expect(note()).toContain("Most answers take under two minutes");
    expect(note()).not.toMatch(/sleep|wak/i);
  });

  it("a question asked behind others says how many asked before it are still being answered, in place of the usual time", () => {
    render(<StageList current="checking" details={{}} checkingLabel="Checking" reduceMotion modelPlace="the Verity server" ahead={3} />);
    expect(note()).toContain(
      "The model runs on the Verity server. It answers one question at a time, and 3 questions asked before this one are still being answered.",
    );
    expect(note()).not.toContain("under two minutes");
  });

  it("one question ahead is said as one", () => {
    render(<StageList current="checking" details={{}} checkingLabel="Checking" reduceMotion ahead={1} />);
    expect(note()).toContain("The model answers one question at a time, and one question asked before this one is still being answered.");
  });

  it("control: nothing ahead keeps the usual sentence", () => {
    render(<StageList current="checking" details={{}} checkingLabel="Checking" reduceMotion ahead={0} />);
    expect(note()).toContain("Most answers take under two minutes");
  });
});
