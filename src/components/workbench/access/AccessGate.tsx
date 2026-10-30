"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import styles from "../Workbench.module.css";
import door from "../landing/Landing.module.css";
import { Brand } from "../shell/primitives";
import { ACCESS_REQUIRED_EVENT, enterWithInvite, errorMessage, getAccess, health, isConflict, visit, type Health } from "@/lib/api";
import { safeDecode } from "@/lib/address";
import type { AccessView } from "@/lib/types";
import { modelPlace } from "@/lib/modelPlace";
import { SOURCE, TopLinks } from "../landing/TopLinks";
import { AccessModeKnown, PublicDemo, Reader } from "./PublicDemo";

/**
 * The door in front of the workbench, when the API has one (backend/app/api/access.py). This component decides
 * nothing: the API says whether a session is needed and whether this browser has one, and every route answers 401
 * for itself. All that happens here is the exchange of an invite for a session, and the asking.
 *
 * A reader arrives by a link that carries the invite in its fragment (`…/?document=…&run=…#invite=<token>`). The
 * fragment is exchanged for a session cookie before the workbench mounts and is then removed from the address bar,
 * so what is left is the page the link was for. A reader who arrives without it, or whose session has ended, is
 * asked for the link: one field, no account, nothing to reset.
 *
 * A public demo (the API says `anonymous`) has no door to show: a browser with no session is handed one of its own
 * at once (POST /api/access/visit), in a workspace no other browser can read, and the workbench opens. If that is
 * refused (too many new visits from one network) the page says so and offers to try again; it never asks for an
 * invite. A workspace that ends while the page is open is said to have ended, and a new one starts only when asked.
 */

type State = "checking" | "open" | "closed" | "unavailable" | "ended" | "switch";

/** An invite for another reader, refused while this browser is inside: the API's sentence, naming both, and the invite. */
type SwitchOffer = { invite: string; sentence: string };

const INVITE_IN_FRAGMENT = /(?:^#|&)invite=([^&]+)/;

/**
 * The invite in the address bar, if any, taken out of it at once so it is not left on screen or in a copied URL; an
 * invite that is not a valid escape sequence is taken out too, and comes back as `damaged` (lib/address safeDecode).
 */
function takeInviteFromAddress(): string | null | { damaged: true } {
  const found = INVITE_IN_FRAGMENT.exec(window.location.hash);
  if (!found) return null;
  window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
  return safeDecode(found[1]) ?? { damaged: true };
}

const DAMAGED_INVITE = "This invite link is damaged. Open it again from the message it came in, or paste it below.";

/**
 * Ask for a session one tab at a time. Two tabs opened at once each asked with no cookie, so the server made two
 * sessions and the browser kept whichever cookie arrived last: a contract added in the first tab before the second's
 * answer arrived then belonged to a workspace neither tab could read (reproduced on staging with a slow second tab,
 * 2026-10-13). Under the lock the second tab asks after the first has its cookie, and the server answers a request that
 * carries a working session with that same session (backend api/access.py visit), so both tabs share one workspace.
 * A browser without the Web Locks API asks at once, as before.
 */
async function visitOneTabAtATime(): Promise<AccessView> {
  const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
  if (!locks) return visit();
  // A lock held too long by another tab, or refused (site storage blocked), falls back to asking at once (review).
  const signal = typeof AbortSignal.timeout === "function" ? AbortSignal.timeout(LOCK_WAIT_MS) : undefined;
  try {
    return await locks.request("verity-first-visit", { signal }, () => visit());
  } catch (error) {
    if (error instanceof DOMException && ["AbortError", "TimeoutError", "SecurityError", "InvalidStateError"].includes(error.name)) return visit();
    throw error;
  }
}

// How long a tab waits for another tab's first visit before asking itself.
const LOCK_WAIT_MS = 15_000;

export function AccessGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>("checking");
  const [invite, setInvite] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  // Anonymous health names no provider or model, only where the model runs; nothing is claimed until it answers.
  const [apiHealth, setApiHealth] = useState<Health | null>(null);
  const [demo, setDemo] = useState<{ retentionDays: number } | null>(null);
  // Whether the API said which door it is; the workbench opens either way, but claims neither door until it has.
  const [modeKnown, setModeKnown] = useState(true);
  // Who this browser is inside as, and an invite for someone else waiting for the person's word (never switched unasked).
  const [reader, setReader] = useState<string | null>(null);
  const [offer, setOffer] = useState<SwitchOffer | null>(null);
  const demoRef = useRef(false);

  const startVisit = useCallback(async (): Promise<State> => {
    try {
      const visited = await visitOneTabAtATime();
      setDemo({ retentionDays: visited.retentionDays ?? 7 });
      setProblem(null);
      return "open";
    } catch (error) {
      setProblem(errorMessage(error));
      return "unavailable";
    }
  }, []);

  const settle = useCallback(
    async (access: AccessView): Promise<State> => {
      demoRef.current = access.anonymous;
      setReader(access.anonymous ? null : (access.subject ?? null));
      if (access.anonymous) {
        if (access.entered) {
          setDemo({ retentionDays: access.retentionDays ?? 7 });
          return "open";
        }
        return startVisit();
      }
      return access.entered ? "open" : "closed";
    },
    [startVisit],
  );

  useEffect(() => {
    let cancelled = false;
    const arrive = async () => {
      // Whatever the address carried, the page ends at the door or in the workbench, never on "Opening the workbench".
      let waiting: SwitchOffer | null = null;
      try {
        const carried = takeInviteFromAddress();
        if (typeof carried === "object" && carried !== null) {
          if (!cancelled) setProblem(DAMAGED_INVITE);
        } else if (carried) {
          try {
            await enterWithInvite(carried);
            if (!cancelled) setProblem(null);
          } catch (error) {
            // Another reader is inside: nothing was changed, and nothing is until the person says which (authz 1).
            if (!isConflict(error)) throw error;
            waiting = { invite: carried, sentence: errorMessage(error) };
          }
        }
      } catch (error) {
        if (!cancelled) setProblem(errorMessage(error));
      }
      try {
        const access = await getAccess();
        const next = await settle(access);
        if (!cancelled) {
          setModeKnown(true);
          setOffer(waiting);
          setState(waiting && next === "open" ? "switch" : next);
        }
      } catch {
        // The API did not answer. The workbench says so in its own words; the door has nothing to add, and claims
        // no door (AccessModeKnown).
        if (!cancelled) {
          setModeKnown(false);
          setState("open");
        }
      }
    };
    void arrive();
    health()
      .then((answer) => {
        if (!cancelled) setApiHealth(answer);
      })
      .catch(() => undefined);
    // A session that ends while the page is open: the next request is refused, and the door closes. In a public demo
    // the workspace has ended; a new one is not started behind the visitor's back.
    const close = () => setState(demoRef.current ? "ended" : "closed");
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
  }, [settle]);

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

  /** The person chose: switch to the invited reader (the API is told they chose), or stay as the reader inside. */
  const choose = async (switching: boolean) => {
    if (!offer || busy) return;
    if (!switching) {
      setOffer(null);
      setState("open");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await enterWithInvite(offer.invite, { replace: true });
      setOffer(null);
      setState(await settle(await getAccess()));
    } catch (error) {
      setProblem(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const again = async () => {
    if (busy) return;
    setBusy(true);
    const next = await startVisit();
    setBusy(false);
    setState(next);
  };

  const place = modelPlace(apiHealth);
  if (state === "open")
    return (
      <AccessModeKnown.Provider value={modeKnown}>
        <PublicDemo.Provider value={demo}>
          <Reader.Provider value={reader}>{children}</Reader.Provider>
        </PublicDemo.Provider>
      </AccessModeKnown.Provider>
    );
  // While the API is asked, the frame the visitor is about to see, not an empty page (the first paint on a slow phone
  // was blank until the session answered: lab LCP 4.4 s, 2026-10-09).
  if (state === "checking")
    return (
      <div className={styles.root} data-stage="empty" aria-busy="true">
        <section className={door.page} aria-label="Live workbench">
          <header className={door.topbar}>
            <Brand />
            <div className={door.topRight}>
              <TopLinks />
            </div>
          </header>
          <p className={door.opening} role="status">
            Opening the workbench
          </p>
        </section>
      </div>
    );
  if (state === "switch" && offer) {
    // The API's sentence names both readers; the button names the one the link is for.
    const invited = /The link is for (.+?);/.exec(offer.sentence)?.[1] ?? "the invited reader";
    return (
      <div className={styles.root} data-stage="empty">
        <section id="main" tabIndex={-1} className={door.page} aria-label="Live workbench">
          <header className={door.topbar}>
            <Brand />
            <div className={door.topRight}>
              <TopLinks />
            </div>
          </header>
          <div className={door.gate}>
            <h1 className={door.title}>The live Verity workbench</h1>
            <p className={door.lead}>{offer.sentence}</p>
            <p className={door.gateNote}>
              What you add is kept in the workspace of the reader you are inside as. Switching signs this browser in as the reader the link was made for; the
              other reader&apos;s work stays where it is.
            </p>
            <div className={door.gateForm}>
              <button type="button" className={door.primary} disabled={busy} onClick={() => void choose(true)}>
                {busy ? "Switching" : `Switch to ${invited}'s invite`}
              </button>
              <button type="button" className={door.secondary} disabled={busy} onClick={() => void choose(false)}>
                Stay as {reader ?? "the reader inside"}
              </button>
            </div>
            {problem && (
              <p className={door.error} role="alert">
                {problem}
              </p>
            )}
          </div>
        </section>
      </div>
    );
  }
  if (state === "unavailable" || state === "ended") {
    return (
      <div className={styles.root} data-stage="empty">
        <section id="main" tabIndex={-1} className={door.page} aria-label="Live workbench">
          <header className={door.topbar}>
            <Brand />
            <div className={door.topRight}>
              <TopLinks />
            </div>
          </header>
          <div className={door.gate}>
            <h1 className={door.title}>The live Verity workbench</h1>
            {state === "ended" ? (
              <p className={door.lead}>
                Your demo workspace has ended: it lasts {demo?.retentionDays ?? 7} days, and this browser&apos;s cookie for it is gone or has expired. What it
                held cannot be opened again. A new workspace starts empty.
              </p>
            ) : (
              <p className={door.error} role="alert">
                {problem}
              </p>
            )}
            <div className={door.gateForm}>
              <button type="button" className={door.primary} disabled={busy} onClick={again}>
                {busy ? "Starting" : state === "ended" ? "Start a new workspace" : "Try again"}
              </button>
            </div>
            <p className={door.gateNote}>
              Meanwhile:{" "}
              <a className={door.link} href="/state">
                Read the recorded research
              </a>
              , or the{" "}
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
  return (
    <div className={styles.root} data-stage="empty">
      <section id="main" tabIndex={-1} className={door.page} aria-label="Live workbench">
        <header className={door.topbar}>
          <Brand />
          <div className={door.topRight}>
            <TopLinks />
            <span className={door.preview}>
              <span className={door.previewDot} aria-hidden="true" />
              Private preview
            </span>
          </div>
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
                ? // Everything a question sends, listed (analysis/service.py build_user_message), not only the sections: the
                  // file's name and the guidance go too, and the opening sections when retrieval ranks none (counter-review).
                  `Each question is sent to ${place.place}, where the model runs, with any guidance, the contract's file name and sections of the contract.`
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
