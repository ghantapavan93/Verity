// @vitest-environment node
/**
 * No inline script runs unless the server put it there for this response (stress test, 2026-10-30, K64): the policy,
 * its nonce, and the proxy that sets both on every page. The browser's enforcement is the e2e check (e2e/security.spec).
 */

import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { config, proxy } from "../proxy";
import { contentSecurityPolicy, newNonce } from "./csp";

function directives(policy: string): Map<string, string[]> {
  return new Map(
    policy.split(";").map((d) => {
      const [name, ...values] = d.trim().split(/\s+/);
      return [name, values];
    }),
  );
}

describe("the script policy", () => {
  it("lets a script run only with this response's nonce, or loaded by one that has it, and never inline", () => {
    const script = directives(contentSecurityPolicy("abc123"))?.get("script-src") ?? [];
    expect(script).toEqual(["'self'", "'nonce-abc123'", "'strict-dynamic'"]);
    expect(contentSecurityPolicy("abc123")).not.toContain("unsafe-inline");
  });

  it("adds eval only on the development server, and never 'unsafe-inline'", () => {
    expect(directives(contentSecurityPolicy("n", { dev: true })).get("script-src")).toContain("'unsafe-eval'");
    expect(contentSecurityPolicy("n", { dev: true })).not.toContain("unsafe-inline");
    expect(contentSecurityPolicy("n")).not.toContain("unsafe-eval");
  });

  it("keeps the frame and plugin protections the pages had", () => {
    const policy = directives(contentSecurityPolicy("n"));
    expect(policy.get("frame-ancestors")).toEqual(["'none'"]);
    expect(policy.get("object-src")).toEqual(["'none'"]);
    expect(policy.get("base-uri")).toEqual(["'none'"]);
  });

  it("draws a new, unguessable nonce for every response", () => {
    const drawn = new Set(Array.from({ length: 200 }, newNonce));
    expect(drawn.size).toBe(200);
    for (const nonce of drawn) expect(atob(nonce)).toHaveLength(16);
  });
});

describe("the proxy", () => {
  it("sets the same policy, with a fresh nonce, on the request Next renders and on the response the browser enforces", () => {
    const first = proxy(new NextRequest("http://localhost/?run=r1"));
    const second = proxy(new NextRequest("http://localhost/state"));
    const policy = first.headers.get("Content-Security-Policy") ?? "";
    expect(policy).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
    // NextResponse.next carries the request headers Next renders with under x-middleware-request-*.
    expect(first.headers.get("x-middleware-request-content-security-policy")).toBe(policy);
    expect(second.headers.get("Content-Security-Policy")).not.toBe(policy);
  });

  it("runs on pages, and not on the API, Next's built files or public files", () => {
    const source = new RegExp(`^${config.matcher[0].source}$`);
    for (const page of ["/", "/state", "/break"]) expect(source.test(page), page).toBe(true);
    for (const file of ["/api/runs", "/_next/static/chunks/main.js", "/icon.svg", "/samples/cloud-service-agreement.docx", "/contract-state.json"]) {
      expect(source.test(file), file).toBe(false);
    }
  });
});
