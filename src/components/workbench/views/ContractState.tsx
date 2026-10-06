"use client";

/**
 * One contract changes: what else must change with it. A recording from the contract-state experiment, replayed from
 * its result file. The engine planned every arrival before recomputing anything, recomputed only what the plan named
 * and whose inputs had moved, and was checked against a rebuild from nothing. Every number here is the experiment's;
 * this component chooses which recorded arrival to show and decides nothing else.
 */

import { useState } from "react";
import styles from "./Views.module.css";
import local from "./ContractState.module.css";
import { Figures } from "./Figures";
import { formatWhen, shortHash } from "@/lib/format";
import type { ContractStateView, StateArrivalView } from "@/lib/types";

const grouped = new Intl.NumberFormat("en-US");

const FACT_LABELS: Record<string, string> = { GOVERNING_LAW: "Governing law", MATURITY_DATE: "Maturity date" };

type Doc = NonNullable<StateArrivalView["edge"]>["target"];

function titleOf(doc: Doc | StateArrivalView["document"] | null | undefined): string {
  if (!doc) return "–";
  return doc.title || doc.recordId;
}

function factText(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return "not stated";
  if (value === "AMBIGUOUS") return "stated two ways: needs review";
  return String(value);
}

function count(byKind: Record<string, number> | undefined, kind: string): number {
  return byKind?.[kind] ?? 0;
}

/** What moved in the family's effective state: the admitted facts that changed, else the instructions read. */
function effectiveChange(arrival: StateArrivalView): string {
  if (!count(arrival.changed.byKind, "EFFECTIVE")) return "no";
  const before = arrival.effective.before ?? {};
  const after = arrival.effective.after ?? {};
  const moved = Object.keys(FACT_LABELS).filter((f) => arrival.effective.before && before[f] !== after[f]);
  if (moved.length) return `yes: ${moved.map((f) => FACT_LABELS[f].toLowerCase()).join(", ")}`;
  const e = arrival.effective;
  return `yes: its instructions (${e.applied} applied, ${e.needsReview} left for review); no admitted fact moved`;
}

function EffectiveFacts({ arrival }: { arrival: StateArrivalView }) {
  const after = arrival.effective.after ?? {};
  const before = arrival.effective.before;
  const fields = Object.keys(FACT_LABELS);
  return (
    <dl className={local.facts}>
      {fields.map((field) => {
        const was = before ? before[field] : undefined;
        const now = after[field];
        const moved = before !== null && before !== undefined && was !== now;
        return (
          <div key={field} style={{ display: "contents" }}>
            <dt>{FACT_LABELS[field]}</dt>
            <dd className={moved ? local.moved : undefined}>{moved ? `${factText(was)} → ${factText(now)}` : factText(now)}</dd>
          </div>
        );
      })}
      <div style={{ display: "contents" }}>
        <dt>Instructions</dt>
        <dd>
          {arrival.effective.operations === 0
            ? "none read in the family"
            : `${arrival.effective.applied} applied, ${arrival.effective.needsReview} left for review; ${arrival.effective.unsupportedMutations} unsupported`}
        </dd>
      </div>
    </dl>
  );
}

export function ContractState({ view }: { view: ContractStateView }) {
  const [index, setIndex] = useState(0);
  if (!view.available || !view.summary || !view.portfolio) {
    return (
      <section className={styles.experiments} aria-labelledby="state-title">
        <div className={styles.kicker}>Recorded in the laboratory</div>
        <h2 id="state-title" className={styles.title}>
          One contract changes
        </h2>
        <p className={styles.quiet}>The contract-state record is not connected. {view.detail}</p>
      </section>
    );
  }
  const summary = view.summary;
  const portfolio = view.portfolio;
  const arrival = view.arrivals[Math.min(index, view.arrivals.length - 1)] ?? null;
  const naive = summary.naiveRebuildPerChange ?? {};
  const audit = (view.evidence?.relationship_audit as { metrics?: Record<string, number | null> } | undefined)?.metrics;
  const leakage = (view.evidence?.authorization as { cross_scope_leakage_observations?: number; changes_in_room_0?: number } | undefined) ?? null;
  return (
    <section className={styles.experiments} aria-labelledby="state-title">
      <div className={styles.kicker}>Recorded in the laboratory</div>
      <h2 id="state-title" className={styles.title}>
        One contract changes. What else must change with it?
      </h2>
      <p className={styles.lede}>
        {view.whatThisIs} Replayed here from the result file{view.sourceCommit ? ` of commit ${shortHash(view.sourceCommit, 7)}` : ""}; nothing on this surface
        is live.
      </p>
      {arrival && (
        <p className={local.headline} aria-label="This arrival in one line">
          {grouped.format(arrival.documentsBefore)} documents → {arrival.plan.documentsExamined} examined →{" "}
          {arrival.edge?.proof === "ACCEPTED" ? "1 family joined" : "no family joined"} → {arrival.changed.total} of {grouped.format(arrival.objectsBefore)}{" "}
          derived objects changed; the rest untouched.
        </p>
      )}
      <Figures
        label="The portfolio, and what every arrival was held to"
        items={[
          { label: "Documents", value: portfolio.documentsAtStart },
          { label: "Derived objects", value: portfolio.objectsAtStart, note: "edges, families, effective states, findings, templates, cohorts" },
          { label: "Arrivals recorded", value: summary.arrivals },
          {
            label: "Checked against a rebuild",
            value: `${summary.verifiedStateEqual} of ${summary.verifiedAgainstRebuild}`,
            note: "state equal to rebuilding everything from nothing",
          },
          { label: "Changed but not planned", value: summary.falseNegativeReach, note: "over the checked arrivals" },
          { label: "Recomputed with no input moved", value: summary.stabilityBudgetDisturbedWithoutDependencyChange, note: "over every arrival" },
        ]}
      />
      {arrival && (
        <>
          <p className={styles.quiet} style={{ marginTop: 18 }}>
            <label htmlFor="state-pick">Arrival</label>{" "}
            <select id="state-pick" value={index} onChange={(event) => setIndex(Number(event.target.value))} style={{ maxWidth: "100%" }}>
              {view.arrivals.map((a, i) => (
                <option key={a.document.recordId} value={i}>
                  {titleOf(a.document)}
                  {a.document.date ? ` · ${a.document.date}` : ""}
                </option>
              ))}
            </select>
          </p>
          <div className={local.panes}>
            <div className={local.pane}>
              <h3 className={local.paneTitle}>Relationship family</h3>
              {arrival.family ? (
                <ol className={local.members} aria-label="Family members, oldest first">
                  {arrival.family.members.map((m) => (
                    <li key={m.recordId} className={`${local.member} ${m.arrived ? local.memberArrived : ""}`}>
                      <span>
                        {titleOf(m)}
                        {m.date ? `, ${m.date}` : ""}
                        {m.arrived ? " · arrived" : ""}
                      </span>
                      {m.relation && (
                        <span className={local.relation}>
                          {m.relation} → {titleOf(arrival.family!.members.find((x) => x.recordId === m.actsOn) ?? null)}
                        </span>
                      )}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className={styles.quiet}>No family.</p>
              )}
              {arrival.edge?.evidence && <p className={local.evidence}>“{arrival.edge.evidence}”</p>}
            </div>
            <div className={local.pane}>
              <h3 className={local.paneTitle}>Effective state, as of {arrival.effective.asOf}</h3>
              <EffectiveFacts arrival={arrival} />
            </div>
            <div className={local.pane}>
              <h3 className={local.paneTitle}>Template and cohort</h3>
              <dl className={local.facts}>
                <div style={{ display: "contents" }}>
                  <dt>Template</dt>
                  <dd>
                    {arrival.context.template
                      ? `${arrival.context.template.clusterSize} ${arrival.context.template.clusterSize === 1 ? "agreement" : "agreements"} on this form${
                          arrival.context.template.baseIsExemplar ? "; this base is the exemplar" : `; exemplar ${titleOf(arrival.context.template.exemplar)}`
                        }`
                      : "the base is not an executed agreement in the corpus"}
                  </dd>
                </div>
                <div style={{ display: "contents" }}>
                  <dt>Cohort</dt>
                  <dd>
                    {arrival.context.cohort
                      ? `${arrival.context.cohort.comparable} comparable ${arrival.context.cohort.type.toLowerCase()}s under ${arrival.context.cohort.governingLaw} law; ${arrival.context.cohort.maturityDateStated} state a maturity date`
                      : "no cohort: governing law not read"}
                  </dd>
                </div>
                <div style={{ display: "contents" }}>
                  <dt>Deviations</dt>
                  <dd>
                    {arrival.context.deviationsFromExemplar.length
                      ? arrival.context.deviationsFromExemplar
                          .map((d) => `${FACT_LABELS[d.field] ?? d.field}: ${factText(d.before)} → ${factText(d.after)}`)
                          .join("; ")
                      : "none established from the exemplar"}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
          <ol className={local.plan} aria-label="The recompute plan for this arrival">
            <li className={local.step}>
              <span className={local.stepName}>Portfolio</span>
              <span className={local.stepValue}>
                {grouped.format(arrival.documentsBefore)} documents, {grouped.format(arrival.objectsBefore)} derived objects
              </span>
            </li>
            <li className={local.step}>
              <span className={local.stepName}>Candidates examined</span>
              <span className={local.stepValue}>{arrival.plan.documentsExamined}</span>
            </li>
            <li className={local.step}>
              <span className={local.stepName}>Relationship</span>
              <span className={local.stepValue}>
                {arrival.edge?.target && arrival.edge.proof === "ACCEPTED"
                  ? `${arrival.edge.relation}: this ${titleOf(arrival.document).toLowerCase()} → ${titleOf(arrival.edge.target)}${arrival.edge.target.date ? `, ${arrival.edge.target.date}` : ""}`
                  : arrival.edge?.state === "ambiguous"
                    ? "two distinct agreements satisfy the reference: none accepted"
                    : "none bound"}
              </span>
            </li>
            <li className={local.step}>
              <span className={local.stepName}>Planned before recompute</span>
              <span className={local.stepValue}>
                {arrival.plan.planned} objects{" "}
                <em>
                  · {count(arrival.plan.plannedByKind, "FAMILY")} families, {count(arrival.plan.plannedByKind, "FINDING")} findings
                </em>
              </span>
            </li>
            <li className={local.step}>
              <span className={local.stepName}>Effective state changed</span>
              <span className={local.stepValue}>{effectiveChange(arrival)}</span>
            </li>
            <li className={local.step}>
              <span className={local.stepName}>Deviations reached</span>
              <span className={local.stepValue}>{count(arrival.changed.byKind, "DEVIATION")}</span>
            </li>
            <li className={local.step}>
              <span className={local.stepName}>Cohorts reached</span>
              <span className={local.stepValue}>{count(arrival.changed.byKind, "COHORT")}</span>
            </li>
            <li className={local.step}>
              <span className={local.stepName}>Findings</span>
              <span className={local.stepValue}>
                {arrival.findings.changed} stale or new ·{" "}
                {arrival.findings.inFamilyAfter - arrival.findings.changed >= 0 ? arrival.findings.inFamilyAfter - arrival.findings.changed : 0} in the family
                kept
              </span>
            </li>
            <li className={local.step}>
              <span className={local.stepName}>Left for a model</span>
              <span className={local.stepValue}>{arrival.edge?.leftForModel ? "1 · none executed" : "0"}</span>
            </li>
            <li className={local.step}>
              <span className={local.stepName}>Latency</span>
              <span className={local.stepValue}>
                {grouped.format(Math.round(arrival.latencyMs))} ms{" "}
                <em>
                  · {arrival.work.computed} objects recomputed, {arrival.work.keptByInputCheck} kept because no input moved
                </em>
              </span>
            </li>
          </ol>
          <Figures
            label="Work avoided by this arrival, against rebuilding everything"
            items={[
              { label: "Documents not examined", value: Math.max(0, arrival.documentsBefore - arrival.plan.documentsExamined) },
              { label: "Objects not recomputed", value: Math.max(0, Math.round((naive.objects_recomputed ?? 0) - arrival.work.computed)) },
              {
                label: "Findings not recomputed",
                value: Math.max(0, Math.round((naive.findings_recomputed ?? 0) - arrival.work.modelCallsIfFindingsWereModelMade)),
                note: "each a model call, were findings model-made",
              },
              {
                label: "Changed but not planned",
                value: arrival.verified ? arrival.verified.changedNotPlanned : "not checked",
                note: arrival.verified ? "checked against a rebuild" : undefined,
              },
            ]}
          />
        </>
      )}
      <p className={styles.quiet} style={{ marginTop: 16 }}>
        Evidence in the same experiment:{" "}
        {audit
          ? `on a second blind-read audit of real document pairs, the relationship engine's precision was ${audit.precision ?? "–"} and its recall ${audit.recall ?? "–"} (it leaves the rest UNKNOWN), with every accepted direction right`
          : "no relationship audit record"}
        {leakage
          ? `; a viewer of one room observed ${leakage.cross_scope_leakage_observations} changes from ${leakage.changes_in_room_0} arrivals in the other`
          : ""}
        .
      </p>
      <p className={styles.quiet}>
        Source: {view.source}
        {view.generatedAt ? ` · exported ${formatWhen(view.generatedAt)}` : ""}
        {view.sha256 ? ` · sha256 ${shortHash(view.sha256, 12)}` : ""}
        {view.sha256Verified === true
          ? " · file matches its hash"
          : view.sha256Verified === false
            ? " · FILE DOES NOT MATCH ITS HASH: it was edited after export"
            : ""}
      </p>
    </section>
  );
}
