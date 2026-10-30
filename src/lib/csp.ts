/**
 * The page's script policy: no inline script runs unless the server put it there for this response. The policy allowed
 * every inline script, so a script that reached the page by any other way would have run (stress test, 2026-10-30, K64).
 * A fresh nonce for every request (src/proxy.ts), and a script runs only when it carries it or was loaded by one that
 * does ('strict-dynamic': Next's own chunks); 'unsafe-inline' is never in the policy. Next reads the nonce from this
 * header while it renders and puts it on its own scripts, which is why every page is rendered per request (app/layout).
 *
 * Only scripts are governed here, and the frames and plugins beside them; styles, images and connections are not, since
 * the motion system writes style attributes and the API may be another origin. The static /state export has no server
 * and so no proxy: its host sets its headers (deploy/).
 */

/** 128 random bits, base64: unguessable, and new for every response. */
export function newNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

/**
 * The Content-Security-Policy for one response. `dev`: the development server, where React needs eval to rebuild server
 * error stacks (Next's guide); a production build never gets it.
 */
export function contentSecurityPolicy(nonce: string, { dev = false }: { dev?: boolean } = {}): string {
  const script = ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", ...(dev ? ["'unsafe-eval'"] : [])];
  return [`script-src ${script.join(" ")}`, "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'"].join("; ");
}
