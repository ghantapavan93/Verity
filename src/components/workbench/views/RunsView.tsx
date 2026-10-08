"use client";

/**
 * Runs: the engineering record. Every run keeps its hashes, prompt and model versions, decoding
 * options, the sections handed to the model, the raw structured output and how each quote was
 * verified. Below the runs sit the pre-registered experiments that preceded this product, read
 * from the ivo-experiments results file rather than retyped.
 */

import { useEffect, useState } from "react";
import wb from "../Workbench.module.css";
import { WhyThisAnswer } from "../assistant/WhyThisAnswer";
import { TERMINAL } from "../shell/constants";
import { StatusChip } from "../shell/primitives";
import styles from "./Views.module.css";
import { Figures, MethodBar } from "./Figures";
import { ListSkeleton, ReadFailed } from "./Skeleton";
import { ContractState } from "./ContractState";
import { absolute, getBatch, getCitations, getExperiments, getFamilies, getGoldens, getContractState, getRunDetail, listBatches, listRuns } from "@/lib/api";
import { formatClock, formatDelta, formatLatency, formatWhen, plural, shortHash } from "@/lib/format";
import {
  OUTCOME_LABELS,
  REASON_TITLES,
  STATUS_SOURCE_LABELS,
  retrievalNote,
  type BatchSummary,
  type BatchValue,
  type BatchView,
  type CitationRecord,
  type ExperimentsView,
  type FamiliesView,
  type GoldenRunView,
  type GoldensView,
  type GoldenVerdict,
  type ContractStateView,
  type RunDetailView,
  type RunStage,
  type RunSummary,
} from "@/lib/types";

function outcomeTone(stage: RunStage): string {
  return stage === "complete" ? wb.statusPass : stage === "failed" ? wb.statusBad : wb.statusMuted;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

interface TimingRow {
  step: string;
  ms: number;
}

/** Where the time went: the parse recorded at upload, then each stage's recorded duration (or the gap to the next stage on older runs). */
function timingRows(run: RunDetailView): TimingRow[] {
  const rows: TimingRow[] = [];
  if (run.documentParseMs != null) rows.push({ step: "Parse at upload", ms: run.documentParseMs });
  const names: Record<string, string> = {
    reading: "Load sections",
    finding_evidence: "Retrieve candidates",
    checking: "Model call",
    verifying: "Verify quotes and persist",
  };
  for (let i = 0; i < run.stages.length; i += 1) {
    const row = run.stages[i];
    const step = names[row.stage];
    if (!step) continue;
    const recorded = row.durationMs;
    const next = run.stages[i + 1];
    const ms = recorded != null ? recorded : next ? new Date(next.at).getTime() - new Date(row.at).getTime() : Number.NaN;
    if (Number.isFinite(ms)) rows.push({ step, ms });
  }
  return rows;
}

// The commit the interface was built from, set by deploy/install-supervision.ps1 at build time; absent in a dev build.
const BUILD_SHA = process.env.NEXT_PUBLIC_BUILD_SHA ?? "";

export function RunsView({
  notice,
  currentRunId = null,
  onOpenRun,
}: {
  notice: string | null;
  currentRunId?: string | null;
  onOpenRun: (runId: string) => void;
}) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [experiments, setExperiments] = useState<ExperimentsView | null>(null);
  const [contractState, setContractState] = useState<ContractStateView | null>(null);
  const [goldens, setGoldens] = useState<GoldensView | null>(null);
  const [citations, setCitations] = useState<CitationRecord | null>(null);
  const [batches, setBatches] = useState<BatchSummary[] | null>(null);
  const [families, setFamilies] = useState<FamiliesView | null>(null);
  const [selected, setSelected] = useState<RunDetailView | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listRuns()
      .then((rows) => !cancelled && setRuns(rows))
      .catch((e: unknown) => !cancelled && setError(message(e)));
    getExperiments()
      .then((view) => !cancelled && setExperiments(view))
      .catch(
        () =>
          !cancelled &&
          setExperiments({
            available: false,
            pageUrl: null,
            source: null,
            detail: "The experiment records could not be loaded.",
            page: {},
            repoHead: null,
            generatedAt: null,
            board: [],
            baselines: [],
          }),
      );
    getContractState()
      .then((view) => !cancelled && setContractState(view))
      .catch(
        () =>
          !cancelled &&
          setContractState({
            available: false,
            source: null,
            detail: "The contract-state record could not be loaded.",
            evidence: {},
            arrivals: [],
          }),
      );
    getCitations()
      .then((record) => !cancelled && setCitations(record))
      .catch(() => !cancelled && setCitations(null));
    listBatches()
      .then((rows) => !cancelled && setBatches(rows))
      .catch(() => !cancelled && setBatches([]));
    getFamilies()
      .then((view) => !cancelled && setFamilies(view))
      .catch(() => !cancelled && setFamilies(null));
    getGoldens()
      .then((view) => !cancelled && setGoldens(view))
      .catch(
        () =>
          !cancelled &&
          setGoldens({
            available: false,
            detail: "The golden set could not be loaded.",
            setSha256: "",
            documentName: "",
            rules: "",
            categories: {},
            goldens: [],
            prompts: [],
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const select = async (id: string) => {
    setLoadingId(id);
    setError(null);
    try {
      setSelected(await getRunDetail(id));
    } catch (e) {
      setError(message(e));
    } finally {
      setLoadingId(null);
    }
  };

  if (selected) {
    return (
      <div className={styles.pane}>
        <div className={styles.inner}>
          <RunRecord run={selected} onBack={() => setSelected(null)} onOpen={() => onOpenRun(selected.id)} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.pane}>
      <div className={styles.inner}>
        <div className={styles.kicker}>Runs</div>
        <h1 className={styles.title}>
          Every model run, as recorded
          {runs && (
            <span className={styles.count}>
              {/* The list is the API's latest page; when the record holds more, the count says which part is shown. */}
              {citations && citations.runs > runs.length ? `latest ${runs.length}` : runs.length}
            </span>
          )}
        </h1>
        <p className={styles.lede}>
          A run stores the document and guidance hashes, the prompt version and hash, the decoding options, the sections handed to the model, the raw structured
          output and how each quoted passage was verified. Nothing is summarised away.
        </p>
        {citations && citations.runs > 0 && (
          <>
            <Figures
              label="The citation record"
              items={[
                {
                  label: "Runs where the model answered",
                  value: citations.runs,
                  note: citations.firstRunAt ? `since ${formatWhen(citations.firstRunAt)}` : undefined,
                },
                { label: "Quoted passages", value: citations.spans },
                { label: "Found verbatim", value: citations.verifiedSpans },
                { label: "Findings withheld", value: citations.withheldFindings, note: `of ${citations.findings.toLocaleString("en-US")} findings` },
              ]}
            />
            <MethodBar record={citations} />
          </>
        )}
        {BUILD_SHA && (
          <p className={styles.quiet} data-testid="build-identity">
            Interface built from commit <code>{BUILD_SHA.slice(0, 12)}</code>; the API record names the reader, verifier, prompt and model of each run.
          </p>
        )}
        {notice && <p className={styles.notice}>{notice}</p>}
        {error && !runs && (
          <ReadFailed
            what="the runs"
            error={error}
            onRetry={() => {
              setError(null);
              setAttempt((n) => n + 1);
            }}
          />
        )}
        {error && runs && <p className={styles.notice}>{error}</p>}
        {!runs && !error && <ListSkeleton rows={8} label="Runs" />}

        <nav className={styles.jump} aria-label="On this page">
          <a href="#runs">Runs</a>
          {goldens && <a href="#golden-set">Golden set</a>}
          {batches && <a href="#batches">Batch extraction</a>}
          {families && <a href="#families">Document families</a>}
          {contractState && <a href="#contract-state">One contract changes</a>}
          {experiments && <a href="#experiments">Before this product</a>}
        </nav>

        <div id="runs" className={styles.anchor} />
        {runs && runs.length === 0 && (
          <div className={styles.empty}>
            <p>No runs yet. Open a contract and ask it a question.</p>
          </div>
        )}

        {runs && runs.length > 0 && (
          <ul className={styles.list}>
            {runs.map((r, i) => (
              <li key={r.id}>
                <button type="button" className={`${styles.row} ${styles.indexed}`} onClick={() => void select(r.id)} aria-busy={loadingId === r.id}>
                  <span className={styles.rowIndex} aria-hidden="true">
                    {String(runs.length - i).padStart(3, "0")}
                  </span>
                  <div className={styles.rowMain}>
                    <div className={styles.rowTitle}>
                      <span className={styles.rowTitleText}>{r.question}</span>
                      {r.id === currentRunId && <span className={`${wb.statusChip} ${wb.statusPass}`}>On screen</span>}
                      {r.shared && <span className={styles.fileType}>curated</span>}
                    </div>
                    <div className={styles.rowMeta}>
                      <span>{r.documentName}</span>
                      <span>{r.model}</span>
                      <span>prompt {r.promptVersion}</span>
                      {r.latencyMs !== null && <span>{formatLatency(r.latencyMs)}</span>}
                      <span>{plural(r.findings, "finding")}</span>
                      {r.hasGuidance && <span>with guidance</span>}
                      <span>{formatWhen(r.createdAt)}</span>
                    </div>
                  </div>
                  <div className={styles.rowSide}>
                    <span className={`${wb.statusChip} ${outcomeTone(r.stage)}`}>
                      {TERMINAL.includes(r.stage) ? OUTCOME_LABELS[r.stage] : `${OUTCOME_LABELS[r.stage]} · in progress`}
                    </span>
                    <span className={styles.mono}>{r.id}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}

        {goldens && (
          <div id="golden-set" className={styles.anchor}>
            <GoldenSet view={goldens} onOpenRun={(id) => void select(id)} />
          </div>
        )}
        {batches && (
          <div id="batches" className={styles.anchor}>
            <Batches batches={batches} onOpenRun={(id) => void select(id)} />
          </div>
        )}
        {families && (
          <div id="families" className={styles.anchor}>
            <Families view={families} />
          </div>
        )}
        {contractState && (
          <div id="contract-state" className={styles.anchor}>
            <ContractState view={contractState} />
          </div>
        )}
        {experiments && (
          <div id="experiments" className={styles.anchor}>
            <Experiments view={experiments} />
          </div>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------ record

/** Where the time went, each step drawn to scale against the longest: the model call is the bar that fills the row. */
function TimingTable({ rows }: { rows: TimingRow[] }) {
  const longest = Math.max(1, ...rows.map((row) => row.ms));
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Step</th>
          <th className={styles.timingBarHead}>Share of the wait</th>
          <th>Time</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.step}>
            <td>{row.step}</td>
            <td className={styles.timingBarCell}>
              <span className={styles.timingBar} style={{ width: `${Math.max(0.6, (row.ms / longest) * 100)}%` }} aria-hidden="true" />
            </td>
            <td>{formatLatency(row.ms)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RunRecord({ run, onBack, onOpen }: { run: RunDetailView; onBack: () => void; onOpen: () => void }) {
  const first = run.stages[0]?.at;
  const options = Object.entries(run.options ?? {});
  return (
    <>
      <button type="button" className={styles.back} onClick={onBack}>
        <span aria-hidden="true">←</span> All runs
      </button>
      <div className={styles.recordHead}>
        <div>
          <div className={styles.kicker}>
            Run <span className={styles.kickerId}>{run.id}</span>
          </div>
          <h1 className={styles.recordTitle}>{run.question}</h1>
        </div>
        <span className={`${wb.statusChip} ${outcomeTone(run.stage)}`}>{OUTCOME_LABELS[run.stage]}</span>
      </div>

      <dl className={styles.facts}>
        <div>
          <dt>Document</dt>
          <dd>
            <span className={styles.mono}>{run.documentSha256}</span>
          </dd>
        </div>
        <div>
          <dt>Guidance</dt>
          <dd>{run.guidanceSha256 ? <span className={styles.mono}>{run.guidanceSha256}</span> : "none supplied"}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>
            {run.model} via {run.provider}
            {run.task ? ` · task ${run.task.replace(/_/g, " ")}` : ""}
            {run.routingReason ? <span className={styles.factNote}>{run.routingReason}</span> : null}
          </dd>
        </div>
        <div>
          <dt>Prompt</dt>
          <dd>
            {run.promptVersion} · <span className={styles.mono}>{run.promptHash}</span>
          </dd>
        </div>
        {options.length > 0 && (
          <div>
            <dt>Options</dt>
            <dd>{options.map(([k, v]) => `${k} ${v}`).join(" · ")}</dd>
          </div>
        )}
        <div>
          <dt>Tokens</dt>
          <dd>{run.inputTokens !== null || run.outputTokens !== null ? `${run.inputTokens ?? "?"} in · ${run.outputTokens ?? "?"} out` : "not reported"}</dd>
        </div>
        <div>
          <dt>Citations</dt>
          <dd>{run.totalSpans > 0 ? `${run.verifiedSpans} of ${run.totalSpans} found in the document text` : "none proposed"}</dd>
        </div>
        <div>
          <dt>Model latency</dt>
          <dd>{run.latencyMs !== null ? formatLatency(run.latencyMs) : "not recorded"}</dd>
        </div>
        {run.reason && (
          <div>
            <dt>Outcome</dt>
            <dd>{REASON_TITLES[run.reason] ?? run.reason}</dd>
          </div>
        )}
        <div>
          <dt>Started</dt>
          <dd>{formatWhen(run.createdAt)}</dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd>{run.finishedAt ? formatWhen(run.finishedAt) : "still running"}</dd>
        </div>
        {(run.note || run.error) && (
          <div>
            <dt>{run.error ? "Error" : "Note"}</dt>
            <dd>{run.error ?? run.note}</dd>
          </div>
        )}
      </dl>

      <div style={{ marginTop: 18, display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
        <button type="button" className={wb.primaryButton} onClick={onOpen}>
          Open in workspace
        </button>
        <a
          className={wb.actionLink}
          href={absolute(`/api/runs/${run.id}/evidence-pack`)}
          title="The original bytes, the sections, every located span and a verify.py that checks them without this service"
        >
          Download evidence pack
        </a>
      </div>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Stages</h2>
        <ol className={styles.timeline}>
          {run.stages.map((s, i) => (
            <li key={`${s.stage}-${i}`}>
              <span className={styles.tlStage}>{OUTCOME_LABELS[s.stage] ?? s.stage}</span>
              <span className={styles.tlAt}>{i === 0 || !first ? formatClock(s.at) : formatDelta(first, s.at)}</span>
              <span className={styles.tlDetail}>
                {s.detail ?? ""}
                {s.status === "failed" && s.errorCode ? ` · failed: ${s.errorCode}` : ""}
                {s.status === "running" ? " · running" : ""}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          Timing <span className={styles.sectionNote}>measured on this run; the model call is the whole wait</span>
        </h2>
        <TimingTable rows={timingRows(run)} />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          Sections handed to the model <span className={styles.sectionNote}>{retrievalNote(run.retrievalMode)}</span>
        </h2>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Label</th>
              <th>Section</th>
            </tr>
          </thead>
          <tbody>
            {run.candidates.map((c) => (
              <tr key={c.label}>
                <td className={styles.mono}>{c.label}</td>
                <td>{c.number ? `§${c.number} · ${c.heading}` : c.heading}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          Findings <span className={styles.sectionNote}>including any that did not verify</span>
        </h2>
        {run.findings.length === 0 && <p className={styles.quiet}>The model returned no findings for this run.</p>}
        {run.findings.map((f) => (
          <article key={f.id} className={styles.finding}>
            <div className={styles.findingHead}>
              <span>{f.topic}</span>
              <StatusChip status={f.status} hasGuidance={run.hasGuidance} source={f.statusSource} />
            </div>
            <p className={styles.findingText}>{f.conclusion}</p>
            <p className={styles.quiet}>{STATUS_SOURCE_LABELS[f.statusSource] ?? f.statusSource}</p>
            {f.spans.map((s, i) => (
              <div key={i} className={styles.span}>
                <div className={styles.spanMeta}>
                  <span>
                    cited <strong className={styles.mono}>{s.citedSectionLabel || "no label"}</strong>
                  </span>
                  <span>
                    located <strong>{s.verified ? `${s.method} · offsets ${s.start} to ${s.end}` : "not found"}</strong>
                  </span>
                </div>
                <p className={styles.quote}>{s.quote}</p>
              </div>
            ))}
          </article>
        ))}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          Raw model output <span className={styles.sectionNote}>structured JSON under a fixed schema; no chain-of-thought is requested or stored</span>
        </h2>
        <pre className={styles.raw}>{run.rawOutput ?? "(none)"}</pre>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          Why this answer?{" "}
          <span className={styles.sectionNote}>
            the run explained from its record by the API: what was read, what retrieval chose, what the model saw and proposed, what code established
          </span>
        </h2>
        <WhyThisAnswer runId={run.id} />
      </section>
    </>
  );
}

// ------------------------------------------------------------------------------ golden set

const VERDICT_LABELS: Record<GoldenVerdict, string> = { pass: "Pass", fail: "Fail", missing: "Not run" };
const CHANGE_LABELS = { better: "Better", worse: "Worse", same: "Same" } as const;

function verdictTone(verdict: GoldenVerdict): string {
  return verdict === "pass" ? wb.statusPass : verdict === "fail" ? wb.statusReview : wb.statusMuted;
}

function changeTone(change: keyof typeof CHANGE_LABELS): string {
  return change === "better" ? wb.statusPass : change === "worse" ? wb.statusReview : wb.statusMuted;
}

/** Fixed questions about the sample, judged by code against each prompt version's recorded run. Shows the verdicts; decides nothing. */
function GoldenSet({ view, onOpenRun }: { view: GoldensView; onOpenRun: (runId: string) => void }) {
  const goldens = view.goldens ?? [];
  const prompts = view.prompts ?? [];
  const compare = view.compare ?? null;
  const runsByVersion = new Map(prompts.map((p) => [p.version, new Map(p.runs.map((r) => [r.goldenId, r]))]));
  const deltas = new Map((compare?.rows ?? []).map((r) => [r.goldenId, r]));
  return (
    <section className={styles.goldens}>
      <div className={styles.kicker}>Golden set</div>
      <h2 className={styles.title}>
        The same questions, every prompt version
        {goldens.length > 0 && <span className={styles.count}>{goldens.length}</span>}
      </h2>
      <p className={styles.lede}>
        {view.rules} Verdicts are computed by code from the run records. A prompt or retrieval change is kept only when this table moves in its favour and no
        passing golden regresses; a change that moves nothing is dropped, or the set is extended until it can see it.
      </p>
      {prompts.length === 0 ? (
        <p className={styles.quiet}>{view.detail}</p>
      ) : (
        <>
          <p className={styles.quiet}>
            {prompts
              .map(
                (p) =>
                  `${p.version}: ${p.passes} of ${p.recorded} pass${p.meanLatencyMs != null ? `, mean model latency ${(p.meanLatencyMs / 1000).toFixed(0)} s` : ""}`,
              )
              .join(" · ")}
            {compare &&
              ` · ${compare.head} against ${compare.base}: ${compare.better} better, ${compare.worse} worse, ${compare.same} same, ${compare.changed} with different citations or statuses${
                compare.latencyDeltaMs != null ? `, latency ${compare.latencyDeltaMs >= 0 ? "+" : ""}${(compare.latencyDeltaMs / 1000).toFixed(1)} s` : ""
              }`}
          </p>
          {prompts[prompts.length - 1].byCategory.length > 0 && (
            <p className={styles.quiet}>
              {prompts[prompts.length - 1].version} by category:{" "}
              {prompts[prompts.length - 1].byCategory.map((c) => `${c.category.replace(/_/g, " ")} ${c.passes}/${c.recorded}`).join(" · ")}
            </p>
          )}
          <table className={styles.table} style={{ marginTop: 14 }}>
            <thead>
              <tr>
                <th>#</th>
                <th>Question</th>
                {compare ? (
                  <>
                    <th>Previous answer · {compare.base}</th>
                    <th>New answer · {compare.head}</th>
                    <th>What changed</th>
                    <th>Better or worse</th>
                  </>
                ) : (
                  <>
                    <th>Expect</th>
                    {prompts.map((p) => (
                      <th key={p.version}>{p.version}</th>
                    ))}
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {goldens.map((g) => {
                const delta = deltas.get(g.id);
                const sections = g.expect.sections ?? [];
                const expect = g.expect.kind === "present" ? `expects a verified citation in §${sections.join(", §")}` : "expects nothing asserted";
                const previous = compare ? runsByVersion.get(compare.base)?.get(g.id) : undefined;
                const next = compare ? runsByVersion.get(compare.head)?.get(g.id) : undefined;
                return (
                  <tr key={g.id}>
                    <td className={styles.mono}>{g.id}</td>
                    <td>
                      {g.question}
                      <div className={styles.cellNote}>
                        {g.category ? `${g.category.replace(/_/g, " ")} · ` : ""}
                        {expect}
                        {g.expect.status ? ` with status ${g.expect.status.replace("_", " ")}` : ""} · {g.why}
                        {g.guidance ? ` · guidance: ${g.guidance}` : ""}
                      </div>
                    </td>
                    {compare ? (
                      <>
                        <td>{previous ? <VerdictCell run={previous} onOpenRun={onOpenRun} /> : <span className={styles.mono}>none</span>}</td>
                        <td>{next ? <VerdictCell run={next} onOpenRun={onOpenRun} /> : <span className={styles.mono}>none</span>}</td>
                        <td className={styles.cellNote}>{whatChanged(previous, next)}</td>
                        <td>
                          {delta && (
                            <>
                              <span className={`${wb.statusChip} ${changeTone(delta.change)}`}>{CHANGE_LABELS[delta.change]}</span>
                              {delta.change === "same" && delta.changed && <div className={styles.cellNote}>same verdict, different citations or statuses</div>}
                            </>
                          )}
                        </td>
                      </>
                    ) : (
                      <>
                        <td>{g.expect.kind === "present" ? `present · §${sections.join(", §")}` : "absent"}</td>
                        {prompts.map((p) => {
                          const run = runsByVersion.get(p.version)?.get(g.id);
                          return <td key={p.version}>{run ? <VerdictCell run={run} onOpenRun={onOpenRun} /> : <span className={styles.mono}>none</span>}</td>;
                        })}
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className={styles.quiet}>
            Set <span className={styles.mono}>{shortHash(view.setSha256)}</span> · sample {view.documentName}{" "}
            <span className={styles.mono}>{shortHash(view.documentSha256)}</span>
            {prompts.map((p) => (
              <span key={p.version}>
                {" · "}
                {p.version} <span className={styles.mono}>{shortHash(p.hash)}</span>
              </span>
            ))}
          </p>
        </>
      )}
    </section>
  );
}

/** The section numbers a golden run cited, from the API's "5.3.1 exact" labels. */
function citedNumbers(run: GoldenRunView): string {
  return run.cited.length ? run.cited.map((c) => `§${c.split(" ")[0]}`).join(", ") : "nothing";
}

/** What differs between two recorded answers to the same golden, in the reviewer's own terms. */
function whatChanged(previous: GoldenRunView | undefined, next: GoldenRunView | undefined): string {
  if (!previous || !next) return "not recorded under both versions";
  const parts: string[] = [];
  if (previous.verdict !== next.verdict) parts.push(`${VERDICT_LABELS[previous.verdict]} → ${VERDICT_LABELS[next.verdict]}`);
  if (previous.stage !== next.stage) parts.push(`${previous.stage ?? "none"} → ${next.stage ?? "none"}`);
  const statuses = (run: GoldenRunView) => (run.statuses.length ? run.statuses.join("/") : "no finding");
  if (statuses(previous) !== statuses(next)) parts.push(`status ${statuses(previous)} → ${statuses(next)}`);
  if (citedNumbers(previous) !== citedNumbers(next)) parts.push(`cited ${citedNumbers(previous)} → ${citedNumbers(next)}`);
  return parts.length ? parts.join(" · ") : "same outcome, citations and statuses";
}

function VerdictCell({ run, onOpenRun }: { run: GoldenRunView; onOpenRun: (runId: string) => void }) {
  const runId = run.runId;
  const chip = <span className={`${wb.statusChip} ${verdictTone(run.verdict)}`}>{VERDICT_LABELS[run.verdict]}</span>;
  return (
    <>
      {runId ? (
        <button type="button" className={styles.chipButton} onClick={() => onOpenRun(runId)} title={`Open run ${runId}`}>
          {chip}
        </button>
      ) : (
        chip
      )}
      <div className={styles.cellNote}>
        {run.because}
        {run.runId ? ` · cited ${citedNumbers(run)}` : ""}
      </div>
    </>
  );
}

// ------------------------------------------------------------------------------ batch extraction

const VALUE_LABELS: Record<BatchValue["outcome"], string> = {
  answered: "Answered",
  not_found: "Not found",
  withheld: "Withheld",
  failed: "Failed",
  in_progress: "In progress",
};

function valueTone(outcome: BatchValue["outcome"]): string {
  return outcome === "answered" ? wb.statusPass : outcome === "withheld" || outcome === "failed" ? wb.statusReview : wb.statusMuted;
}

/** Field extraction over a corpus, as recorded: the batches, and for the open one its numbers and every value with its citation. */
function Batches({ batches, onOpenRun }: { batches: BatchSummary[]; onOpenRun: (runId: string) => void }) {
  const [open, setOpen] = useState<BatchView | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const show = async (id: string) => {
    setLoadingId(id);
    setError(null);
    try {
      setOpen(await getBatch(id));
    } catch (e) {
      setError(message(e));
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <section className={styles.goldens}>
      <div className={styles.kicker}>Batch extraction</div>
      <h2 className={styles.title}>
        The same run, over a corpus
        {batches.length > 0 && <span className={styles.count}>{batches.length}</span>}
      </h2>
      <p className={styles.lede}>
        A batch asks the same field questions of every contract in a corpus, through the same run and the same verification, with a bound on how many are in
        flight. The numbers are computed from the run records: throughput, model latency, invalid output, verified citations, withheld findings, reuse and
        retries. Batches start from the command line, never from here.
      </p>
      {error && <p className={styles.notice}>{error}</p>}
      {batches.length === 0 && <p className={styles.quiet}>No batch recorded yet.</p>}
      {batches.length > 0 && (
        <ul className={styles.list}>
          {batches.map((b) => (
            <li key={b.id}>
              <button type="button" className={styles.row} onClick={() => void show(b.id)} aria-busy={loadingId === b.id}>
                <div className={styles.rowMain}>
                  <div className={styles.rowTitle}>
                    {b.task} · {b.corpus}
                  </div>
                  <div className={styles.rowMeta}>
                    <span>{plural(b.documents, "document")}</span>
                    <span>{plural(b.requested, "value")} requested</span>
                    <span>{b.model}</span>
                    <span>concurrency {b.concurrency}</span>
                    <span>{b.finishedAt ? `finished ${formatWhen(b.finishedAt)}` : `started ${formatWhen(b.startedAt)} · in progress`}</span>
                  </div>
                </div>
                <div className={styles.rowSide}>
                  <span className={styles.mono}>{b.id}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>
            {open.task} over {open.corpus}{" "}
            <span className={styles.sectionNote}>
              {open.documents} documents · {open.runsCreated} runs made, {open.runsReused} reused · {open.wallMinutes} min
            </span>
          </h3>
          <dl className={styles.facts}>
            <div>
              <dt>Throughput</dt>
              <dd>{open.documentsPerMinute != null ? `${open.documentsPerMinute} documents/min · ${open.valuesPerMinute} values/min` : "still running"}</dd>
            </div>
            <div>
              <dt>Answered</dt>
              <dd>
                {open.answered} of {open.requested}
              </dd>
            </div>
            <div>
              <dt>Model latency</dt>
              <dd>
                {open.modelLatencyP50Ms != null
                  ? `p50 ${formatLatency(open.modelLatencyP50Ms)} · p95 ${formatLatency(open.modelLatencyP95Ms ?? 0)} · mean ${formatLatency(open.modelLatencyMeanMs ?? 0)}`
                  : "no new model calls"}
              </dd>
            </div>
            <div>
              <dt>Citations</dt>
              <dd>
                {open.verifiedSpans} of {open.spans} found in the document text · {open.withheldFindings} of {open.findings} findings withheld
              </dd>
            </div>
            <div>
              <dt>Failures</dt>
              <dd>
                {Object.keys(open.failedRunsByReason).length === 0
                  ? "none"
                  : Object.entries(open.failedRunsByReason)
                      .map(([reason, count]) => `${count} ${reason}`)
                      .join(" · ")}
                {open.retries > 0 ? ` · ${plural(open.retries, "model call")} retried` : ""}
              </dd>
            </div>
            <div>
              <dt>Values</dt>
              <dd>
                <a className={wb.actionLink} href={absolute(`/api/batches/${open.id}/values.csv`)}>
                  Download as CSV
                </a>
              </dd>
            </div>
          </dl>
          <table className={styles.table} style={{ marginTop: 14 }}>
            <thead>
              <tr>
                <th>Document</th>
                {open.fields.map((f) => (
                  <th key={f.key} title={f.question}>
                    {f.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {open.rows.map((row) => (
                <tr key={row.documentId}>
                  <td>{row.documentName}</td>
                  {open.fields.map((f) => {
                    const value = row.values[f.key];
                    return (
                      <td key={f.key}>
                        {value.runId ? (
                          <button type="button" className={styles.chipButton} onClick={() => onOpenRun(value.runId)} title={`Open run ${value.runId}`}>
                            <span className={`${wb.statusChip} ${valueTone(value.outcome)}`}>{VALUE_LABELS[value.outcome]}</span>
                          </button>
                        ) : (
                          <span className={`${wb.statusChip} ${valueTone(value.outcome)}`}>{VALUE_LABELS[value.outcome]}</span>
                        )}
                        <div className={styles.cellNote} title={value.value ?? undefined}>
                          {value.citation ? `${value.citation} · ` : ""}
                          {value.value ? (value.value.length > 90 ? `${value.value.slice(0, 87).trimEnd()}…` : value.value) : (value.reason ?? "")}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------------------------ document families

/** Structural families among the labeled corpus, with the evaluation against the labels. Deterministic; no model. */
function Families({ view }: { view: FamiliesView }) {
  const grouped = (view.families ?? []).filter((f) => f.members.length > 1);
  const singles = (view.families ?? []).filter((f) => f.members.length === 1);
  return (
    <section className={styles.goldens}>
      <div className={styles.kicker}>Document families</div>
      <h2 className={styles.title}>
        Which contracts belong together, from structure alone
        {view.available && <span className={styles.count}>{view.documents}</span>}
      </h2>
      <p className={styles.lede}>
        Each document is fingerprinted three ways (its normalised headings, the terms it defines, word shingles over its text), pairs are scored by exact
        Jaccard with fixed weights, and families are single-linkage clusters at a threshold. Every number here is pairwise against hand labels for a public
        corpus; the threshold sweep is reported so the chosen value is a fact about this corpus, not a claim about another.
      </p>
      {!view.available ? (
        <p className={styles.quiet}>{view.detail}</p>
      ) : (
        <>
          <p className={styles.quiet}>
            threshold {view.threshold} · weights{" "}
            {Object.entries(view.weights ?? {})
              .map(([k, v]) => `${k} ${v}`)
              .join(", ")}
            {view.missing.length > 0 ? ` · not in the store: ${view.missing.join(", ")}` : ""}
          </p>
          <table className={styles.table} style={{ marginTop: 14 }}>
            <thead>
              <tr>
                <th>Family</th>
                <th>Members</th>
                <th>Similarity within</th>
              </tr>
            </thead>
            <tbody>
              {grouped.map((f) => (
                <tr key={f.members.join("+")}>
                  <td className={styles.mono}>{f.members.length} documents</td>
                  <td>
                    {f.members.join(", ")}
                    <div className={styles.cellNote}>{f.titles.join(" · ")}</div>
                  </td>
                  <td>{f.minSimilarity != null ? `${f.minSimilarity.toFixed(2)} to ${(f.maxSimilarity ?? f.minSimilarity).toFixed(2)}` : "not measured"}</td>
                </tr>
              ))}
              {singles.length > 0 && (
                <tr>
                  <td className={styles.mono}>on their own</td>
                  <td>{singles.map((f) => f.members[0]).join(", ")}</td>
                  <td>none</td>
                </tr>
              )}
            </tbody>
          </table>
          <table className={styles.table} style={{ marginTop: 14 }}>
            <thead>
              <tr>
                <th>Label set</th>
                <th>Labeled pairs</th>
                <th>At {view.threshold}</th>
                <th>Best F1 in the sweep</th>
              </tr>
            </thead>
            <tbody>
              {view.evaluations.map((e) => (
                <tr key={e.labelSet}>
                  <td>
                    {e.labelSet}
                    <div className={styles.cellNote}>{e.description}</div>
                  </td>
                  <td>{e.labeledPairs}</td>
                  <td>
                    precision {e.precision.toFixed(2)} · recall {e.recall.toFixed(2)} · F1 {e.f1.toFixed(2)}
                  </td>
                  <td>
                    {e.bestF1.toFixed(2)} at {e.bestThreshold}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className={styles.quiet}>
            Closest pairs:{" "}
            {view.pairs
              .slice(0, 6)
              .map((p) => `${p.a} and ${p.b} ${p.combined.toFixed(2)}${p.labeled ? " (labeled suite)" : ""}`)
              .join(" · ")}
          </p>
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------------------------ experiments

function Experiments({ view }: { view: ExperimentsView }) {
  const page = view.page ?? {};
  return (
    <section className={styles.experiments}>
      <div className={styles.kicker}>Before this product</div>
      <h2 className={styles.title}>{page.title ?? "Pre-registered experiments"}</h2>
      {view.available ? (
        <>
          <p className={styles.lede}>
            {page.subtitle ? `${page.subtitle}. ` : ""}
            Three product ideas were tested against pre-registered kill rules before any of this was built; each was killed by its own rule. Records are read
            from the experiments repository
            {view.repoHead ? ` at commit ${view.repoHead}` : ""}.
          </p>
          <div className={styles.list} style={{ marginTop: 18 }}>
            {view.board.map((r) => (
              <div key={r.id} className={styles.expRow}>
                <span className={styles.expCode}>{r.code}</span>
                <span className={styles.expTitle}>
                  {r.title}
                  {view.pageUrl && (
                    <>
                      {" "}
                      <a className={wb.actionLink} href={`${view.pageUrl.replace(/\/$/, "")}/#${r.id}`} target="_blank" rel="noreferrer">
                        Open experiment
                      </a>
                    </>
                  )}
                </span>
                <span className={`${wb.statusChip} ${wb.statusMuted}`}>Killed {r.date}</span>
                <dl className={styles.expFacts}>
                  {r.expected && (
                    <div>
                      <dt>Expected</dt>
                      <dd>{r.expected}</dd>
                    </div>
                  )}
                  <div>
                    <dt>Kill rule</dt>
                    <dd>{r.gate}</dd>
                  </div>
                  <div>
                    <dt>Observed</dt>
                    <dd>{r.observed}</dd>
                  </div>
                </dl>
              </div>
            ))}
          </div>
          {view.baselines.length > 0 && (
            <p className={styles.quiet}>
              Before the three, two prompt baselines set their shape:{" "}
              {view.baselines.map((b, i) => `${b.title.toLowerCase()} went ${b.observed}${i < view.baselines.length - 1 ? "; " : "."}`).join("")}
            </p>
          )}
          <p className={styles.quiet}>
            Source:{" "}
            {page.repoUrl ? (
              <a className={wb.actionLink} href={page.repoUrl} target="_blank" rel="noreferrer">
                {page.repoUrl}
              </a>
            ) : (
              <span>the experiments repository, read from its results file</span>
            )}
            {view.generatedAt ? ` · built ${formatWhen(view.generatedAt)}` : ""}
            {view.repoHead ? ` · ${shortHash(view.repoHead, 7)}` : ""}
          </p>
        </>
      ) : (
        <p className={styles.quiet}>Experiment records are not connected. {view.detail}</p>
      )}
    </section>
  );
}
