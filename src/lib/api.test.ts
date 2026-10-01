import { afterEach, describe, expect, it, vi } from "vitest";
import { health } from "./api";

/** Behind Cloudflare Access an expired sign-in answers a request for data with a sign-in page, status 200. */
describe("a page in place of data", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("becomes a sentence about the sign-in, not a JSON parse error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<!doctype html><title>Sign in</title>", { status: 200, headers: { "content-type": "text/html" } })),
    );
    await expect(health()).rejects.toThrow(/sign-in may have expired/);
  });

  it("still reads JSON answers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: { "content-type": "application/json" } })),
    );
    await expect(health()).resolves.toEqual({ status: "ok" });
  });
});
