/**
 * The door decides nothing: the API says whether a session is needed and whether this browser has one. What is
 * tested here is the exchange and the asking: an invite carried in the link is exchanged before anything else
 * mounts and leaves the address bar; without a session nothing behind the door is rendered, so nothing behind it
 * asks the API; a refusal while the page is open closes the door again.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { enterWithInvite, getAccess, health, visit } from "@/lib/api";

const api = vi.hoisted(() => ({
  getAccess: vi.fn<typeof getAccess>(),
  enterWithInvite: vi.fn<typeof enterWithInvite>(),
  health: vi.fn<typeof health>(),
  visit: vi.fn<typeof visit>(),
}));

vi.mock("@/lib/api", () => ({
  ACCESS_REQUIRED_EVENT: "verity:access-required",
  getAccess: api.getAccess,
  enterWithInvite: api.enterWithInvite,
  health: api.health,
  visit: api.visit,
  errorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
}));

import { AccessGate } from "./AccessGate";

const OUT = { required: true, entered: false, subject: null, anonymous: false };
const IN = { required: true, entered: true, subject: "min-kyu", anonymous: false };
const OFF = { required: false, entered: true, subject: null, anonymous: false };

function Inside() {
  return <p>the workbench</p>;
}

describe("AccessGate", () => {
  beforeEach(() => {
    api.getAccess.mockReset();
    api.enterWithInvite.mockReset();
    api.health.mockReset();
    api.visit.mockReset();
    api.health.mockRejectedValue(new Error("no answer"));
    window.history.replaceState(null, "", "/");
  });
  afterEach(cleanup);

  it("lets the workbench mount when the API has no gate", async () => {
    api.getAccess.mockResolvedValue(OFF);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect(screen.queryByText("the workbench")).toBeNull();
    expect(await screen.findByText("the workbench")).toBeTruthy();
    expect(api.enterWithInvite).not.toHaveBeenCalled();
  });

  it("exchanges the invite a link carries, takes it out of the address bar, and keeps the page the link was for", async () => {
    window.history.replaceState(null, "", "/?document=d1&run=r1#invite=v1.abc.def");
    api.enterWithInvite.mockResolvedValue(IN);
    api.getAccess.mockResolvedValue(IN);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect(window.location.hash).toBe("");
    expect(window.location.pathname + window.location.search).toBe("/?document=d1&run=r1");
    expect(await screen.findByText("the workbench")).toBeTruthy();
    expect(api.enterWithInvite).toHaveBeenCalledWith("v1.abc.def");
    expect(api.enterWithInvite.mock.invocationCallOrder[0]).toBeLessThan(api.getAccess.mock.invocationCallOrder[0]);
  });

  it("renders nothing behind the door without a session, and asks for the link in a restrained way", async () => {
    api.getAccess.mockResolvedValue(OUT);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect(await screen.findByRole("heading", { name: "The live Verity workbench" })).toBeTruthy();
    expect(screen.queryByText("the workbench")).toBeNull();
    expect(screen.getByLabelText("Invite link")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Enter workbench" })).toBeTruthy();
    for (const theatre of [/sign up/i, /forgot/i, /google/i, /sso/i, /create account/i]) expect(screen.queryByText(theatre)).toBeNull();
  });

  it("opens on a pasted invite the API accepts, and says what the API said when it does not", async () => {
    api.getAccess.mockResolvedValue(OUT);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    const field = await screen.findByLabelText("Invite link");
    api.enterWithInvite.mockRejectedValueOnce(new Error("That invite is not valid, or it has expired. Ask for a new link."));
    fireEvent.change(field, { target: { value: "https://ivo.example/#invite=old" } });
    fireEvent.click(screen.getByRole("button", { name: "Enter workbench" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That invite is not valid, or it has expired. Ask for a new link.");
    expect(screen.queryByText("the workbench")).toBeNull();

    api.enterWithInvite.mockResolvedValueOnce(IN);
    fireEvent.change(field, { target: { value: "https://ivo.example/#invite=good" } });
    fireEvent.click(screen.getByRole("button", { name: "Enter workbench" }));
    expect(await screen.findByText("the workbench")).toBeTruthy();
    expect(api.enterWithInvite).toHaveBeenLastCalledWith("https://ivo.example/#invite=good");
  });

  it("says so when the invite in the link is refused, and still takes it out of the address bar", async () => {
    window.history.replaceState(null, "", "/#invite=expired");
    api.enterWithInvite.mockRejectedValue(new Error("That invite is not valid, or it has expired. Ask for a new link."));
    api.getAccess.mockResolvedValue(OUT);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect((await screen.findByRole("alert")).textContent).toContain("not valid");
    expect(window.location.hash).toBe("");
    expect(screen.queryByText("the workbench")).toBeNull();
  });

  it("exchanges an invite link opened in a tab that already shows the door, where only the fragment changes", async () => {
    api.getAccess.mockResolvedValueOnce(OUT);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect(await screen.findByRole("heading", { name: "The live Verity workbench" })).toBeTruthy();
    // The browser does not reload for a change of fragment; it only says the fragment changed.
    api.enterWithInvite.mockResolvedValue(IN);
    api.getAccess.mockResolvedValue(IN);
    window.history.replaceState(null, "", "/?document=d1&run=r1#invite=v1.abc.def");
    act(() => {
      window.dispatchEvent(new Event("hashchange"));
    });
    expect(await screen.findByText("the workbench")).toBeTruthy();
    expect(api.enterWithInvite).toHaveBeenCalledWith("v1.abc.def");
    expect(window.location.hash).toBe("");
    expect(window.location.pathname + window.location.search).toBe("/?document=d1&run=r1");
    // A fragment that carries no invite is nobody's business here.
    api.enterWithInvite.mockClear();
    window.history.replaceState(null, "", "/#section-4");
    act(() => {
      window.dispatchEvent(new Event("hashchange"));
    });
    expect(api.enterWithInvite).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("#section-4");
  });

  it("closes again when the API refuses a request while the page is open", async () => {
    api.getAccess.mockResolvedValue(IN);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect(await screen.findByText("the workbench")).toBeTruthy();
    act(() => {
      window.dispatchEvent(new Event("verity:access-required"));
    });
    expect(screen.queryByText("the workbench")).toBeNull();
    expect(screen.getByRole("heading", { name: "The live Verity workbench" })).toBeTruthy();
  });

  it("tells a visitor without an invite what the workbench does and where to go instead, with real destinations", async () => {
    api.getAccess.mockResolvedValue(OUT);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    await screen.findByRole("heading", { name: "The live Verity workbench" });
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/PDF, DOCX or TXT/);
    expect(text).toMatch(/sample agreement/);
    expect(text).toMatch(/passage/);
    expect(screen.getByRole("navigation", { name: "Elsewhere" }).querySelector('a[href="/state"]')).toBeTruthy();
    expect(screen.getByRole("link", { name: /recorded research/i }).getAttribute("href")).toBe("/state");
    expect(screen.getByRole("link", { name: /source code/i }).getAttribute("href")).toBe("https://github.com/ghantapavan93/Verity");
    // Nothing is said about where the model runs until the API says.
    expect(text).not.toMatch(/runs on|model runs/i);
  });

  it("says where the model runs only as the API reports it", async () => {
    api.getAccess.mockResolvedValue(OUT);
    api.health.mockResolvedValue({ ok: true, provider: "", model: "", detail: "", access: "required", modelLocation: "server", modelHost: "" } as Awaited<
      ReturnType<typeof health>
    >);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect(await screen.findByText(/model runs on the Verity server/)).toBeTruthy();
  });
});

describe("AccessGate: a public demo", () => {
  const ANON_OUT = { required: true, entered: false, subject: null, anonymous: true, retentionDays: 7 };
  const ANON_IN = { ...ANON_OUT, entered: true };

  beforeEach(() => {
    api.getAccess.mockReset();
    api.enterWithInvite.mockReset();
    api.visit.mockReset();
    api.health.mockReset();
    api.health.mockRejectedValue(new Error("no answer"));
    window.history.replaceState(null, "", "/");
  });
  afterEach(cleanup);

  it("hands a first visit a workspace of its own and opens the workbench with no step in between", async () => {
    api.getAccess.mockResolvedValue(ANON_OUT);
    api.visit.mockResolvedValue(ANON_IN);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect(await screen.findByText("the workbench")).toBeTruthy();
    expect(api.visit).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText("Invite link")).toBeNull();
  });

  it("keeps the workspace a returning browser already has", async () => {
    api.getAccess.mockResolvedValue(ANON_IN);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect(await screen.findByText("the workbench")).toBeTruthy();
    expect(api.visit).not.toHaveBeenCalled();
  });

  it("says why it cannot open when the visit is refused, offers to try again, and never asks for an invite", async () => {
    api.getAccess.mockResolvedValue(ANON_OUT);
    api.visit.mockRejectedValueOnce(new Error("Too many new visits from your network in the last hour. Try again in 12 minutes."));
    api.visit.mockResolvedValueOnce(ANON_IN);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    expect(await screen.findByText(/Too many new visits/)).toBeTruthy();
    expect(screen.queryByLabelText("Invite link")).toBeNull();
    expect(screen.getByRole("link", { name: /recorded research/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("the workbench")).toBeTruthy();
  });

  it("says a workspace has ended and starts a new one only when asked", async () => {
    api.getAccess.mockResolvedValue(ANON_IN);
    api.visit.mockResolvedValue(ANON_IN);
    render(
      <AccessGate>
        <Inside />
      </AccessGate>,
    );
    await screen.findByText("the workbench");
    act(() => {
      window.dispatchEvent(new Event("verity:access-required"));
    });
    expect(await screen.findByText(/workspace has ended/i)).toBeTruthy();
    expect(screen.queryByLabelText("Invite link")).toBeNull();
    expect(api.visit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Start a new workspace" }));
    expect(await screen.findByText("the workbench")).toBeTruthy();
  });
});
