import { afterEach, describe, expect, it, vi } from "vitest";
import { POLL_MAX_MS, POLL_MS, apiBase, followRun, health, unreachable } from "./api";

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

/** A run followed by polling (the stream dropped, or the browser has none) asks less while nothing changes. */
describe("following a run by polling", () => {
  const detail = (stage: string, ahead: number | null) =>
    new Response(JSON.stringify({ id: "run1", stage, ahead, stages: [{ stage: "reading", detail: "4 sections" }] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  let visibility: DocumentVisibilityState = "visible";

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    visibility = "visible";
  });

  function polled(answers: () => Response) {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", undefined);
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
    const fetch = vi.fn(async () => answers());
    vi.stubGlobal("fetch", fetch);
    const ahead: (number | null)[] = [];
    const stop = followRun(
      "run1",
      () => {},
      () => {},
      () => {},
      (n) => ahead.push(n),
    );
    return { fetch, ahead, stop };
  }

  it("waits longer after each poll that finds nothing new, up to its ceiling, and passes on the queue", async () => {
    const { fetch, ahead, stop } = polled(() => detail("checking", 2));
    await vi.advanceTimersByTimeAsync(0);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(ahead).toEqual([2]);
    const waits = [POLL_MS, POLL_MS * 2, POLL_MS * 4, POLL_MAX_MS, POLL_MAX_MS];
    for (const [i, wait] of waits.entries()) {
      await vi.advanceTimersByTimeAsync(wait - 1);
      expect(fetch).toHaveBeenCalledTimes(i + 1);
      await vi.advanceTimersByTimeAsync(1);
      expect(fetch).toHaveBeenCalledTimes(i + 2);
    }
    stop();
  });

  it("control: a poll that finds the run moved asks again at the first pace", async () => {
    let ahead = 5;
    const { fetch, stop } = polled(() => detail("checking", ahead--));
    await vi.advanceTimersByTimeAsync(0);
    for (let i = 0; i < 4; i++) await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(fetch).toHaveBeenCalledTimes(5);
    stop();
  });

  it("asks nothing while the page is hidden, and asks at once when it is shown", async () => {
    const { fetch, stop } = polled(() => detail("checking", 1));
    await vi.advanceTimersByTimeAsync(0);
    visibility = "hidden";
    await vi.advanceTimersByTimeAsync(POLL_MAX_MS * 10);
    expect(fetch).toHaveBeenCalledTimes(1);
    visibility = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(0);
    expect(fetch).toHaveBeenCalledTimes(2);
    stop();
  });
});
