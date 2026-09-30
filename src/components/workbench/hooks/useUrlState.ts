"use client";

import { useEffect, useRef } from "react";
import { VIEWS, type Stage, type View } from "../shell/constants";
import type { DocumentView, RunView } from "@/lib/types";

interface UrlStateArgs {
  view: View;
  doc: DocumentView | null;
  stage: Stage;
  run: RunView | null;
  openRun: (runId: string, findingId: string | null, show: boolean) => Promise<void>;
  openDocument: (documentId: string, show: boolean) => Promise<void>;
  navigate: (view: View) => void;
}

/**
 * The URL carries `document`, `run` and `view`, so an open document, the run (in flight or finished)
 * and the current surface survive a reload. Restored once on mount; written whenever they change. A run
 * in flight is written as soon as it exists, so a refresh mid-run reattaches to it instead of losing it.
 */
export function useUrlState({ view, doc, stage, run, openRun, openDocument, navigate }: UrlStateArgs) {
  const restored = useRef(false);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("view");
    const wantsView = requested && (VIEWS as readonly string[]).includes(requested) && requested !== "assistant" ? (requested as View) : null;
    const runId = params.get("run");
    const documentId = params.get("document");
    // `finding` is read, never written: a memo's citation links back to the run and the finding it came from.
    if (runId) void openRun(runId, params.get("finding"), !wantsView);
    else if (documentId) void openDocument(documentId, !wantsView);
    if (wantsView) navigate(wantsView);
  }, [openRun, openDocument, navigate]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (view !== "assistant") params.set("view", view);
    if (doc && stage === "workspace") params.set("document", doc.id);
    if (run?.id && doc && stage === "workspace") params.set("run", run.id);
    const query = params.toString();
    const next = `${window.location.pathname}${query ? `?${query}` : ""}`;
    if (next !== `${window.location.pathname}${window.location.search}`) window.history.replaceState(null, "", next);
  }, [view, doc, stage, run]);
}
