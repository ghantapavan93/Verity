"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import styles from "../Workbench.module.css";
import { ACCESS_REQUIRED_EVENT, enterWithInvite, errorMessage, getAccess } from "@/lib/api";

/**
 * The door in front of the workbench, when the API has one (backend/app/api/access.py). This component decides
 * nothing: the API says whether a session is needed and whether this browser has one, and every route answers 401
 * for itself. All that happens here is the exchange of an invite for a session, and the asking.
 *
 * A reader arrives by a link that carries the invite in its fragment (`…/?document=…&run=…#invite=<token>`). The
 * fragment is exchanged for a session cookie before the workbench mounts and is then removed from the address bar,
 * so what is left is the page the link was for. A reader who arrives without it, or whose session has ended, is
 * asked for the link: one field, no account, nothing to reset.
 */

type State = "checking" | "open" | "closed";

const INVITE_IN_FRAGMENT = /(?:^#|&)invite=([^&]+)/;

/** The invite in the address bar, if any, taken out of it at once so it is not left on screen or in a copied URL. */
function takeInviteFromAddress(): string | null {
  const found = INVITE_IN_FRAGMENT.exec(window.location.hash);
  if (!found) return null;
  window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
  return decodeURIComponent(found[1]);
}

export function AccessGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>("checking");
  const [invite, setInvite] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const arrive = async () => {
      const carried = takeInviteFromAddress();
      try {
        if (carried) {
          await enterWithInvite(carried);
          if (!cancelled) setProblem(null);
        }
      } catch (error) {
        if (!cancelled) setProblem(errorMessage(error));
      }
      try {
        const access = await getAccess();
        if (!cancelled) setState(access.entered ? "open" : "closed");
      } catch {
        // The API did not answer. The workbench says so in its own words; the door has nothing to add.
        if (!cancelled) setState("open");
      }
    };
    void arrive();
    // A session that ends while the page is open: the next request is refused, and the door closes.
    const close = () => setState("closed");
    window.addEventListener(ACCESS_REQUIRED_EVENT, close);
    // An invite link opened in a tab that already shows this page changes only the fragment, and a browser does not
    // reload for that: without this the link did nothing and the invite stayed in the address bar (found by driving
    // the deployed build, 2026-10-02).
    const arrivedInPlace = () => {
      if (INVITE_IN_FRAGMENT.test(window.location.hash)) void arrive();
    };
    window.addEventListener("hashchange", arrivedInPlace);
    return () => {
      cancelled = true;
      window.removeEventListener(ACCESS_REQUIRED_EVENT, close);
      window.removeEventListener("hashchange", arrivedInPlace);
    };
  }, []);

  const enter = async (event: FormEvent) => {
    event.preventDefault();
    if (!invite.trim() || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      await enterWithInvite(invite.trim());
      setInvite("");
      setState("open");
    } catch (error) {
      setProblem(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  if (state === "open") return <>{children}</>;
  if (state === "checking") return <div className={styles.root} data-stage="empty" aria-busy="true" />;
  return (
    <div className={styles.root} data-stage="empty">
      <section className={styles.landing} aria-label="Private preview">
        <header className={styles.topbar}>
          <div className={styles.brand}>
            <span className={styles.mark} aria-hidden="true" />
            <span className={styles.wordmark}>Verity</span>
          </div>
        </header>
        <div className={styles.landingBody}>
          <h1 className={styles.prompt}>Private engineering preview</h1>
          <p className={styles.gateLead}>
            This workbench runs against the actual local analysis pipeline: real uploads, real model runs, one store. It opens from the invite link you were
            sent.
          </p>
          <form className={styles.gateForm} onSubmit={enter}>
            <label htmlFor="invite-link">Invite link</label>
            <input
              id="invite-link"
              className={styles.popoverInput}
              value={invite}
              onChange={(e) => setInvite(e.target.value)}
              placeholder="Paste the link from your invitation"
              autoComplete="off"
              spellCheck={false}
              autoFocus
            />
            <button type="submit" className={styles.memoButton} disabled={busy || !invite.trim()}>
              {busy ? "Entering…" : "Enter workbench"}
            </button>
          </form>
          {problem && (
            <p className={styles.errorLine} role="alert">
              {problem}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
