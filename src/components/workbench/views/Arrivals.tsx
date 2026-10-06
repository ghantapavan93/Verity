"use client";

/**
 * One amendment arrives: a recording from the contract-lineage experiment, replayed from its result file. Every
 * number on this surface is the experiment's; the component picks which recorded arrival to show and decides
 * nothing else. The API read the file and checked its hash; whether the hash held is shown too.
 */

import { useState } from "react";
import styles from "./Views.module.css";
import { Figures } from "./Figures";
import { formatWhen, shortHash } from "@/lib/format";
import type { LineageArrivalView, LineageView } from "@/lib/types";

const grouped = new Intl.NumberFormat("en-US");

function percent(part: number, whole: number): string {
  return whole > 0 ? `${((100 * part) / whole).toFixed(2)}%` : "–";
}

function titleOf(document: LineageArrivalView["document"]): string {
  return document.title || document.recordId;
}

function sectionOf(findingId: string): string {
  const at = findingId.lastIndexOf(":");
  return at >= 0 ? `§${findingId.slice(at + 1)}` : findingId;
}

export function Arrivals({ view }: { view: LineageView }) {
  const [index, setIndex] = useState(0);
  if (!view.available || !view.summary || !view.portfolio) {
    return (
      <section className={styles.experiments} aria-labelledby="arrivals-title">
        <div className={styles.kicker}>Recorded in the laboratory</div>
        <h2 id="arrivals-title" className={styles.title}>
          One amendment arrives
        </h2>
        <p className={styles.quiet}>The lineage record is not connected. {view.detail}</p>
      </section>
    );
  }
  const summary = view.summary;
  const portfolio = view.portfolio;
  const arrival = view.arrivals[Math.min(index, view.arrivals.length - 1)] ?? null;
  const hybrid = view.candidateGenerationHeldOut?.["hybrid-norefs"];
  const deterministic = view.adjudicationHeldOut?.["deterministic"];
  return (
    <section className={styles.experiments} aria-labelledby="arrivals-title">
      <div className={styles.kicker}>Recorded in the laboratory</div>
      <h2 id="arrivals-title" className={styles.title}>
        One amendment arrives in a portfolio of {grouped.format(portfolio.documentsAtStart)} documents
      </h2>
      <p className={styles.lede}>
        {view.whatThisIs} Each arrival below was measured once in the contract-lineage experiment and is replayed here from its result file
        {view.sourceCommit ? ` at commit ${shortHash(view.sourceCommit, 7)}` : ""}. The portfolio is {portfolio.source}.
      </p>
      <Figures
        label="The portfolio before any arrival"
        items={[
          { label: "Documents", value: portfolio.documentsAtStart },
          { label: "Families", value: portfolio.familiesAtStart },
          { label: "Findings", value: portfolio.findingsAtStart },
          { label: "Arrivals recorded", value: summary.arrivals },
          { label: "Unrelated families recomputed", value: summary.unrelatedFamiliesRecomputedTotal, note: "over every arrival" },
          { label: "Model calls", value: summary.modelAsksTotal, note: "left for a model to answer; none made" },
        ]}
      />
      {arrival && (
        <>
          <p className={styles.quiet} style={{ marginTop: 18 }}>
            <label htmlFor="arrival-pick">Arrival</label>{" "}
            <select id="arrival-pick" value={index} onChange={(event) => setIndex(Number(event.target.value))}>
              {view.arrivals.map((a, i) => (
                <option key={a.document.recordId} value={i}>
                  {titleOf(a.document)}
                  {a.document.date ? ` · ${a.document.date}` : ""}
                </option>
              ))}
            </select>
          </p>
          <Figures
            label="What this arrival touched"
            items={[
              {
                label: "Documents examined",
                value: arrival.documentsExamined,
                note: `of ${grouped.format(arrival.portfolioDocuments)} · ${percent(arrival.documentsExamined, arrival.portfolioDocuments)}`,
              },
              {
                label: "Relationship",
                value: arrival.relationship ? arrival.relationship.relation : "none bound",
                note: arrival.relationship ? "bound on cited language, agreement, date, parties, target" : "its own family of one",
              },
              { label: "Families rebuilt", value: arrival.familiesRebuilt, note: `${arrival.unrelatedFamiliesRecomputed} unrelated recomputed` },
              { label: "Sections changed", value: arrival.compositeSectionsChanged.length },
              { label: "Findings invalidated", value: arrival.findingsInvalidated.length, note: `${grouped.format(arrival.findingsPreserved)} preserved` },
              { label: "Model calls", value: arrival.modelCalls },
              { label: "Latency", value: `${Math.round(arrival.seconds * 1000)} ms` },
            ]}
          />
          <dl className={styles.expFacts} style={{ marginTop: 14 }}>
            <div>
              <dt>Arrived</dt>
              <dd>
                {titleOf(arrival.document)}
                {arrival.document.date ? `, dated ${arrival.document.date}` : ""}
                {arrival.document.filerName ? ` · filed by ${arrival.document.filerName}` : ""}
              </dd>
            </div>
            <div>
              <dt>Family</dt>
              <dd>
                {arrival.relationship
                  ? `${arrival.relationship.relation} ${titleOf(arrival.relationship.target)}${arrival.relationship.target.date ? `, dated ${arrival.relationship.target.date}` : ""}${
                      arrival.relationshipIsGold === true
                        ? " · the base the experiment's gold names"
                        : arrival.relationshipIsGold === false
                          ? " · not the base the experiment's gold names"
                          : ""
                    }`
                  : "No relationship bound; nothing else in the portfolio was touched."}
              </dd>
            </div>
            <div>
              <dt>Changed</dt>
              <dd>
                {arrival.compositeSectionsChanged.length
                  ? `${arrival.compositeSectionsChanged
                      .slice(0, 8)
                      .map((n) => `§${n}`)
                      .join(", ")}${arrival.compositeSectionsChanged.length > 8 ? ` and ${arrival.compositeSectionsChanged.length - 8} more` : ""}`
                  : "No section of the composite changed."}
              </dd>
            </div>
            <div>
              <dt>Findings</dt>
              <dd>
                {arrival.findingsInvalidated.length
                  ? `Stale: ${arrival.findingsInvalidated.slice(0, 8).map(sectionOf).join(", ")}${arrival.findingsInvalidated.length > 8 ? ` and ${arrival.findingsInvalidated.length - 8} more` : ""}; ${grouped.format(arrival.findingsPreserved)} preserved.`
                  : `None invalidated; ${grouped.format(arrival.findingsPreserved)} preserved.`}
              </dd>
            </div>
          </dl>
        </>
      )}
      <p className={styles.quiet} style={{ marginTop: 16 }}>
        Held out, in the same experiment:{" "}
        {hybrid
          ? `the reference-blind candidate generator reached the base within 10 for ${Math.round(100 * (hybrid["recall@10"] ?? 0))}% and within 20 for ${Math.round(100 * (hybrid["recall@20"] ?? 0))}% of amendments, examining ${hybrid.candidates_examined_per_query_mean ?? "–"} documents a query`
          : "no candidate-generation record"}
        {deterministic
          ? `; the deterministic adjudicator: precision ${deterministic.precision ?? "–"}, recall ${deterministic.recall ?? "–"}, false-family rate ${deterministic.false_family_rate ?? "–"} on ${deterministic.positives ?? "–"} positives and ${deterministic.hard_negatives ?? "–"} hard negatives.`
          : "."}
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
