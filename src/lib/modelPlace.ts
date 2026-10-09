import type { Health } from "./types";

/**
 * Where the model runs, as the API reports it (HealthOut.modelLocation), so no sentence claims a contract stays on a
 * machine it has left. Null while the API has not said: nothing is claimed then. Triage risk review, 2026-10-09: the
 * interface said "run on this machine; no contract is sent to a hosted model" whatever the deployment.
 */
export function modelPlace(health: Health | null): { hosted: boolean; place: string } | null {
  if (!health || !health.modelLocation) return null;
  return health.modelLocation === "hosted" ? { hosted: true, place: health.modelHost || "a hosted GPU" } : { hosted: false, place: "the Verity server" };
}
