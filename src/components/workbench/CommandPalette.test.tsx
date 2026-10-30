import { render } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { CommandPalette } from "./CommandPalette";

/** Where focus goes when the palette closes: back to its opener, unless a command already moved it (fresh review,
 * 2026-10-30: the evidence sheet focused its close button, and the palette's cleanup took focus back to the rail). */
describe("CommandPalette focus", () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView ??= () => {}; // jsdom draws nothing, so it has no scrolling
  });

  function opened() {
    const opener = document.createElement("button");
    opener.textContent = "Search";
    document.body.append(opener);
    opener.focus();
    const view = render(<CommandPalette getCommands={() => []} onClose={() => {}} reduceMotion />);
    return { opener, view };
  }

  it("gives focus back to its opener when it closes", () => {
    const { opener, view } = opened();
    expect(document.activeElement).not.toBe(opener);
    view.unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it("leaves focus where a command put it", () => {
    const { opener, view } = opened();
    const sheet = document.createElement("button");
    sheet.textContent = "Close evidence";
    document.body.append(sheet);
    sheet.focus();
    view.unmount();
    expect(document.activeElement).toBe(sheet);
    opener.remove();
    sheet.remove();
  });
});
