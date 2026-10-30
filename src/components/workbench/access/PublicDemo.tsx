"use client";

import { createContext } from "react";

/**
 * Set when the workbench is a public demo (backend/app/api/access.py visit): every browser is handed a workspace of its
 * own, deleted `retentionDays` after it was made. Null when readers enter by invitation.
 */
export const PublicDemo = createContext<{ retentionDays: number } | null>(null);

/**
 * False when the API could not say which door it is (`/api/access` failed): the workbench still opens and says what
 * failed in its own words, but nothing may claim a public demo or an invitation, since either may be false. A public
 * demo's visitor was told "Private preview" and "Every run is kept" when only that request failed (counter-review,
 * 2026-10-13).
 */
export const AccessModeKnown = createContext(true);

/**
 * The reader this browser is inside as, by invitation: the name the invite was made for (the API's AccessOut.subject).
 * Null when there is none to name (the gate is off, a public demo, or the API has not said). Shown so a reader can see
 * whose workspace they are adding to: an invite once switched the session silently (stress test, 2026-10-30, authz 1).
 */
export const Reader = createContext<string | null>(null);
