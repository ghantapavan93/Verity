/**
 * The proof page states each measurement as the record holds it, with the day it was measured. It gave CUAD-30 as
 * citation precision 0.85 and recall 0.67, the figures of a scorer that was not the pre-registered rule, and BM25
 * Recall@6 as 0.85, measured without the alias table that made it 0.98, both undated (stress test, 2026-10-30, evaluation
 * claims EVL-4 and EVL-6). Every figure here is read from what the code derives: docs/CUAD.md's table, which
 * backend/tests/test_docs_claims.py holds to scripts/score_cuad.py, and the committed retrieval measurement.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = process.cwd();
const page = readFileSync(join(ROOT, "proof", "index.html"), "utf8");

/** A row of the measurements table, by the question it answers, as text. */
function row(question: string): string {
  const found = [...page.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map((m) => m[1].replace(/<[^>]+>/g, "")).find((r) => r.includes(question));
  expect(found, question).toBeTruthy();
  return found!;
}

/** The precision and recall columns of a docs/CUAD.md table row. */
function cuad(category: string): { precision: string; recall: string } {
  const line = readFileSync(join(ROOT, "docs", "CUAD.md"), "utf8")
    .split("\n")
    .find((l) => l.startsWith(`| ${category} |`))!;
  const cells = line.split("|").map((c) => c.trim());
  return { precision: cells.at(-4)!, recall: cells.at(-3)! };
}

describe("the proof page's measurements", () => {
  it("states CUAD-30 as the scored recording does, overall and for the two categories named unfit, and says when", () => {
    const text = row("labels that are not ours");
    const all = cuad("**all**");
    const uncapped = cuad("Uncapped Liability");
    const nonCompete = cuad("Non-Compete");
    expect(text).toContain(`citation precision ${all.precision}, recall ${all.recall}`);
    expect(text).toContain(`uncapped liability ${uncapped.precision} (recall ${uncapped.recall})`);
    expect(text).toContain(`non-compete ${nonCompete.precision} (recall ${nonCompete.recall})`);
    expect(text).toMatch(/scored 20\d\d-\d\d-\d\d/);
  });

  it("states BM25 Recall@6 as the committed measurement, with its day and what it was measured under", () => {
    const results = JSON.parse(readFileSync(join(ROOT, "backend", "scripts", "results", "eval_retrieval-bm25.json"), "utf8"));
    const sets = results.modes.bm25.sets;
    const text = row("right section");
    expect(text).toContain(`${sets["CUAD both"]["R@6"].toFixed(2)} and ${sets.goldens["R@6"].toFixed(2)}`);
    expect(text).toContain(`measured ${results.measured}`);
  });

  it("names a day beside every figure in those rows", () => {
    for (const question of ["labels that are not ours", "right section"]) {
      for (const clause of row(question).split(/;\s*|\.\s+/)) {
        if (/\b0\.\d\d\b/.test(clause)) expect(clause, clause).toMatch(/\b20\d\d-\d\d-\d\d\b/);
      }
    }
  });
});
