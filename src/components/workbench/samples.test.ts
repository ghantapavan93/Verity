/**
 * The bundled samples: each names a file this build serves, and the amended one brings its own three questions.
 */

import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { SAMPLES, suggestionsFor } from "./samples";

describe("samples", () => {
  it("names files the build serves from public/", () => {
    for (const sample of Object.values(SAMPLES)) expect(existsSync(join(process.cwd(), "public", sample.path))).toBe(true);
  });

  it("offers the open sample's questions first, and the general ones otherwise", () => {
    const general = ["What is the limitation of liability?"];
    expect(suggestionsFor(null, general)).toBe(general);
    expect(suggestionsFor("standard", general)).toBe(general);
    expect(suggestionsFor("amended", general)).toHaveLength(3);
  });
});
