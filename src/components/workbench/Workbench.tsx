"use client";

/**
 * The workbench coordinates layout and shell state: which surface is on screen, which document
 * and run are open, what is highlighted, what the palette can do. Feature behaviour lives beside
 * its feature (hooks/, assistant/, workspace/, landing/, views/); domain decisions live in the API.
 *
 * The document is the source of truth on screen; the Assistant is secondary. Nothing on the
 * primary path is simulated: uploads are parsed by the API, runs are model runs, and every
 * passage shown was found in the document text by the API before it arrived here.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CommandPalette, type Command } from "./CommandPalette";
import styles from "./Workbench.module.css";
import { AccessGate } from "./access/AccessGate";
import { ASSISTANT_SUGGESTIONS, AssistantPanel } from "./assistant/AssistantPanel";
import { SAMPLES, suggestionsFor, type SampleKind } from "./samples";
import { outcomeTitle } from "./assistant/RunOutcome";
import { useDocWidth } from "./hooks/useDocWidth";
import { useDropZone } from "./hooks/useDropZone";
import { DEFAULT_GUIDANCE, useGuidance } from "./hooks/useGuidance";
import { useHighlightScroll } from "./hooks/useHighlightScroll";
import { useModelWake } from "./hooks/useModelWake";
import { useMemoAction } from "./hooks/useMemoAction";
import { useRunFollower } from "./hooks/useRunFollower";
import { useUrlState } from "./hooks/useUrlState";
import { Landing } from "./landing/Landing";
import { chooseProof } from "./landing/proofRun";
import { modelPlace } from "@/lib/modelPlace";
import { Rail } from "./shell/Rail";
import { NARROW_QUERY, type Stage, TERMINAL, type View, transitions } from "./shell/constants";
import { DocumentsView } from "./views/DocumentsView";
import { FindingsView } from "./views/FindingsView";
import { RunsView } from "./views/RunsView";
import { Divider } from "./workspace/Divider";
import { DocumentPane, type Highlight } from "./workspace/DocumentPane";
import {
  ApiError,
  errorMessage,
  getDocument,
  getGuidance,
  getRun,
  getRunDetail,
  health,
  listDocuments,
  listRuns,
  uploadDocument,
  type Health,
} from "@/lib/api";
import {
  STAGE_LABELS,
  stageAnnouncement,
  citationLabel,
  evidenceJump,
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

// The run the first screen offers as a finished review, set at build time for a deployment whose store holds it
// (the Phase 1 proof run, docs/DEMO-PROOF.md), and that run or none (landing/proofRun.ts); otherwise the latest complete run with findings.
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
  const [sample, setSample] = useState<SampleKind | null>(null);
  // On a phone the split shows one pane at a time (Workbench.module.css): the answer, or the contract. View state only.
  const [narrowPane, setNarrowPane] = useState<"answer" | "contract">("answer");
  const [uploadError, setUploadError] = useState<{ name: string | null; reason: string } | null>(null);
  const [apiHealth, setApiHealth] = useState<Health | null>(null);
  const [accessKnown, setAccessKnown] = useState(true);
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
  const { run, show: showRun, refresh: refreshRun, claim: claimRun, setRunError, stop: stopRun, ask: startRun } = runs;
  // On a phone, a new contract or a new run on screen opens on its answer, whatever put it there (an upload, a list, the
  // palette, a link): the pane an earlier passage left on the contract hides the composer and the answer (skeptic
  // review, 2026-10-15). Adjusted while rendering, keyed on what is shown; a jump within the same run keeps its pane.
  const shownKey = `${doc?.id ?? ""}:${run?.id ?? ""}`;
  const [paneKey, setPaneKey] = useState(shownKey);
  if (paneKey !== shownKey) {
    setPaneKey(shownKey);
    setNarrowPane("answer");
  }
  const guidance = useGuidance();
  const { guidance: guidanceRecord, setGuidance, setDraft: setGuidanceDraft, open: guidanceOpen, setOpen: setGuidanceOpen } = guidance;
  const memo = useMemoAction();
  const { reset: resetMemo, generate: generateMemo } = memo;
  const split = useDocWidth();

  const docPaneRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const assistantInputRef = useRef<HTMLTextAreaElement>(null);
  // A document that has just opened hands focus to the question box: the next thing a person does is ask. Until
  // 2026-10-09 focus fell to the page body, fifteen Tab presses from the box (frontend review).
  const focusComposerOnOpen = useRef(false);
  const drawerCloseRef = useRef<HTMLButtonElement>(null);
  const evidenceTriggerRef = useRef<HTMLElement | null>(null);
  const litTimer = useRef<number | null>(null);

  const sectionsById = useMemo(() => new Map((doc?.sections ?? []).map((s) => [s.id, s])), [doc]);

  // A hosted model sleeps when idle: adding a contract, or starting a question, wakes it (hooks/useModelWake). Opening
  // one from a link, a reload or a recorded run only looks, and wakes nothing.
  const [contractsAdded, setContractsAdded] = useState(0);
  useModelWake(apiHealth?.modelLocation === "hosted", contractsAdded, composerText.trim().length > 0);

  // ---- health ----------------------------------------------------------------------------

  const onLanding = stage === "empty" && view === "assistant";

  useEffect(() => {
    let cancelled = false;
    health()
      .then((h) => {
        if (cancelled) return;
        setApiHealth(h);
        // Known again once the API answers: one unanswered check hid where the model runs for the rest of the visit
        // (2026-10-13).
        setAccessKnown(true);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // The API could not be asked, so nothing is known about its door: the first screen claims neither open nor private.
        setAccessKnown(false);
        // The model's whereabouts are unknown too; with accessKnown false nothing reads them (landing/Landing.tsx place).
        setApiHealth({ ok: false, provider: "", model: "", detail: errorMessage(error), access: "off", modelLocation: "server", modelHost: "", fault: "" });
      });
    return () => {
      cancelled = true;
    };
    // Asked again whenever the first screen comes and goes, not once per page: a model that went offline while the
    // page stayed open was never announced, and the first a reader heard of it was a failed question (journey audit,
    // 2026-10-09).
  }, [onLanding]);

  // Documents already in the workbench, so a returning reviewer can reopen one from the first screen.
  useEffect(() => {
    if (!onLanding) return;
    let cancelled = false;
    listDocuments()
      .then((rows) => !cancelled && setRecent(rows.slice(0, 3)))
      .catch(() => !cancelled && setRecent([]));
    chooseProof(PROOF_RUN_ID, listRuns, getRunDetail)
      .then((run) => !cancelled && setProof(run))
      .catch(() => !cancelled && setProof(null));
    return () => {
      cancelled = true;
    };
  }, [onLanding]);

  // ---- upload -----------------------------------------------------------------------------

  const loadFile = useCallback(
    async (file: File, kind: SampleKind | null = null) => {
      // The first screen's box promises "Your question, asked once the contract is added": a question typed there is
      // asked when the document opens. Until 2026-10-08 it was carried into the composer and left unsent (QA review).
      // A file added from inside the workspace sends nothing the person did not send themselves.
      const question = stage !== "workspace" ? composerText.trim() : "";
      setUploadError(null);
      setPendingName(file.name);
      setProcessingLabel("Reading document");
      // A file added from another view (Documents) is read on the first screen, where its progress and result show.
      setView("assistant");
      setStage("processing");
      try {
        const uploaded = await uploadDocument(file);
        setDoc(uploaded);
        setContractsAdded((n) => n + 1);
        setSample(kind);
        showRun(null); // the previous run's follower and drawer do not outlive its document
        resetMemo();
        setHighlight(null);
        setEvidence(null);
        setProcessingLabel("Ready");
        window.setTimeout(() => {
          focusComposerOnOpen.current = true;
          setStage("workspace");
          if (!question) return;
          setComposerText("");
          void startRun(uploaded.id, guidanceRecord?.id ?? null, question).then((started) => {
            if (!started) setComposerText(question); // the API refused it; the words are the person's, not the error's
          });
        }, READY_PAUSE_MS);
      } catch (error) {
        setUploadError({ name: file.name, reason: errorMessage(error) });
        setStage("empty");
      }
    },
    [showRun, resetMemo, stage, composerText, startRun, guidanceRecord],
  );

  useEffect(() => {
    if (stage !== "workspace" || !focusComposerOnOpen.current) return;
    focusComposerOnOpen.current = false;
    // The workspace mounts after the landing's exit animation: wait for the box, a frame at a time, for up to a second.
    let frame = 0;
    let handle = 0;
    const tryFocus = () => {
      const box = assistantInputRef.current;
      if (box) box.focus({ preventScroll: true });
      else if (frame++ < 60) handle = window.requestAnimationFrame(tryFocus);
    };
    tryFocus();
    return () => window.cancelAnimationFrame(handle);
  }, [stage, doc]);

  const loadSample = useCallback(
    async (kind: SampleKind) => {
      setUploadError(null);
      try {
        // eslint-disable-next-line no-restricted-globals -- the bundled sample is a static file of this origin, not the API
        const response = await fetch(SAMPLES[kind].path);
        if (!response.ok) throw new Error("The sample agreement is missing from this build.");
        const blob = await response.blob();
        await loadFile(new File([blob], SAMPLES[kind].name, { type: blob.type }), kind);
      } catch (error) {
        setUploadError({ name: null, reason: errorMessage(error) });
      }
    },
    [loadFile],
  );

  // The API could not be asked: a dropped or picked file would only fail (round 2: a drop still said "Release to add").
  const unreachable = apiHealth !== null && !apiHealth.ok && !accessKnown;
  useDropZone(stage !== "workspace" && stage !== "processing" && !unreachable, setStage, loadFile);

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

  /** Why a record could not be opened. A 404 says so in a sentence (the API's "run not found" read as a fault, QA
   *  2026-10-15), and claims only what a 404 means here: not readable from this workspace, or gone. */
  const openFailure = (error: unknown, record: "run" | "contract"): string =>
    error instanceof ApiError && error.status === 404
      ? `This ${record} cannot be opened in this workspace: it belongs to another one, or no longer exists.`
      : errorMessage(error);

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
        focusComposerOnOpen.current = show;
        setNarrowPane("answer");
        setStage("workspace");
        if (show) setView("assistant");
        return;
      }
      try {
        const loaded = await getDocument(id);
        stopRun();
        setDoc(loaded);
        setSample(null);
        showRun(null);
        resetMemo();
        setRunError(null);
        setHighlight(null);
        setEvidence(null);
        focusComposerOnOpen.current = show;
        setNarrowPane("answer");
        setStage("workspace");
        if (show) setView("assistant");
      } catch (error) {
        setViewError(openFailure(error, "contract"));
      }
    },
    [doc, stopRun, showRun, resetMemo, setRunError],
  );

  /** Show a recorded run in the workspace: its document, its guidance as the scope, its findings. */
  const openRun = useCallback(
    async (runId: string, findingId: string | null = null, show = true) => {
      setViewError(null);
      // Opening waits on three fetches; a question asked or another run opened meanwhile is newer and keeps the screen.
      const current = claimRun();
      try {
        const detail = await getRunDetail(runId);
        const [loadedDoc, loadedRun, loadedGuidance] = await Promise.all([
          doc && doc.id === detail.documentId ? Promise.resolve(doc) : getDocument(detail.documentId),
          getRun(runId),
          detail.guidanceId ? getGuidance(detail.guidanceId) : Promise.resolve(null),
        ]);
        if (!current()) return;
        stopRun();
        setDoc(loadedDoc);
        setSample(null);
        showRun(loadedRun); // followed when it is still in flight
        setGuidance(loadedGuidance ? { id: loadedGuidance.id, text: loadedGuidance.text } : null);
        setGuidanceDraft(loadedGuidance ? loadedGuidance.text : DEFAULT_GUIDANCE);
        resetMemo();
        setRunError(null);
        setHighlight(null);
        setEvidence(null);
        setPendingFindingId(findingId);
        // A run opens on its answer: the pane left on the contract by an earlier passage is not what was asked for.
        setNarrowPane("answer");
        setStage("workspace");
        if (show) setView("assistant");
      } catch (error) {
        if (current()) setViewError(openFailure(error, "run"));
      }
    },
    [doc, claimRun, stopRun, showRun, setGuidance, setGuidanceDraft, resetMemo, setRunError],
  );

  useUrlState({ view, doc, stage, run, findingId: evidence?.id ?? null, openRun, openDocument, navigate, goHome });

  // Reviews are made on the Findings surface; when the Assistant is shown again its finished run is re-read from the
  // record, so the drawer's review state and the memo's review head are the record's, not a stale copy.
  const finishedRunId = run && TERMINAL.includes(run.stage) ? run.id : null;
  const reviewHead = run?.reviewHead ?? "";
  useEffect(() => {
    if (view !== "assistant" || !finishedRunId) return;
    // refreshRun applies the record only while this run is still the one on screen.
    getRun(finishedRunId)
      .then((fresh) => {
        if (fresh.reviewHead === reviewHead) return;
        refreshRun(fresh);
        // The drawer holds its own copy of the finding: a decision made on Findings shows there too, not the old
        // state with buttons that the API would refuse (2026-10-13).
        setEvidence((open) => (open && [...fresh.findings, ...fresh.withheld].find((f) => f.id === open.id)) || open);
      })
      .catch(() => undefined);
  }, [view, finishedRunId, reviewHead, refreshRun]);

  // Spoken to screen readers through the live region; derived, never stored.
  const modelSleeps = accessKnown && apiHealth?.modelLocation === "hosted";
  const announcement = useMemo(() => {
    if (!run) return "";
    if (run.stage in STAGE_LABELS) return stageAnnouncement(run.stage as keyof typeof STAGE_LABELS, modelSleeps);
    if (run.stage === "complete") return `${run.findings.length} finding${run.findings.length === 1 ? "" : "s"} ready`;
    return outcomeTitle(run);
  }, [run, modelSleeps]);

  // ---- the tab title: where the reader is, in the browser's own chrome -------------------------

  useEffect(() => {
    const screen =
      view === "documents"
        ? "Documents"
        : view === "findings"
          ? "Findings"
          : view === "runs"
            ? "Runs"
            : stage === "workspace" && doc
              ? doc.name.replace(/\.[^.]+$/, "")
              : null;
    document.title = screen ? `${screen} · Verity` : "Verity";
  }, [view, stage, doc]);

  // ---- document navigation ---------------------------------------------------------------

  const jumpTo = useCallback((sectionId: string, span: SpanView | null = null) => {
    if (!docPaneRef.current?.querySelector(`[data-section="${sectionId}"]`)) return;
    // On a phone the contract is the other pane: show it, then mark the passage there.
    if (window.matchMedia(NARROW_QUERY).matches) setNarrowPane("contract");
    // A new object every time, so jumping to the passage already marked scrolls back to it.
    setHighlight({ sectionId, span });
    setLit(sectionId);
    if (litTimer.current) window.clearTimeout(litTimer.current);
    litTimer.current = window.setTimeout(() => setLit(null), HIGHLIGHT_MS);
  }, []);
  useHighlightScroll(docPaneRef, highlight, reduceMotion);

  // The drawer opens beside the document, so the document shows the passage the drawer is about, from every place the
  // drawer opens (release readiness, 2026-10-10: the card's "Inspect evidence" left it at the top of the contract).
  const openEvidence = useCallback(
    (finding: FindingView, trigger: HTMLElement | null) => {
      evidenceTriggerRef.current = trigger;
      const shown = !!run?.findings.some((f) => f.id === finding.id);
      const narrow = window.matchMedia(NARROW_QUERY).matches;
      const span = evidenceJump(finding, { shown, narrow });
      if (span) jumpTo(span.sectionId, span);
      // On a phone the drawer is a sheet over the answer, and closing it returns focus to the card that opened it:
      // that card must be on screen, not behind the contract pane.
      if (narrow) setNarrowPane("answer");
      setEvidence(finding);
    },
    [jumpTo, run],
  );

  /** A decision recorded from the drawer: the run on screen takes the record's review, so the card and the drawer agree. */
  const reviewed = useCallback(
    (findingId: string, review: ReviewView | null | undefined, latestReviewId?: number) => {
      if (!run) return;
      // `undefined`: the decision was refused because the finding was reviewed since; only the fetch below shows the state.
      if (review !== undefined) {
        const update = (f: FindingView) => (f.id === findingId ? { ...f, review, latestReviewId: latestReviewId ?? f.latestReviewId } : f);
        refreshRun({ ...run, findings: run.findings.map(update) });
        setEvidence((open) => (open ? update(open) : open));
      }
      // Both updates go through refreshRun: a review's answer, or the record read after it, can arrive after the person
      // has asked the next question, and must not put the reviewed run back on screen (m9 smoke, 2026-10-11).
      getRun(run.id)
        .then((fresh) => {
          refreshRun(fresh);
          setEvidence((open) => (open ? (fresh.findings.find((f) => f.id === open.id) ?? open) : open));
        })
        .catch(() => undefined);
    },
    [run, refreshRun],
  );

  // Focus returns to the control that opened the sheet after the sheet is gone: the panel under the sheet is inert
  // while it is open, and a focus call made before that render lands nowhere (found by the 2026-10-08 browser pass).
  const restoreFocusRef = useRef(false);
  const closeEvidence = useCallback(() => {
    restoreFocusRef.current = true;
    setEvidence(null);
  }, []);

  useEffect(() => {
    if (evidence) {
      drawerCloseRef.current?.focus();
    } else if (restoreFocusRef.current) {
      restoreFocusRef.current = false;
      evidenceTriggerRef.current?.focus();
    }
  }, [evidence]);

  // A finding opened from the Findings surface: once its document and run are on screen
  // (the workspace mounts after the previous view's exit), open the drawer, which jumps to its evidence.
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
      openEvidence(finding, null);
      setPendingFindingId(null);
    }, 50);
    return () => window.clearInterval(timer);
  }, [pendingFindingId, run, stage, view, openEvidence]);

  // ---- keyboard ---------------------------------------------------------------------------

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        // Ctrl K does what the rail's "Search (Ctrl K)" does, from every view; with nothing to search it leaves the
        // browser's own shortcut alone. It used to be swallowed everywhere but the Assistant (m7 audit, 2026-10-10).
        if (stage === "workspace" && view === "assistant") {
          event.preventDefault();
          setPaletteOpen((o) => !o);
        } else if (doc && stage !== "processing") {
          event.preventDefault();
          setView("assistant");
          setStage("workspace");
          setPaletteOpen(true);
        }
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
  }, [stage, view, doc, setView, setStage, paletteOpen, guidanceOpen, setGuidanceOpen, evidence, closeEvidence]);

  // ---- commands ---------------------------------------------------------------------------

  // The palette calls this once when it mounts; nothing here runs during the workbench render.
  const buildCommands = (): Command[] => {
    const list: Command[] = suggestionsFor(sample, ASSISTANT_SUGGESTIONS).map((s) => ({ id: `ask-${s}`, label: s, group: "Ask", run: () => void ask(s) }));
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
            onPickFile={() => !unreachable && fileInputRef.current?.click()}
            onLoadSample={(kind) => void loadSample(kind)}
            proof={proof}
            proofStory={Boolean(PROOF_RUN_ID) && proof?.id === PROOF_RUN_ID}
            onOpenProof={(id, findingId) => void openRun(id, findingId)}
            uploadError={uploadError}
            apiHealth={apiHealth}
            accessKnown={accessKnown && apiHealth !== null}
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
                      onAdd={() => fileInputRef.current?.click()}
                      onStart={() => void loadSample("amended")}
                    />
                  )}
                  {view === "findings" && (
                    <FindingsView notice={viewError} onOpen={(record) => void openRun(record.runId, record.id)} onStart={() => void loadSample("amended")} />
                  )}
                  {view === "runs" && <RunsView notice={viewError} currentRunId={run?.id ?? null} onOpenRun={(id) => void openRun(id)} />}
                </motion.div>
              ) : (
                <motion.div key="workspace" className={styles.main} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={quick}>
                  <div className={styles.narrowNote}>
                    <div className={styles.paneSwitch} role="group" aria-label="Show on this screen">
                      <button type="button" aria-pressed={narrowPane === "answer"} onClick={() => setNarrowPane("answer")}>
                        Answer
                      </button>
                      <button type="button" aria-pressed={narrowPane === "contract"} onClick={() => setNarrowPane("contract")}>
                        Contract
                      </button>
                    </div>
                  </div>
                  <div className={styles.split} data-pane={narrowPane} style={{ gridTemplateColumns: `${split.docWidth}% 8px minmax(0, 1fr)` }}>
                    <DocumentPane
                      doc={doc}
                      sample={sample}
                      lit={lit}
                      highlight={highlight}
                      reduceMotion={reduceMotion}
                      paneRef={docPaneRef}
                      findings={run?.stage === "complete" ? run.findings : []}
                      onJump={jumpTo}
                    />
                    <Divider docWidth={split.docWidth} setDocWidth={split.setDocWidth} onPointerDown={split.startDrag} />
                    <AssistantPanel
                      modelPlace={accessKnown ? (modelPlace(apiHealth)?.place ?? null) : null}
                      modelSleeps={modelSleeps}
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
                      sample={sample}
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
