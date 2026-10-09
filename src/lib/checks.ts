import { codeAccount, decidedByCode, passageLabel, type FindingView, type SectionView } from "./types";

/**
 * What was checked about one finding, and by whom, as rows a reader can scan. Every row is read from a recorded field:
 * the spans the verifier located, the status source and reason the policy recorded, how many sections the model was
 * handed, and the person's review. Nothing here infers; a row says "not checked" where nothing checked.
 *
 * Found by a real-model evaluation (2026-10-09): a quote that says 10% stood under an answer saying 5%, and the card
 * read "1 passage found in the document text" in the pass colour. The quote's location was verified; whether it
 * supports the answer never is, by code. The two were shown as one fact.
 */
export type CheckBy = "code" | "model" | "person" | "nobody";

export type CheckRow = { key: "quote" | "support" | "comparison" | "context" | "person"; label: string; text: string; by: CheckBy };

const VERBATIM = new Set(["exact", "normalized"]);

function located(method: string): string {
  const base = method.split(":").pop() ?? method;
  if (VERBATIM.has(base)) return "word for word";
  if (base === "casefold") return "word for word, case aside";
  return "with the same words and numbers, spacing and punctuation aside";
}

export function checkLedger(
  finding: FindingView,
  hasGuidance: boolean,
  sectionsById: Map<string, SectionView>,
  context: { text: string; partial: boolean } | null,
): CheckRow[] {
  const cited = finding.spans.length;
  const found = finding.spans.filter((s) => s.verified);
  const rows: CheckRow[] = [];

  if (finding.evidenceKind === "coverage") {
    rows.push({
      key: "quote",
      label: "Passages",
      text: `Read, not relied on: ${found.length} provision${found.length === 1 ? "" : "s"} the model looked at; it reports that none states the point`,
      by: "nobody",
    });
    rows.push({
      key: "support",
      label: "Absent?",
      text: "Not checked by code: that the point is absent is the model's reading of what it was handed",
      by: "model",
    });
  } else if (cited === 0) {
    rows.push({ key: "quote", label: "Quote", text: "No passage cited", by: "nobody" });
  } else {
    const first = found[0];
    const section = first?.sectionId ? sectionsById.get(first.sectionId) : undefined;
    const where = first && section ? ` at ${passageLabel(first, section)}` : "";
    const withheld = cited - found.length;
    rows.push({
      key: "quote",
      label: "Quote",
      text:
        found.length === 0
          ? `Not found in the document text: ${cited} quoted passage${cited === 1 ? "" : "s"} withheld`
          : `Found in the document text${where}, ${located(first.method)}${
              found.length > 1 ? ` (${found.length} of ${cited} passages)` : ""
            }${withheld > 0 ? `; ${withheld} withheld` : ""}`,
      by: found.length > 0 ? "code" : "nobody",
    });
    rows.push({
      key: "support",
      label: "Supports it?",
      text: "Not checked by code: that the passage supports the answer is the model's reading",
      by: "model",
    });
  }

  const source = finding.statusSource || "model_hint";
  const account = codeAccount(source);
  if (decidedByCode(source) || source === "confirmed_days") {
    rows.push({
      key: "comparison",
      label: "Compared",
      text: finding.statusReason ? `${account.role}: ${finding.statusReason}` : account.sentence,
      by: "code",
    });
  } else if (source === "model_hint" && finding.statusReason) {
    // Code compared the periods and left the model's status standing: policy v3 lowers, never confirms. The comparison
    // is code's and is said; the status is not (round 2 review: AD15 read "Nothing" while code had compared 120 with 90).
    rows.push({ key: "comparison", label: "Compared", text: `Code compared: ${finding.statusReason}. The status is still the model's view.`, by: "code" });
  } else if (source === "no_evidence") {
    rows.push({ key: "comparison", label: "Compared", text: "Nothing: no passage was found to compare", by: "nobody" });
  } else {
    rows.push({
      key: "comparison",
      label: "Compared",
      text: hasGuidance
        ? "Nothing: code found no period in the passage and the guidance to compare; the status is the model's view"
        : "Nothing: no guidance was given to compare against; the status is the model's view",
      by: "nobody",
    });
  }

  if (context) {
    const said = context.text.charAt(0).toUpperCase() + context.text.slice(1);
    rows.push({ key: "context", label: "Read", text: context.partial ? `${said}; the other sections were not read` : said, by: "nobody" });
  }

  rows.push(
    finding.review
      ? {
          key: "person",
          label: "Person",
          text: `${finding.review.verdict === "confirmed" ? "Confirmed" : "Dismissed"} by ${finding.review.reviewer}`,
          by: "person",
        }
      : { key: "person", label: "Person", text: "Not reviewed yet", by: "nobody" },
  );
  return rows;
}

/** What a run concluded, from its findings by status: "1 needs review · 1 not found", never just "1 finding". */
export function runOutcome(outcomes: Record<string, number> | undefined, hasGuidance: boolean): string {
  const words: Record<string, string> = {
    needs_review: "needs review",
    missing: "not found",
    // Under policy v3 code lowers a status and never confirms one: a pass is the model's view.
    pass: hasGuidance ? "within guidance (model's view)" : "answered",
  };
  const parts = Object.entries(outcomes ?? {})
    .filter(([status, n]) => n > 0 && status in words)
    .sort(([a], [b]) => Object.keys(words).indexOf(a) - Object.keys(words).indexOf(b))
    .map(([status, n]) => `${n} ${words[status]}`);
  return parts.length > 0 ? parts.join(" · ") : "no finding";
}
