/**
 * The arrivals surface shows the experiment's recording and decides nothing: every number on it is in the record
 * it was given, and the record's own hash verdict is shown with it.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { LineageView } from "@/lib/types";

import { Arrivals } from "./Arrivals";

const document = (id: string, title: string, date: string) => ({
  recordId: id,
  title,
  date,
  filer: "0000000001",
  filerName: "ACME CORP",
  instrument: "AMENDMENT",
  agreementType: "CREDIT AGREEMENT",
});

const VIEW: LineageView = {
  available: true,
  source: "lineage-arrivals.json",
  detail: null,
  schemaVersion: "lineage-arrivals/1",
  sourceCommit: "148007b0000000000000000000000000000000000",
  generatedAt: "2026-10-05T23:00:00+00:00",
  sha256: "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
  sha256Verified: true,
  whatThisIs: "A recording. Not a live run.",
  portfolio: { documentsAtStart: 5414, familiesAtStart: 4918, findingsAtStart: 31676, source: "5,474 real documents less the arrivals" },
  summary: {
    arrivals: 2,
    portfolioDocumentsAtStart: 5414,
    familiesAtStart: 4918,
    findingsAtStart: 31676,
    unrelatedFamiliesRecomputedTotal: 0,
    documentsExaminedMean: 29.3,
    documentsExaminedMax: 64,
    edgesBound: 2,
    edgesBoundToGoldBase: 2,
    findingsInvalidatedTotal: 3,
    findingsPreservedTotal: 20,
    modelAsksTotal: 0,
    wallSecondsP50: 0.35,
    wallSecondsP95: 5,
  },
  candidateGenerationHeldOut: { "hybrid-norefs": { "recall@10": 0.89, "recall@20": 1, candidates_examined_per_query_mean: 83.2 } },
  adjudicationHeldOut: { deterministic: { precision: 1, recall: 1, false_family_rate: 0, positives: 274, hard_negatives: 483 } },
  arrivals: [
    {
      document: document("edgar:a-1", "AMENDMENT NO. 1 TO CREDIT AGREEMENT", "2023-07-17"),
      portfolioDocuments: 5414,
      documentsExamined: 29,
      relationship: { target: { ...document("edgar:a-0", "CREDIT AGREEMENT", "2023-05-17"), instrument: "BASE" }, relation: "AMENDS" },
      relationshipIsGold: true,
      family: "family:abc",
      familiesRebuilt: 1,
      unrelatedFamiliesRecomputed: 0,
      familyNodesChanged: 1,
      compositeSectionsChanged: ["2.2", "2.3"],
      trustDependenciesReached: ["family:abc:2.2->2.2"],
      findingsInvalidated: ["family:abc:2.2", "family:abc:2.3"],
      findingsPreserved: 11,
      modelCalls: 0,
      seconds: 0.35,
    },
    {
      document: document("edgar:a-2", "AMENDMENT NO. 2 TO LEASE", "2024-01-01"),
      portfolioDocuments: 5415,
      documentsExamined: 64,
      relationship: null,
      relationshipIsGold: null,
      family: "family:lone",
      familiesRebuilt: 1,
      unrelatedFamiliesRecomputed: 0,
      familyNodesChanged: 0,
      compositeSectionsChanged: [],
      trustDependenciesReached: [],
      findingsInvalidated: [],
      findingsPreserved: 9,
      modelCalls: 0,
      seconds: 0.01,
    },
  ],
};

afterEach(cleanup);

describe("Arrivals", () => {
  it("shows the recording's numbers for the chosen arrival and the file's hash verdict", () => {
    render(<Arrivals view={VIEW} />);
    expect(screen.getByRole("heading", { name: /One amendment arrives in a portfolio of 5,414 documents/ })).toBeTruthy();
    expect(screen.getByText("of 5,414 · 0.54%")).toBeTruthy();
    expect(screen.getByText("AMENDS")).toBeTruthy();
    expect(screen.getByText(/AMENDS CREDIT AGREEMENT, dated 2023-05-17 · the base the experiment's gold names/)).toBeTruthy();
    expect(screen.getByText(/Stale: §2.2, §2.3; 11 preserved\./)).toBeTruthy();
    expect(screen.getByText(/file matches its hash/)).toBeTruthy();
    expect(screen.getByText(/within 10 for 89% and within 20 for 100%/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Arrival"), { target: { value: "1" } });
    expect(screen.getByText("none bound")).toBeTruthy();
    expect(screen.getByText("No relationship bound; nothing else in the portfolio was touched.")).toBeTruthy();
    expect(screen.getByText("of 5,415 · 1.18%")).toBeTruthy();
  });

  it("says when the record is not connected and shows an edited file as edited", () => {
    render(
      <Arrivals
        view={{
          available: false,
          source: null,
          detail: "lineage-arrivals.json not found",
          arrivals: [],
          candidateGenerationHeldOut: {},
          adjudicationHeldOut: {},
        }}
      />,
    );
    expect(screen.getByText(/The lineage record is not connected\. lineage-arrivals\.json not found/)).toBeTruthy();
    cleanup();
    render(<Arrivals view={{ ...VIEW, sha256Verified: false }} />);
    expect(screen.getByText(/FILE DOES NOT MATCH ITS HASH/)).toBeTruthy();
  });
});
