/**
 * Nothing the record says is cut off or pushed out of its box (the layout spec's rule). A 68-character file name with no
 * break point, as document-management exports name contracts, widened the questions pane past the screen at 375, 768 and
 * 1024 px, and a 91-character one at 1280 and 1440: the pane is a grid with hidden overflow and no declared columns, so
 * its one implicit track grew to the widest row that does not scroll (the header's document chip), and every row was
 * clipped with it: the status, the conclusion, the verified quote, Ctrl K and Send (stress test, 2026-10-30).
 *
 * Two primitives hold the class, checked here over every stylesheet, since jsdom lays nothing out: every grid that clips
 * declares its columns with a definite minimum, so no row can widen its siblings; and text the record supplies may break
 * anywhere it must, from the root, so an unbroken token wraps inside its box instead of setting the box's width.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function stylesheets(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return stylesheets(path);
    return name.endsWith(".css") ? [path] : [];
  });
}

/** Each innermost rule of a stylesheet, comments removed: its selector and its declarations. */
function rules(css: string): { selector: string; body: string }[] {
  const plain = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...plain.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim(), body: m[2] }));
}

/** The tracks of a grid-template-columns value, a repeat() unrolled to its track list. */
function tracks(value: string): string[] {
  const unrolled = value.replace(/repeat\(\s*[^,]+,\s*((?:[^()]|\([^()]*\))+)\)/g, "$1");
  return unrolled.match(/minmax\([^()]*\)|fit-content\([^()]*\)|[^\s()]+/g) ?? [];
}

/** A track whose minimum is definite: a length or percentage, or minmax() with one. `auto`, a bare fr and the content
 *  keywords all take their minimum from the content, which is what let one row widen the pane. */
function definite(track: string): boolean {
  const min = /^minmax\(\s*([^,]+),/.exec(track)?.[1]?.trim() ?? track;
  return /^(?:0|-?\d*\.?\d+(?:px|rem|em|%|vw|vh|dvh|ch))$/.test(min);
}

describe("a box that clips", () => {
  it("is never a grid whose columns grow with their widest content", () => {
    const loose: string[] = [];
    for (const path of stylesheets(join(process.cwd(), "src"))) {
      for (const { selector, body } of rules(readFileSync(path, "utf8"))) {
        if (!/display:\s*(?:inline-)?grid/.test(body) || !/overflow(?:-x)?:\s*(?:hidden|clip)/.test(body)) continue;
        const columns = /grid-template-columns:\s*([^;]+)/.exec(body)?.[1];
        if (!columns || !tracks(columns).every(definite)) loose.push(`${path.split("src")[1]} ${selector.split("\n").at(-1)}: ${columns ?? "implicit auto"}`);
      }
    }
    expect(loose).toEqual([]);
  });

  it("control: the track reading tells a definite minimum from a content one", () => {
    expect(tracks("56px minmax(0, 1fr)").every(definite)).toBe(true);
    expect(tracks("repeat(auto-fit, minmax(128px, 1fr))").every(definite)).toBe(true);
    expect(tracks("repeat(2, minmax(0, 1fr))").every(definite)).toBe(true);
    for (const value of ["1fr", "auto", "minmax(auto, 1fr)", "24px 1fr", "max-content", "fit-content(200px)"]) {
      expect(tracks(value).every(definite), value).toBe(false);
    }
  });
});

describe("text the record supplies", () => {
  it("may break anywhere it must, from the root", () => {
    const root = rules(readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8")).find((r) => /(^|,)\s*body\s*$/m.test(r.selector));
    expect(root?.body).toMatch(/overflow-wrap:\s*anywhere/);
  });
});
