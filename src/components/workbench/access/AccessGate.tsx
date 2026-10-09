"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import styles from "../Workbench.module.css";
import door from "../landing/Landing.module.css";
import { Brand } from "../shell/primitives";
import { ACCESS_REQUIRED_EVENT, enterWithInvite, errorMessage, getAccess, health, type Health } from "@/lib/api";
import { modelPlace } from "@/lib/modelPlace";

const SOURCE = "https://github.com/ghantapavan93/Verity";

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
  // Anonymous health names no provider or model, only where the model runs; nothing is claimed until it answers.
  const [apiHealth, setApiHealth] = useState<Health | null>(null);

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
    health()
      .then((answer) => {
        if (!cancelled) setApiHealth(answer);
      })
      .catch(() => undefined);
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

  const place = modelPlace(apiHealth);
  if (state === "open") return <>{children}</>;
  if (state === "checking") return <div className={styles.root} data-stage="empty" aria-busy="true" />;
  return (
    <div className={styles.root} data-stage="empty">
      <section id="main" tabIndex={-1} className={door.page} aria-label="Live workbench">
        <header className={door.topbar}>
          <Brand />
          <span className={door.preview}>
            <span className={door.previewDot} aria-hidden="true" />
            Private preview
          </span>
        </header>
        <div className={door.gate}>
          <p className={door.kicker}>
            <span className={door.kickerRule} />
            By invitation
          </p>
          <h1 className={door.title}>The live Verity workbench</h1>
          <p className={door.lead}>
            Add a contract (PDF, DOCX or TXT) or the sample agreement, ask a question about it, and open the passage each answer cites. Findings, reviews and
            past runs stay in your own workspace. This is the working system, not a recording of one; it opens from a personal invite link.
          </p>
          {place && (
            <p className={door.gateNote}>
              {place.hosted
                ? `Contracts and questions are sent to ${place.place}, where the model runs.`
                : `Contracts and questions stay with this deployment: the model runs on ${place.place}.`}
            </p>
          )}
          <form className={door.gateForm} onSubmit={enter}>
            <label htmlFor="invite-link" className={door.gateLabel}>
              Invite link
            </label>
            <input
              id="invite-link"
              className={door.gateInput}
              value={invite}
              onChange={(e) => setInvite(e.target.value)}
              placeholder="Paste the link from your invitation"
              autoComplete="off"
              spellCheck={false}
              autoFocus
            />
            <button type="submit" className={door.primary} disabled={busy || !invite.trim()}>
              {busy ? "Entering" : "Enter workbench"}
            </button>
          </form>
          {problem && (
            <p className={door.error} role="alert">
              {problem}
            </p>
          )}
          <p className={door.gateNote}>
            The link signs you in on this browser for seven days. There is no account and no password. Ask for a new link if this one has expired.
          </p>
          <p className={door.gateNote}>
            No invite?{" "}
            <a className={door.link} href="/state">
              Read the recorded research
            </a>
            , open to everyone, or the{" "}
            <a className={door.link} href={SOURCE}>
              source code
            </a>
            .
          </p>
        </div>
      </section>
    </div>
  );
}
