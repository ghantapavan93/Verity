/**
 * The door decides nothing: the API says whether a session is needed and whether this browser has one. What is
 * tested here is the exchange and the asking: an invite carried in the link is exchanged before anything else
 * mounts and leaves the address bar; without a session nothing behind the door is rendered, so nothing behind it
 * asks the API; a refusal while the page is open closes the door again.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { enterWithInvite, getAccess } from "@/lib/api";

const api = vi.hoisted(() => ({
  getAccess: vi.fn<typeof getAccess>(),
  enterWithInvite: vi.fn<typeof enterWithInvite>(),
}));

vi.mock("@/lib/api", () => ({
  ACCESS_REQUIRED_EVENT: "verity:access-required",
  getAccess: api.getAccess,
  enterWithInvite: api.enterWithInvite,
  errorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
}));

import { AccessGate } from "./AccessGate";

const OUT = { required: true, entered: false, subject: null };
const IN = { required: true, entered: true, subject: "min-kyu" };
const OFF = { required: false, entered: true, subject: null };

function Inside() {
  return <p>the workbench</p>;
}

describe("AccessGate", () => {
  beforeEach(() => {
    api.getAccess.mockReset();
    api.enterWithInvite.mockReset();
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
    expect(await screen.findByRole("heading", { name: "Private engineering preview" })).toBeTruthy();
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
    expect(await screen.findByRole("heading", { name: "Private engineering preview" })).toBeTruthy();
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
    expect(screen.getByRole("heading", { name: "Private engineering preview" })).toBeTruthy();
  });
});
