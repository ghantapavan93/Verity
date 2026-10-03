"use client";

/**
 * The workbench coordinates layout and shell state: which surface is on screen, which document
 * and run are open, what is highlighted, what the palette can do. Feature behaviour lives beside
 * its feature (hooks/, assistant/, workspace/, landing/, views/); domain decisions live in the API.
 *
 * The document is the source of truth on screen; the Assistant is secondary. Nothing on the
 * primary path is simulated: uploads are parsed by the API, runs are model runs, and every
 * citation shown was verified verbatim by the API before it arrived here.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CommandPalette, type Command } from "./CommandPalette";
import styles from "./Workbench.module.css";
import { AccessGate } from "./access/AccessGate";
import { ASSISTANT_SUGGESTIONS, AssistantPanel } from "./assistant/AssistantPanel";
import { outcomeTitle } from "./assistant/RunOutcome";
import { useDocWidth } from "./hooks/useDocWidth";
import { useDropZone } from "./hooks/useDropZone";
import { DEFAULT_GUIDANCE, useGuidance } from "./hooks/useGuidance";
import { useHighlightScroll } from "./hooks/useHighlightScroll";
import { useMemoAction } from "./hooks/useMemoAction";
import { useRunFollower } from "./hooks/useRunFollower";
import { useUrlState } from "./hooks/useUrlState";
import { Landing } from "./landing/Landing";
import { Rail } from "./shell/Rail";
import { type Stage, TERMINAL, type View, transitions } from "./shell/constants";
import { DocumentsView } from "./views/DocumentsView";
import { FindingsView } from "./views/FindingsView";
import { RunsView } from "./views/RunsView";
import { Divider } from "./workspace/Divider";
import { DocumentPane, type Highlight } from "./workspace/DocumentPane";
import { errorMessage, getDocument, getGuidance, getRun, getRunDetail, health, listDocuments, listRuns, uploadDocument, type Health } from "@/lib/api";
import {
  STAGE_LABELS,
  citationLabel,
  isLocated,
  type DocumentSummary,
  type DocumentView,
  type FindingView,
  type ReviewView,
  type RunSummary,
  type SpanView,
} from "@/lib/types";

const HIGHLIGHT_MS = 1600;
const READY_PAUSE_MS = 450;

// A real, openly licensed agreement bundled for "try the sample": Common Paper's Cloud Service
// Agreement, CC BY 4.0. Attribution is shown under the document when it is loaded.
const SAMPLE_PATH = "/samples/cloud-service-agreement.docx";
const SAMPLE_NAME = "Cloud Service Agreement (Common Paper).docx";
// The run the first screen offers as a finished review, set at build time for a deployment whose store holds it
// (the Phase 1 proof run, docs/DEMO-PROOF.md); otherwise the latest complete run with findings.
const PROOF_RUN_ID = process.env.NEXT_PUBLIC_PROOF_RUN ?? "";

/** The workbench, behind the gate the API keeps (access/AccessGate.tsx): nothing below mounts, and so nothing asks the API, until the reader is through it. */
export function Workbench() {
  return (
    <AccessGate>
      <WorkbenchSurface />
    </AccessGate>
  );
}

function WorkbenchSurface() {
  const reduceMotion = useReducedMotion() ?? false;
  const { morph, quick } = transitions(reduceMotion);

  const [stage, setStage] = useState<Stage>("empty");
  const [processingLabel, setProcessingLabel] = useState("Reading document");
  const [pendingName, setPendingName] = useState("");
  const [doc, setDoc] = useState<DocumentView | null>(null);
  const [isSample, setIsSample] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [apiHealth, setApiHealth] = useState<Health | null>(null);
  const [evidence, setEvidence] = useState<FindingView | null>(null);
  // A finished review a visitor can open from the first screen: the run named at build time, else the latest
  // complete run with findings in this store. A record, never a manufactured example.
  const [proof, setProof] = useState<RunSummary | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [lit, setLit] = useState<string | null>(null);
  const [composerText, setComposerText] = useState("");
  const [view, setView] = useState<View>("assistant");
  const [recent, setRecent] = useState<DocumentSummary[]>([]);
  const [viewError, setViewError] = useState<string | null>(null);
  const [pendingFindingId, setPendingFindingId] = useState<string | null>(null);

  const runs = useRunFollower();
  const { run, show: showRun, setRunError, stop: stopRun, ask: startRun } = runs;
  const guidance = useGuidance(setRunError);
  const { guidance: guidanceRecord, setGuidance, setDraft: setGuidanceDraft, open: guidanceOpen, setOpen: setGuidanceOpen } = guidance;
  const memo = useMemoAction();
  const { reset: resetMemo, generate: generateMemo } = memo;
  const split = useDocWidth();

  const docPaneRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const assistantInputRef = useRef<HTMLTextAreaElement>(null);
  const drawerCloseRef = useRef<HTMLButtonElement>(null);
  const evidenceTriggerRef = useRef<HTMLElement | null>(null);
  const litTimer = useRef<number | null>(null);

  const sectionsById = useMemo(() => new Map((doc?.sections ?? []).map((s) => [s.id, s])), [doc]);

  // ---- health ----------------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    health()
      .then((h) => !cancelled && setApiHealth(h))
      .catch((error: unknown) => !cancelled && setApiHealth({ ok: false, provider: "", model: "", detail: errorMessage(error), access: "off" }));
    return () => {
      cancelled = true;
    };
  }, []);

  // Documents already in the workbench, so a returning reviewer can reopen one from the first screen.
  const onLanding = stage === "empty" && view === "assistant";
  useEffect(() => {
    if (!onLanding) return;
    let cancelled = false;
    listDocuments()
      .then((rows) => !cancelled && setRecent(rows.slice(0, 3)))
      .catch(() => !cancelled && setRecent([]));
    listRuns()
      .then((rows) => {
        if (cancelled) return;
        const named = PROOF_RUN_ID ? rows.find((r) => r.id === PROOF_RUN_ID) : undefined;
        setProof(named ?? rows.find((r) => r.stage === "complete" && r.findings > 0) ?? null);
      })
      .catch(() => !cancelled && setProof(null));
    return () => {
      cancelled = true;
    };
  }, [onLanding]);

  // ---- upload -----------------------------------------------------------------------------

  const loadFile = useCallback(
    async (file: File, sample = false) => {
      setUploadError(null);
      setPendingName(file.name);
      setProcessingLabel("Reading document");
      setStage("processing");
      try {
        const uploaded = await uploadDocument(file);
        setDoc(uploaded);
        setIsSample(sample);
        showRun(null); // the previous run's follower and drawer do not outlive its document
        resetMemo();
        setHighlight(null);
        setEvidence(null);
        setProcessingLabel("Ready");
        window.setTimeout(() => setStage("workspace"), READY_PAUSE_MS);
      } catch (error) {
        setUploadError(errorMessage(error));
        setStage("empty");
      }
    },
    [showRun, resetMemo],
  );

  const loadSample = useCallback(async () => {
    setUploadError(null);
    try {
      // eslint-disable-next-line no-restricted-globals -- the bundled sample is a static file of this origin, not the API
      const response = await fetch(SAMPLE_PATH);
      if (!response.ok) throw new Error("The sample agreement is missing from this build.");
      const blob = await response.blob();
      await loadFile(new File([blob], SAMPLE_NAME, { type: blob.type }), true);
    } catch (error) {
      setUploadError(errorMessage(error));
    }
  }, [loadFile]);

  useDropZone(stage !== "workspace" && stage !== "processing", setStage, loadFile);

  // ---- asking -----------------------------------------------------------------------------

  const ask = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || !doc) return;
      setComposerText("");
      setEvidence(null);
      setHighlight(null);
      resetMemo();
      const started = await startRun(doc.id, guidanceRecord?.id ?? null, question);
      if (!started) setComposerText(text); // the API refused it; the words are the person's, not the error's
    },
    [doc, guidanceRecord, startRun, resetMemo],
  );

  // ---- opening records from the Documents, Findings and Runs surfaces ----------------------

  const navigate = useCallback(
    (next: View) => {
      setViewError(null);
      setPaletteOpen(false);
      setGuidanceOpen(false);
      setView(next);
    },
    [setGuidanceOpen],
  );

  /** The first screen: where a contract is added. The mark on the rail and the palette's last command both lead here. */
  const goHome = useCallback(() => {
    navigate("assistant");
    setStage("empty");
  }, [navigate]);

  const openDocument = useCallback(
    async (id: string, show = true) => {
      setViewError(null);
      if (doc?.id === id) {
        setStage("workspace");
        if (show) setView("assistant");
        return;
      }
      try {
        const loaded = await getDocument(id);
        stopRun();
        setDoc(loaded);
        setIsSample(false);
        showRun(null);
        resetMemo();
        setRunError(null);
        setHighlight(null);
        setEvidence(null);
        setStage("workspace");
        if (show) setView("assistant");
      } catch (error) {
        setViewError(errorMessage(error));
      }
    },
    [doc, stopRun, showRun, resetMemo, setRunError],
  );

  /** Show a recorded run in the workspace: its document, its guidance as the scope, its findings. */
  const openRun = useCallback(
    async (runId: string, findingId: string | null = null, show = true) => {
      setViewError(null);
      try {
        const detail = await getRunDetail(runId);
        const [loadedDoc, loadedRun, loadedGuidance] = await Promise.all([
          doc && doc.id === detail.documentId ? Promise.resolve(doc) : getDocument(detail.documentId),
          getRun(runId),
          detail.guidanceId ? getGuidance(detail.guidanceId) : Promise.resolve(null),
        ]);
        stopRun();
        setDoc(loadedDoc);
        setIsSample(false);
        showRun(loadedRun); // followed when it is still in flight
        setGuidance(loadedGuidance ? { id: loadedGuidance.id, text: loadedGuidance.text } : null);
        setGuidanceDraft(loadedGuidance ? loadedGuidance.text : DEFAULT_GUIDANCE);
        resetMemo();
        setRunError(null);
        setHighlight(null);
        setEvidence(null);
        setPendingFindingId(findingId);
        setStage("workspace");
        if (show) setView("assistant");
      } catch (error) {
        setViewError(errorMessage(error));
      }
    },
    [doc, stopRun, showRun, setGuidance, setGuidanceDraft, resetMemo, setRunError],
  );

  useUrlState({ view, doc, stage, run, findingId: evidence?.id ?? null, openRun, openDocument, navigate, goHome });

  // Reviews are made on the Findings surface; when the Assistant is shown again its finished run is re-read from the
  // record, so the drawer's review state and the memo's review head are the record's, not a stale copy.
  const finishedRunId = run && TERMINAL.includes(run.stage) ? run.id : null;
  const reviewHead = run?.reviewHead ?? "";
  useEffect(() => {
    if (view !== "assistant" || !finishedRunId) return;
    let cancelled = false;
    getRun(finishedRunId)
      .then((fresh) => !cancelled && fresh.reviewHead !== reviewHead && showRun(fresh))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [view, finishedRunId, reviewHead, showRun]);

  // Spoken to screen readers through the live region; derived, never stored.
  const announcement = useMemo(() => {
    if (!run) return "";
    if (run.stage in STAGE_LABELS) return STAGE_LABELS[run.stage as keyof typeof STAGE_LABELS];
    if (run.stage === "complete") return `${run.findings.length} finding${run.findings.length === 1 ? "" : "s"} ready`;
    return outcomeTitle(run);
  }, [run]);

  // ---- document navigation ---------------------------------------------------------------

  const jumpTo = useCallback((sectionId: string, span: SpanView | null = null) => {
    if (!docPaneRef.current?.querySelector(`[data-section="${sectionId}"]`)) return;
    // A new object every time, so jumping to the passage already marked scrolls back to it.
    setHighlight({ sectionId, span });
    setLit(sectionId);
    if (litTimer.current) window.clearTimeout(litTimer.current);
    litTimer.current = window.setTimeout(() => setLit(null), HIGHLIGHT_MS);
  }, []);
  useHighlightScroll(docPaneRef, highlight, reduceMotion);

  const openEvidence = useCallback((finding: FindingView, trigger: HTMLElement | null) => {
    evidenceTriggerRef.current = trigger;
    setEvidence(finding);
  }, []);

  /** A decision recorded from the drawer: the run on screen takes the record's review, so the card and the drawer agree. */
  const reviewed = useCallback(
    (findingId: string, review: ReviewView | null) => {
      if (!run) return;
      const findings = run.findings.map((f) => (f.id === findingId ? { ...f, review } : f));
      showRun({ ...run, findings });
      setEvidence((open) => (open && open.id === findingId ? { ...open, review } : open));
      getRun(run.id)
        .then((fresh) => {
          showRun(fresh);
          setEvidence((open) => (open ? (fresh.findings.find((f) => f.id === open.id) ?? open) : open));
        })
        .catch(() => undefined);
    },
    [run, showRun],
  );

  const closeEvidence = useCallback(() => {
    setEvidence(null);
    evidenceTriggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (evidence) drawerCloseRef.current?.focus();
  }, [evidence]);

  // A finding opened from the Findings surface: once its document and run are on screen
  // (the workspace mounts after the previous view's exit), jump to its evidence and open the drawer.
  useEffect(() => {
    if (!pendingFindingId || !run || stage !== "workspace" || view !== "assistant") return;
    const finding = run.findings.find((f) => f.id === pendingFindingId);
    if (!finding) return; // ids are unique, so a stale id never matches a later run; the next open replaces it
    const span = finding.spans.find(isLocated) ?? null;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      const pane = docPaneRef.current;
      const ready = !!pane && (!span || !!pane.querySelector(`[data-section="${span.sectionId}"]`));
      if (!ready && attempts < 40) return;
      window.clearInterval(timer);
      if (span && ready) jumpTo(span.sectionId, span);
      openEvidence(finding, null);
      setPendingFindingId(null);
    }, 50);
    return () => window.clearInterval(timer);
  }, [pendingFindingId, run, stage, view, jumpTo, openEvidence]);

  // ---- keyboard ---------------------------------------------------------------------------

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (stage === "workspace" && view === "assistant") setPaletteOpen((o) => !o);
        return;
      }
      if (event.key === "Escape") {
        if (paletteOpen) setPaletteOpen(false);
        else if (guidanceOpen) setGuidanceOpen(false);
        else if (evidence) closeEvidence();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stage, view, paletteOpen, guidanceOpen, setGuidanceOpen, evidence, closeEvidence]);

  // ---- commands ---------------------------------------------------------------------------

  // The palette calls this once when it mounts; nothing here runs during the workbench render.
  const buildCommands = (): Command[] => {
    const list: Command[] = ASSISTANT_SUGGESTIONS.map((s) => ({ id: `ask-${s}`, label: s, group: "Ask", run: () => void ask(s) }));
    list.push({
      id: "guidance-edit",
      label: guidanceRecord ? "Edit legal guidance" : "Add legal guidance",
      group: "Guidance",
      run: () => setGuidanceOpen(true),
    });
    if (guidanceRecord) list.push({ id: "guidance-remove", label: "Remove legal guidance", group: "Guidance", run: guidance.remove });
    for (const f of run?.findings ?? []) {
      list.push({ id: `evidence-${f.id}`, label: `Inspect evidence: ${f.topic}`, group: "Evidence", run: () => openEvidence(f, null) });
    }
    if (run?.stage === "complete" && run.findings.length > 0) {
      list.push({ id: "memo", label: "Generate review memo", group: "Evidence", run: () => void generateMemo(run) });
    }
    list.push({ id: "go-documents", label: "Documents", group: "Go to", run: () => navigate("documents") });
    list.push({ id: "go-findings", label: "Findings", group: "Go to", run: () => navigate("findings") });
    list.push({ id: "go-runs", label: "Runs", group: "Go to", run: () => navigate("runs") });
    list.push({ id: "go-new", label: "Review another contract", group: "Go to", run: goHome });
    for (const s of doc?.sections ?? []) {
      if (!s.number) continue;
      list.push({ id: `jump-${s.id}`, label: citationLabel(s), group: "Jump to", hint: "in document", run: () => jumpTo(s.id) });
    }
    return list;
  };

  // ---- render -----------------------------------------------------------------------------

  const showLanding = view === "assistant" && stage !== "workspace";
  const openSearch = () => {
    if (doc) {
      setView("assistant");
      setStage("workspace");
      setPaletteOpen(true);
    } else {
      navigate("assistant");
    }
  };

  return (
    <div className={styles.root} data-stage={stage}>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.txt"
        className={styles.hiddenInput}
        onChange={(e) => {
          const picked = e.target.files?.[0];
          if (picked) void loadFile(picked);
          e.target.value = "";
        }}
      />
      <div className="visually-hidden" aria-live="polite">
        {announcement}
      </div>

      <AnimatePresence mode="wait" initial={false}>
        {showLanding ? (
          <Landing
            key="landing"
            stage={stage}
            processingLabel={processingLabel}
            pendingName={pendingName}
            composerText={composerText}
            setComposerText={setComposerText}
            onHome={goHome}
            onPickFile={() => fileInputRef.current?.click()}
            onLoadSample={() => void loadSample()}
            proof={proof}
            onOpenProof={(id, findingId) => void openRun(id, findingId)}
            uploadError={uploadError}
            apiHealth={apiHealth}
            recent={recent}
            onOpenDocument={(id) => void openDocument(id)}
            onAllDocuments={() => navigate("documents")}
            viewError={viewError}
            reduceMotion={reduceMotion}
          />
        ) : (
          <motion.section key="shell" id="main" tabIndex={-1} className={styles.workspace} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={morph}>
            <Rail active={view} hasDocument={!!doc} onNavigate={navigate} onSearch={openSearch} onHome={goHome} />

            <AnimatePresence mode="wait" initial={false}>
              {view !== "assistant" ? (
                <motion.div key={view} className={styles.main} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={quick}>
                  {view === "documents" && (
                    <DocumentsView
                      currentId={doc?.id ?? null}
                      notice={viewError}
                      onOpen={(id) => void openDocument(id)}
                      onAdd={() => {
                        setView("assistant");
                        setStage("empty");
                      }}
                    />
                  )}
                  {view === "findings" && <FindingsView notice={viewError} onOpen={(record) => void openRun(record.runId, record.id)} />}
                  {view === "runs" && <RunsView notice={viewError} currentRunId={run?.id ?? null} onOpenRun={(id) => void openRun(id)} />}
                </motion.div>
              ) : (
                <motion.div key="workspace" className={styles.main} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={quick}>
                  <div className={styles.narrowNote}>
                    <p>The contract text needs a wider window. Findings, evidence and the record work at this size.</p>
                  </div>
                  <div className={styles.split} style={{ gridTemplateColumns: `${split.docWidth}% 8px minmax(0, 1fr)` }}>
                    <DocumentPane
                      doc={doc}
                      isSample={isSample}
                      lit={lit}
                      highlight={highlight}
                      reduceMotion={reduceMotion}
                      paneRef={docPaneRef}
                      findings={run?.stage === "complete" ? run.findings : []}
                      onJump={jumpTo}
                    />
                    <Divider docWidth={split.docWidth} setDocWidth={split.setDocWidth} onPointerDown={split.startDrag} />
                    <AssistantPanel
                      doc={doc}
                      runs={runs}
                      guidance={guidance}
                      memo={memo}
                      composerText={composerText}
                      setComposerText={setComposerText}
                      onAsk={(text) => void ask(text)}
                      inputRef={assistantInputRef}
                      onFollowUp={() => assistantInputRef.current?.focus()}
                      evidence={evidence}
                      onOpenEvidence={openEvidence}
                      onCloseEvidence={closeEvidence}
                      onReviewed={reviewed}
                      drawerCloseRef={drawerCloseRef}
                      sectionsById={sectionsById}
                      onJump={jumpTo}
                      onOpenPalette={() => setPaletteOpen(true)}
                      reduceMotion={reduceMotion}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <AnimatePresence>
              {paletteOpen && <CommandPalette getCommands={buildCommands} onClose={() => setPaletteOpen(false)} reduceMotion={reduceMotion} />}
            </AnimatePresence>
          </motion.section>
        )}
      </AnimatePresence>
    </div>
  );
}
