import { afterEach, describe, expect, it, vi } from "vitest";
import { apiBase, health, unreachable } from "./api";

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

/** The same expiry, seen the other way: the gate redirects to its own origin and the browser blocks the request. */
describe("a request that fails outright", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("says the API is not reachable, without inventing a cause, on a local address", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    await expect(health()).rejects.toThrow("The workbench API at http://127.0.0.1:8000 is not reachable.");
    expect(unreachable("http://127.0.0.1:8000")).not.toContain("sign-in");
  });

  it("names the expired sign-in as the likely cause behind an access gate", () => {
    expect(unreachable("https://workbench.example")).toBe(
      "The workbench API at https://workbench.example is not reachable. If this page has been open for a long time, your sign-in may have expired: reload the page.",
    );
  });
});

/**
 * A production build reaches the API on its own origin unless told otherwise. Release review, 2026-10-08: the live build
 * was made without NEXT_PUBLIC_API_URL and sent every remote browser to its own 127.0.0.1:8000.
 */
describe("where the interface finds the API", () => {
  it("is its own origin in a production build that names none", () => {
    expect(apiBase(undefined, true)).toBe("");
  });

  it("is what the build names, without a trailing slash", () => {
    expect(apiBase("https://workbench.example/", true)).toBe("https://workbench.example");
    expect(apiBase("", true)).toBe(""); // named as the same origin explicitly
  });

  it("control: a development build keeps the API's local port", () => {
    expect(apiBase(undefined, false)).toBe("http://127.0.0.1:8000");
  });

  it("says the site's own API is unreachable, never an empty address", () => {
    expect(unreachable("")).toMatch(/^The workbench API on this site is not reachable\./);
  });
});
