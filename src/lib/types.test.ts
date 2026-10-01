import { describe, expect, it } from "vitest";
import { statusLabel } from "./types";

/** The chip a lawyer reads most: "Within guidance" is a comparison code made, or it says it is the model's view. */
describe("statusLabel", () => {
  it("calls a pass without guidance an answer", () => {
    expect(statusLabel("pass", false)).toBe("Answered");
    expect(statusLabel("pass", false, "model_hint")).toBe("Answered");
  });

  it("calls a computed pass within guidance", () => {
    expect(statusLabel("pass", true, "computed_days")).toBe("Within guidance");
  });

  it("marks a pass the model hinted as the model's view", () => {
    expect(statusLabel("pass", true, "model_hint")).toBe("Within guidance (model's view)");
  });

  it("leaves the other statuses as they are", () => {
    expect(statusLabel("needs_review", true, "model_hint")).toBe("Needs review");
    expect(statusLabel("missing", false)).toBe("Not found");
  });
});
