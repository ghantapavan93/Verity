import { NextResponse, type NextRequest } from "next/server";
import { contentSecurityPolicy, newNonce } from "@/lib/csp";

/**
 * Every page gets a script policy with a nonce of its own (lib/csp): set on the request, where Next reads it while it
 * renders and puts the nonce on its own scripts, and on the response, where the browser enforces it. No inline script
 * without that nonce runs (stress test, 2026-10-30, K64).
 */
export function proxy(request: NextRequest) {
  const policy = contentSecurityPolicy(newNonce(), { dev: process.env.NODE_ENV === "development" });
  const headers = new Headers(request.headers);
  headers.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

// Pages only: not the API, Next's built files, or the files in public/, which carry no script of their own; nor a
// prefetch, whose response is not a page the browser runs.
export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico|icon.svg|samples/|contract-state.json).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
