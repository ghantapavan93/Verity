"use client";

import { useEffect, useState } from "react";
import styles from "../Workbench.module.css";
import { errorMessage, getRunExplanation } from "@/lib/api";
import { shortHash } from "@/lib/format";
import { statusLabel, type RunExplanationView } from "@/lib/types";

/**
 * Why this answer: the run explained from its record. The API assembles the explanation
 * (`GET /api/runs/{id}/explanation`); this component renders what it says happened and decides
 * nothing. The vocabulary is the domain model's: a ModelProposal is what the model wrote, a
 * SourceMatch is where code found a quote in the stored text, and a recorded PolicyEvaluation is
 * the status as it was decided when the run finished. No model is asked to explain itself.
 */
export function WhyThisAnswer({ runId, findingId = null }: { runId: string; findingId?: string | null }) {
  // The last explanation read, keyed by the run it belongs to; a different run id is a fresh read.
  const [read, setRead] = useState<{ runId: string; explanation: RunExplanationView | null; problem: string | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRunExplanation(runId)
      .then((explanation) => {
        if (!cancelled) setRead({ runId, explanation, problem: null });
      })
      .catch((error: unknown) => {
        if (!cancelled) setRead({ runId, explanation: null, problem: errorMessage(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const current = read && read.runId === runId ? read : null;
  if (current?.problem) return <p className={styles.whyProblem}>The explanation could not be read: {current.problem}</p>;
  if (!current?.explanation) return <p className={styles.whyLede}>Reading the run&apos;s record…</p>;
  return <Explanation explanation={current.explanation} findingId={findingId} />;
}

function yesNo(value: boolean | null | undefined): string {
  return value === null || value === undefined ? "not determined" : value ? "yes" : "no";
}

function Explanation({ explanation, findingId }: { explanation: RunExplanationView; findingId: string | null }) {
  const { reading, retrieval, reconstruction, reproducibility } = explanation;
  const findings = findingId ? explanation.findings.filter((f) => f.id === findingId) : explanation.findings;
  const ordinals = new Set(findings.map((f) => f.ordinal));
  const proposals = findingId ? explanation.proposals.filter((p) => ordinals.has(p.ordinal)) : explanation.proposals;
  const hasGuidance = reconstruction.hasGuidance;
  const approximate = reading.sections > 0 && reading.numberedSections < 3;

  return (
    <div className={styles.why} data-testid="why-this-answer">
      <p className={styles.whyLede}>Everything below is read from the run&apos;s record. No model was asked to explain itself.</p>

      <section className={styles.drawerSection}>
        <h4>What was read</h4>
        <dl className={styles.drawerFacts}>
          <div>
            <dt>Document</dt>
            <dd>
              {reading.documentName} · <span className={styles.whyMono}>{shortHash(reading.documentSha256)}</span>
            </dd>
          </div>
          <div>
            <dt>Reader</dt>
            <dd>{reading.readerVersion ?? "before reader versioning"}</dd>
          </div>
          <div>
            <dt>Structure</dt>
            <dd>
              {reading.pages ? `${reading.pages} page${reading.pages === 1 ? "" : "s"} · ` : ""}
              {reading.sections} section{reading.sections === 1 ? "" : "s"}
              {approximate ? " · little structure was found, so sections are approximate" : ""}
              {reading.trackedChanges ? ` · accepted view of ${reading.trackedChanges} tracked changes` : ""}
              {reading.hiddenRuns ? ` · ${reading.hiddenRuns} hidden runs left out` : ""}
            </dd>
          </div>
          <div>
            <dt>Coverage</dt>
            <dd>
              {reading.coverage
                ? reading.notRead.length > 0
                  ? `not read by this reading: ${reading.notRead.join(", ")}`
                  : "every part of the file with content was read"
                : "not recorded for this reading"}
              {reading.coverage ? ` (${reading.coverage.source}, reader ${reading.coverage.readerVersion})` : ""}
            </dd>
          </div>
        </dl>
      </section>

      <section className={styles.drawerSection}>
        <h4>What retrieval chose</h4>
        <table className={styles.whyTable}>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Label</th>
              <th>Section</th>
              <th>Shown to the model</th>
            </tr>
          </thead>
          <tbody>
            {retrieval.map((c) => (
              <tr key={c.label}>
                <td>{c.rank}</td>
                <td className={styles.whyMono}>{c.label}</td>
                <td>{c.number ? `§${c.number} · ${c.heading}` : c.heading}</td>
                <td>
                  {c.truncated === null
                    ? "not determined"
                    : c.truncated
                      ? `characters ${c.sliceStart}–${c.sliceEnd} of ${c.characters}; the rest was cut`
                      : `all ${c.characters} characters`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {reconstruction.charactersOutsideContext !== null && reconstruction.charactersOutsideContext > 0 && (
          <p className={styles.verifiedTag}>
            {reconstruction.charactersOutsideContext.toLocaleString()} characters across the selected sections were outside this run&apos;s model-visible
            context.
          </p>
        )}
      </section>

      <section className={styles.drawerSection}>
        <h4>What the model saw</h4>
        <dl className={styles.drawerFacts}>
          <div>
            <dt>Question</dt>
            <dd>{reconstruction.question}</dd>
          </div>
          <div>
            <dt>Guidance</dt>
            <dd>{hasGuidance ? "given, as stored on the run" : "none supplied"}</dd>
          </div>
          <div>
            <dt>Prompt</dt>
            <dd>
              {reconstruction.promptVersion} · <span className={styles.whyMono}>{shortHash(reconstruction.promptHash)}</span>
            </dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>
              {reconstruction.model}
              {Object.keys(reconstruction.options).length > 0
                ? ` · ${Object.entries(reconstruction.options)
                    .filter(([k]) => k !== "model")
                    .map(([k, v]) => `${k} ${v}`)
                    .join(" · ")}`
                : ""}
              {reconstruction.queueNote ? ` · ${reconstruction.queueNote}` : ""}
            </dd>
          </div>
          <div>
            <dt>Exact input</dt>
            <dd>
              {reconstruction.reconstructable
                ? `rebuilt from the record; it hashes to what the checking stage recorded (${shortHash(reconstruction.recordedInputSha256 ?? "")})`
                : `could not be rebuilt: ${reconstruction.problem ?? "no reason recorded"}`}
            </dd>
          </div>
        </dl>
      </section>

      <section className={styles.drawerSection}>
        <h4>What the model proposed</h4>
        <span className={styles.whyLabel}>ModelProposal</span>
        {explanation.proposalsProblem ? (
          <p className={styles.whyProblem}>{explanation.proposalsProblem}</p>
        ) : (
          proposals.map((p) => (
            <dl key={p.ordinal} className={styles.drawerFacts}>
              <div>
                <dt>Conclusion</dt>
                <dd>{p.conclusion}</dd>
              </div>
              <div>
                <dt>Hint</dt>
                <dd>{p.statusHint.replace(/_/g, " ")}</dd>
              </div>
              {p.observed && (
                <div>
                  <dt>Observed</dt>
                  <dd>{p.observed} (the model&apos;s words)</dd>
                </div>
              )}
              {p.required && (
                <div>
                  <dt>Required</dt>
                  <dd>{p.required} (the model&apos;s words)</dd>
                </div>
              )}
              <div>
                <dt>Evidence</dt>
                <dd>
                  {p.evidence.map((e, i) => (
                    <div key={i}>
                      cited <span className={styles.whyMono}>{e.citedLabel}</span>: “{e.quote}”
                    </div>
                  ))}
                </dd>
              </div>
            </dl>
          ))
        )}
      </section>

      {findings.map((f) => (
        <section key={f.id} className={styles.drawerSection}>
          <h4>What code established{findings.length > 1 ? `: ${f.topic}` : ""}</h4>
          <span className={styles.whyLabel}>SourceMatch</span>
          {f.sourceMatches.map((m, i) => (
            <dl key={i} className={styles.drawerFacts} data-testid="source-match">
              <div>
                <dt>Model cited</dt>
                <dd className={styles.whyMono}>{m.citedLabel || "—"}</dd>
              </div>
              <div>
                <dt>Located in</dt>
                <dd>
                  {m.verified ? (
                    <>
                      <span className={styles.whyMono}>{m.locatedLabel ?? "—"}</span>
                      {m.locatedHeading ? ` · ${m.locatedHeading}` : ""}
                      {m.relocated ? " (not where the model said)" : ""}
                    </>
                  ) : (
                    "not found in any section handed to the model; withheld"
                  )}
                </dd>
              </div>
              <div>
                <dt>Match</dt>
                <dd>{m.method}</dd>
              </div>
              {m.verified && (
                <>
                  <div>
                    <dt>Occurrences</dt>
                    <dd>{m.matchCount ?? "not recorded"}</dd>
                  </div>
                  <div>
                    <dt>Offsets</dt>
                    <dd>
                      {m.start}–{m.end}
                    </dd>
                  </div>
                  <div>
                    <dt>Inside model-visible context</dt>
                    <dd>{yesNo(m.insideModelVisibleContext)}</dd>
                  </div>
                </>
              )}
            </dl>
          ))}
          <span className={styles.whyLabel}>Recorded PolicyEvaluation</span>
          <dl className={styles.drawerFacts} data-testid="policy-evaluation">
            <div>
              <dt>Final status</dt>
              <dd>{statusLabel(f.recordedPolicyEvaluation.status, hasGuidance, f.recordedPolicyEvaluation.statusSource)}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd className={styles.whyMono}>{f.recordedPolicyEvaluation.statusSource || "—"}</dd>
            </div>
            <div>
              <dt>{f.recordedPolicyEvaluation.deterministic ? "Decided by code" : "Not decided by code"}</dt>
              <dd>{f.recordedPolicyEvaluation.statusReason ?? f.recordedPolicyEvaluation.summary}</dd>
            </div>
          </dl>
        </section>
      ))}

      <section className={styles.drawerSection}>
        <h4>Reproduce this run</h4>
        <dl className={styles.drawerFacts}>
          <div>
            <dt>Run</dt>
            <dd className={styles.whyMono}>{reproducibility.runId}</dd>
          </div>
          <div>
            <dt>Reading</dt>
            <dd>
              <span className={styles.whyMono}>{reproducibility.documentId}</span> · sha256{" "}
              <span className={styles.whyMono}>{shortHash(reproducibility.documentSha256)}</span> · reader {reproducibility.readerVersion ?? "unversioned"}
            </dd>
          </div>
          {reproducibility.guidanceSha256 && (
            <div>
              <dt>Guidance</dt>
              <dd className={styles.whyMono}>{shortHash(reproducibility.guidanceSha256)}</dd>
            </div>
          )}
          <div>
            <dt>Prompt</dt>
            <dd>
              {reproducibility.promptVersion} · <span className={styles.whyMono}>{shortHash(reproducibility.promptHash)}</span>
            </dd>
          </div>
          <div>
            <dt>Input hash</dt>
            <dd>
              <span className={styles.whyMono}>{reproducibility.recordedInputSha256 ? shortHash(reproducibility.recordedInputSha256) : "not recorded"}</span>
              {reproducibility.recordedInputSha256 ? (reproducibility.inputMatches ? " · rebuilt input matches" : " · rebuilt input does not match") : ""}
            </dd>
          </div>
          <div>
            <dt>Evidence pack</dt>
            <dd>available: the original bytes, the sections, every located span and a verify.py that checks them without this service</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
