import { describe, expect, it } from "vitest";
import { nameWithoutType } from "./format";

describe("nameWithoutType", () => {
  it("drops the extension only when it is the type the API recorded", () => {
    expect(nameWithoutType("Master Services Agreement.pdf", "pdf")).toBe("Master Services Agreement");
    expect(nameWithoutType("NOTICE.TXT", "txt")).toBe("NOTICE");
  });

  it("shows a name cut through its extension whole, and a name with no recorded type whole", () => {
    // QA campaign, 2026-10-08: a 269-character name was stored cut to 255 characters, without ".txt".
    const cut = "Master-Services-Agreement-" + "x".repeat(229);
    expect(nameWithoutType(cut, "txt")).toBe(cut);
    expect(nameWithoutType("agreement.final-signed", "txt")).toBe("agreement.final-signed");
    expect(nameWithoutType("agreement.pdf", null)).toBe("agreement.pdf");
    expect(nameWithoutType(".txt", "txt")).toBe(".txt"); // never an empty name
  });
});
