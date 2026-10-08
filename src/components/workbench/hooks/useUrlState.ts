"use client";

import { useEffect, useRef } from "react";
import { VIEWS, type Stage, type View } from "../shell/constants";
import type { DocumentView, RunView } from "@/lib/types";

interface UrlStateArgs {
  view: View;
  doc: DocumentView | null;
  stage: Stage;
  run: RunView | null;
  /** The finding whose evidence is open, if any: written as `finding`, so Back reopens it and a link carries it. */
  findingId: string | null;
  openRun: (runId: string, findingId: string | null, show: boolean) => Promise<void>;
  openDocument: (documentId: string, show: boolean) => Promise<void>;
  navigate: (view: View) => void;
  goHome: () => void;
}

/** Moves within this many milliseconds of each other are one move: a click that loads a run passes through several states. */
const COALESCE_MS = 600;

/** How long a restore may take to arrive before the URL follows the state again. */
const RESTORE_PATIENCE_MS = 5000;

/**
 * The state an address names, comparable across spellings: the parameters in one order, and no `document` beside a
 * `run`, since a run determines its document. `?document=A&run=<a run of B>` names B's run, and B is what is shown.
 */
function named(search: string): string {
  const params = new URLSearchParams(search);
  if (params.get("run")) params.delete("document");
  params.sort();
  return params.toString();
}

/** What the address asks for, and the state that answers it. True when the address named something this app has. */
function apply(search: string, { openRun, openDocument, navigate, goHome }: Pick<UrlStateArgs, "openRun" | "openDocument" | "navigate" | "goHome">): boolean {
  const params = new URLSearchParams(search);
  const requested = params.get("view");
  const wantsView = requested && (VIEWS as readonly string[]).includes(requested) && requested !== "assistant" ? (requested as View) : null;
  const runId = params.get("run");
  const documentId = params.get("document");
  // `finding` opens that finding's evidence: a memo's citation links back to it, and so does Back.
  if (runId) void openRun(runId, params.get("finding"), !wantsView);
  else if (documentId) void openDocument(documentId, !wantsView);
  else if (!wantsView) goHome();
  if (wantsView) navigate(wantsView);
  return Boolean(runId || documentId || wantsView);
}

/**
 * The URL carries `document`, `run` and `view`, so an open document, the run (in flight or finished) and the current
 * surface survive a reload, and the browser's Back and Forward buttons move between them. Restored once on mount and
 * again on every popstate; written whenever the state changes. A move writes a history entry; the several states one
 * click passes through are coalesced into one entry, and a restore writes none. A run in flight is written as soon as
 * it exists, so a refresh mid-run reattaches to it instead of losing it.
 */
export function useUrlState({ view, doc, stage, run, findingId, openRun, openDocument, navigate, goHome }: UrlStateArgs) {
  const restored = useRef(false);
  // The address a restore is heading for, and when it set out. Until the state reaches it the URL is left alone, so a
  // reload mid-load still has the deep link; a restore that never arrives is given up after a few seconds.
  const restoring = useRef<{ search: string; at: number } | null>(null);
  const lastPush = useRef(0);
  const handlers = useRef({ openRun, openDocument, navigate, goHome });
  useEffect(() => {
    handlers.current = { openRun, openDocument, navigate, goHome };
  }, [openRun, openDocument, navigate, goHome]);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    // Whatever the first render writes is a correction of the address, not a move: no history entry for it.
    lastPush.current = Date.now();
    const at = Date.now();
    if (window.location.search && apply(window.location.search, handlers.current)) restoring.current = { search: window.location.search, at };
  }, []);

  useEffect(() => {
    const onPop = () => {
      const at = Date.now();
      restoring.current = apply(window.location.search, handlers.current) || !window.location.search ? { search: window.location.search, at } : null;
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (view !== "assistant") params.set("view", view);
    if (doc && stage === "workspace") params.set("document", doc.id);
    if (run?.id && doc && stage === "workspace") params.set("run", run.id);
    if (findingId && run?.id && doc && stage === "workspace" && view === "assistant") params.set("finding", findingId);
    const query = params.toString();
    const search = query ? `?${query}` : "";
    const next = `${window.location.pathname}${search}`;
    const current = `${window.location.pathname}${window.location.search}`;
    if (restoring.current) {
      if (named(search) === named(restoring.current.search)) {
        restoring.current = null;
        // The restore arrived. An address that said it differently (another document's id beside the run, the
        // parameters in another order) is corrected in place: no history entry, and Back still leaves the page.
        if (next !== current) {
          window.history.replaceState(null, "", next);
          lastPush.current = Date.now();
        }
        return;
      }
      if (Date.now() - restoring.current.at < RESTORE_PATIENCE_MS) return;
      restoring.current = null;
    }
    if (next === current) return;
    const now = Date.now();
    if (now - lastPush.current < COALESCE_MS) {
      window.history.replaceState(null, "", next);
    } else {
      window.history.pushState(null, "", next);
      lastPush.current = now;
    }
  }, [view, doc, stage, run, findingId]);
}
