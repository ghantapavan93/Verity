/**
 * Every page carries the browser's protections whatever edge is in front (a Cloudflare Tunnel adds none), the server's
 * software is never named, and the static export, which has no server, asks Next for no headers.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function load(env: Record<string, string>) {
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value);
  vi.resetModules();
  return (await import("../../next.config")).default;
}

describe("what every page tells the browser", () => {
  it("the server build sends the protections on every path and does not name Next", async () => {
    const config = await load({});
    expect(config.poweredByHeader).toBe(false);
    const rules = await config.headers!();
    expect(rules).toHaveLength(1);
    expect(rules[0].source).toBe("/:path*");
    const sent = Object.fromEntries(rules[0].headers.map((h) => [h.key, h.value]));
    expect(sent).toEqual({
      "Strict-Transport-Security": "max-age=31536000",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "Content-Security-Policy": "frame-ancestors 'none'",
    });
  });

  it("control: the static export asks for no headers and is still an export", async () => {
    const config = await load({ NEXT_PUBLIC_EXPORT: "state" });
    expect(config.headers).toBeUndefined();
    expect(config.output).toBe("export");
  });
});
