/**
 * The contract-state surface shows the experiment's recording and decides nothing: every number on it is in the
 * record it was given, and the record's own hash verdict is shown with it.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ContractStateView, StateArrivalView } from "@/lib/types";

import { ContractState } from "./ContractState";

const doc = (id: string, title: string, date: string, instrument = "AMENDMENT") => ({
  recordId: id,
  title,
  date,
  instrument,
  type: "CREDIT AGREEMENT",
  filer: "0000000001",
  filerName: "ACME CORP",
});

const BASE = doc("edgar:a-0", "CREDIT AGREEMENT", "2023-05-17", "BASE");
const AMEND = doc("edgar:a-1", "AMENDMENT NO. 1 TO CREDIT AGREEMENT", "2023-07-17");

const BOUND: StateArrivalView = {
  document: AMEND,
  edge: {
    state: "bound",
    relation: "AMENDS",
    proof: "ACCEPTED",
    source: AMEND.recordId,
    target: BASE,
    evidence: "that certain Credit Agreement, dated as of May 17, 2023",
    candidates: 4,
    leftForModel: false,
  },
  family: {
    id: "Fabc",
    review: [],
    members: [
      { ...BASE, actsOn: null, relation: null, arrived: false },
      { ...AMEND, actsOn: BASE.recordId, relation: "AMENDS", arrived: true },
    ],
  },
  effective: {
    asOf: "2030-01-01",
    before: { GOVERNING_LAW: "New York", MATURITY_DATE: "2027-05-17" },
    after: { GOVERNING_LAW: "New York", MATURITY_DATE: "2028-05-17" },
    operations: 2,
    applied: 1,
    needsReview: 1,
    unsupportedMutations: 0,
  },
  context: {
    template: { type: "CREDIT AGREEMENT", clusterSize: 3, exemplar: BASE, baseIsExemplar: true },
    cohort: { type: "CREDIT AGREEMENT", governingLaw: "New York", comparable: 43, maturityDateStated: 12 },
    deviationsFromExemplar: [],
  },
  findings: { inFamilyAfter: 12, changed: 1, staleExamples: ["2.2"] },
  impactEnvelope: {
    impactEnvelope: 9,
    impactEnvelopeByKind: { EDGE: 1, FAMILY: 1, EFFECTIVE: 1, FINDING: 4 },
    documentsExamined: 4,
    movedKeys: 31,
    envelopeSeconds: 0.002,
  },
  recomputePlan: { total: 6, byKind: { EDGE: 1, FAMILY: 1, EFFECTIVE: 1, FINDING: 2, MEMBER: 1 } },
  stateDelta: { total: 5, byKind: { EDGE: 1, FAMILY: 1, EFFECTIVE: 1, FINDING: 1, MEMBER: 1 } },
  work: {
    textReads: 7,
    adjudications: 4,
    pairScores: 0,
    computed: 6,
    keptByInputCheck: 3,
    disturbedWithoutDependencyChange: 0,
    modelCallsIfFindingsWereModelMade: 1,
    charactersAModelWouldRead: 900,
  },
  latencyMs: 41.5,
  documentsBefore: 5414,
  objectsBefore: 48000,
  verified: { stateEqualToRebuild: true, changedOutsideEnvelope: 0, rebuildSeconds: 300 },
  edgeOnGoldTarget: true,
};

const AMBIGUOUS: StateArrivalView = {
  ...BOUND,
  document: doc("edgar:b-1", "FIRST AMENDMENT TO FORBEARANCE AGREEMENT", "2023-05-14"),
  edge: { ...BOUND.edge!, state: "ambiguous", relation: null, proof: null, target: null, leftForModel: true, evidence: null },
  family: null,
  effective: { ...BOUND.effective, before: null, operations: 0, applied: 0, needsReview: 0 },
  context: { template: null, cohort: null, deviationsFromExemplar: [] },
  findings: { inFamilyAfter: 0, changed: 0, staleExamples: [] },
  verified: null,
  documentsBefore: 5415,
};

const VIEW: ContractStateView = {
  available: true,
  source: "contract-state.json",
  detail: null,
  schemaVersion: "contract-state/2",
  sourceCommit: "148007b0000000000000000000000000000000000",
  generatedAt: "2026-10-06T23:00:00+00:00",
  sha256: "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
  sha256Verified: true,
  whatThisIs: "A recording.",
  portfolio: { documentsAtStart: 5414, objectsAtStart: 48000, familiesAtStart: 4900, findingsAtEnd: 31000, source: "test" },
  summary: {
    arrivals: 2,
    portfolioDocumentsAtStart: 5414,
    objectsAtStart: 48000,
    verifiedAgainstRebuild: 1,
    verifiedStateEqual: 1,
    changedOutsideEnvelope: 0,
    stabilityBudgetDisturbedWithoutDependencyChange: 0,
    impactEnvelopeMean: 9,
    impactEnvelopeMax: 9,
    recomputePlanMean: 6,
    stateDeltaMean: 5,
    envelopeShareUnchanged: 0.44,
    documentsExaminedMean: 4,
    documentsExaminedMax: 4,
    edgesAccepted: 1,
    edgesOnGoldTarget: 1,
    leftForModel: 1,
    modelCallsExecuted: 0,
    perArrival: {},
    naiveRebuildPerChange: { objects_recomputed: 48000, findings_recomputed: 31000 },
    workAvoidedPerArrivalMean: {},
  },
  evidence: {
    relationship_audit: { metrics: { precision: 0.9559, recall: 0.8904 }, gates: { PRIMARY: "FAIL" } },
    authorization: { cross_scope_leakage_observations: 0, changes_in_room_0: 30 },
  },
  arrivals: [BOUND, AMBIGUOUS],
};

afterEach(cleanup);

describe("ContractState", () => {
  it("shows the chosen arrival's family, the effective fact that moved, envelope, plan and delta, and the work avoided, all from the record", () => {
    render(<ContractState view={VIEW} />);
    expect(screen.getByRole("heading", { name: /One contract changes\. What else must change with it\?/ })).toBeTruthy();
    expect(screen.getByText("1 of 1")).toBeTruthy();
    expect(screen.getByLabelText("This arrival in one line").textContent).toBe(
      "5,414 documents → 4 examined → 1 family joined → 5 of 48,000 derived objects changed; the rest untouched.",
    );
    expect(screen.getByText("2027-05-17 → 2028-05-17")).toBeTruthy();
    expect(screen.getByText("yes: maturity date")).toBeTruthy();
    expect(screen.getByText("AMENDS → CREDIT AGREEMENT")).toBeTruthy();
    expect(screen.getByText(/AMENDS: this amendment no\. 1 to credit agreement → CREDIT AGREEMENT, 2023-05-17/)).toBeTruthy();
    expect(screen.getByText(/43 comparable credit agreements under New York law; 12 state a maturity date/)).toBeTruthy();
    expect(screen.getByText("47,994")).toBeTruthy();
    expect(screen.getByText("30,999")).toBeTruthy();
    expect(screen.getByText("9 objects it could reach")).toBeTruthy();
    expect(screen.getByText("6 objects recomputed")).toBeTruthy();
    expect(screen.getByText("5 objects changed")).toBeTruthy();
    expect(screen.getByText(/precision was 0\.9559 and its recall 0\.8904/)).toBeTruthy();
    expect(screen.getByText(/its preregistered gate \(precision at least 0\.98, false families at most 2%\) was not met/)).toBeTruthy();
    expect(screen.getByText(/language models, not people/)).toBeTruthy();
    expect(screen.getByText(/file matches its hash/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Arrival"), { target: { value: "1" } });
    expect(screen.getByText("two distinct agreements satisfy the reference: none accepted")).toBeTruthy();
    expect(screen.getByText("1 · none executed")).toBeTruthy();
    expect(screen.getByText("not checked")).toBeTruthy();
  });

  it("says when the record is not connected and shows an edited file as edited", () => {
    render(<ContractState view={{ available: false, source: null, detail: "contract-state.json not found", evidence: {}, arrivals: [] }} />);
    expect(screen.getByText(/The contract-state record is not connected\. contract-state\.json not found/)).toBeTruthy();
    cleanup();
    render(<ContractState view={{ ...VIEW, sha256Verified: false }} />);
    expect(screen.getByText(/FILE DOES NOT MATCH ITS HASH/)).toBeTruthy();
  });
});
