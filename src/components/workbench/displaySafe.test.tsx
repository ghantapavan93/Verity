/**
 * The text a person reads is the text that was checked. Ingest holds the contract, its name, guidance and questions to it;
 * nothing held the model's own strings, which the record keeps as the model wrote them. A direction override in a quote
 * displayed "fifteen (51) days" where the contract says fifteen (15), and an override in a topic or a conclusion reorders
 * whatever follows it (hostile-model review, 2026-10-30). Every surface shows such text through one primitive (lib/text
 * revealInvisible: shell/primitives Visible, or shownText for an attribute), which names each invisible character in place
 * and changes nothing in the record.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FindingView, SectionView } from "@/lib/types";
import { expectShownByName, hostile } from "./assistant/__fixtures__/hostile";
import { FindingCard } from "./assistant/FindingCard";
import { WithheldList } from "./assistant/RunOutcome";

afterEach(cleanup);

const SECTION: SectionView = { id: "s2", number: "2", heading: "Termination", text: "Customer may terminate upon fifteen (15) days' notice." } as SectionView;

function finding(over: Partial<FindingView> = {}): FindingView {
  return {
    id: "f1",
    topic: hostile("Termination topic"),
    status: "needs_review",
    statusSource: "model_hint",
    statusReason: null,
    conclusion: hostile("The model's conclusion"),
    modelConclusion: null,
    withheldConclusion: hostile("The withheld sentence"),
    evidenceKind: "passage",
    review: null,
    latestReviewId: 0,
    spans: [
      {
        sectionId: "s2",
        verified: true,
        method: "typed",
        quote: hostile("Customer may terminate"),
        start: 0,
        end: 20,
        citedSectionLabel: hostile("sec_2"),
        matchCount: 1,
        clauseLabel: null,
        sectionLabel: "§2 Termination",
      },
    ],
    relations: [],
    decidedBy: "model",
    ...over,
  } as unknown as FindingView;
}

describe("the model's strings on the answer's surfaces", () => {
  it("the card names every invisible character in the topic, the conclusion, the withheld sentence and the quote", () => {
    const { container } = render(
      <FindingCard
        finding={finding()}
        hasGuidance={false}
        sectionsById={new Map([["s2", SECTION]])}
        onJump={vi.fn()}
        onEvidence={vi.fn()}
        onFollowUp={vi.fn()}
      />,
    );
    expectShownByName(container, "Termination topic");
    expectShownByName(container, "The model's conclusion");
    expectShownByName(container, "The withheld sentence");
  });

  it("a withheld proposal names them too, in its topic, its sentence, its quote and the label it cited", () => {
    const withheld = finding({ status: "unresolved", spans: [{ ...finding().spans[0], sectionId: null, verified: false }] as FindingView["spans"] });
    const { container } = render(<WithheldList findings={[withheld]} sectionsById={new Map()} onEvidence={vi.fn()} />);
    expectShownByName(container, "Termination topic");
    expectShownByName(container, "Customer may terminate");
    expectShownByName(container, "sec_2");
  });

  it("control: right-to-left text and its joiners and marks are shown as written", () => {
    const persian = "\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u062f"; // a zero-width non-joiner inside a Persian word
    const arabic = "\u0661\u0665\u061c/\u0663"; // an Arabic letter mark between Arabic-Indic digits
    const { container } = render(
      <FindingCard
        finding={finding({ topic: persian, conclusion: arabic, withheldConclusion: null, spans: [] })}
        hasGuidance={false}
        sectionsById={new Map()}
        onJump={vi.fn()}
        onEvidence={vi.fn()}
        onFollowUp={vi.fn()}
      />,
    );
    expect(container.textContent).toContain(persian);
    expect(container.textContent).toContain(arabic);
    expect(container.textContent).not.toContain("U+");
  });
});

/**
 * The class, not the examples: no component renders a string the model wrote as a bare child or interpolates it into a
 * label. Each goes through Visible (`text={…}`) or shownText. A new surface that prints one raw fails here.
 */
describe("every surface", () => {
  const MODEL_FIELDS =
    "topic|conclusion|shownConclusion|withheldConclusion|modelConclusion|quote|observed|required|suggestedPosition|guidanceReference|citedSectionLabel|citedLabel";
  const bareChild = new RegExp(`(?<![=\\w])\\{\\s*[\\w.?!]+\\.(?:${MODEL_FIELDS})\\s*\\}`, "g");
  const interpolated = new RegExp(`\\$\\{\\s*[\\w.?!]+\\.(?:${MODEL_FIELDS})\\s*\\}`, "g");

  function sources(dir: string): string[] {
    return readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) return name === "__fixtures__" ? [] : sources(path);
      return /\.tsx$/.test(name) && !/\.test\.tsx$/.test(name) ? [path] : [];
    });
  }

  it("renders no model-written string except through the display primitive", () => {
    const raw: string[] = [];
    for (const path of sources(join(process.cwd(), "src/components/workbench"))) {
      readFileSync(path, "utf8")
        .split("\n")
        .forEach((line, i) => {
          for (const match of [...line.matchAll(bareChild), ...line.matchAll(interpolated)]) raw.push(`${path.split("workbench")[1]}:${i + 1} ${match[0]}`);
        });
    }
    expect(raw).toEqual([]);
  });
});
