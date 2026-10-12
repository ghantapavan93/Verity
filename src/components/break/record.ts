/**
 * The record /break tells (break-record.json, written by backend/scripts/export_break_record.py from recorded stores
 * and re-checked by backend/tests/test_break_record.py), and the few things the page works out from it: which words of
 * a quote the pre-registered expected answer relies on, which characters differ between a quote and the text at its
 * offsets, and the rejected check's counts. Nothing here decides anything the record did not.
 */

export interface SpanRecord {
  sectionId: string;
  start: number;
  end: number;
  quote: string;
  verified: boolean;
  method: string;
  matchCount: number | null;
  citedSectionLabel: string;
}

export interface RetrievalSlice {
  rank: number;
  label: string;
  sectionId: string;
  number: string;
  heading: string;
  characters: number;
  sliceStart: number;
  sliceEnd: number;
  truncated: boolean;
}

export interface SessionRecord {
  session: string;
  runId: string;
  createdAt: string;
  model: string;
  provider: string;
  promptVersion: string;
  promptHash: string;
  options: Record<string, string | number>;
  latencyMs: number;
  inputTokens: number | null;
  outputTokens: number | null;
  documentSha256: string;
  recordedInputSha256: string;
  retrieval: RetrievalSlice[];
  rawOutput: string;
  proposal: { conclusion: string; statusHint: string; evidence: { citedLabel: string; quote: string }[] };
  finding: {
    id: string;
    topic: string;
    conclusion: string;
    status: "pass" | "needs_review" | "missing" | "unresolved";
    statusSource: string;
    statusReason: string | null;
    spans: SpanRecord[];
    policy: { status: string; statusSource: string; statusReason: string | null; deterministic: boolean; summary: string };
  };
  adjudication: { label: "wrong_party" | "correct" | "no_attribution"; premiseAccepted: boolean | null; note: string };
}

export interface SourceRecord {
  title: string;
  company: string;
  form: string;
  filingDate: string;
  accession: string;
  exhibit: string;
  url: string;
  sha256Original: string;
  /** The filing's bytes before the script tag SEC appends to every response (export_break_record.filing_sha256). */
  sha256Filing: string;
  sha256Tested: string;
  conversion: { tool: string; lost: string[] };
  reuseNote: string;
}

export interface CaseRecord {
  id: string;
  family: string;
  question: string;
  expectedAnswer: string;
  requiredConditions: string[];
  decisivePassages: { sectionId: string; heading: string; quote: string }[];
  source: SourceRecord;
  input: { system: string; user: string; sha256: string };
  sessions: SessionRecord[];
  sections: Record<string, { ordinal: number; number: string; heading: string; text: string }>;
}

export type MissReason = "flagged" | "no_parties" | "no_quotes" | "no_actor_in_answer" | "no_party_in_quote" | "actor_also_in_quote";

export interface VerdictRow {
  set: "diagnostic" | "unseen";
  session: string;
  case: string;
  finding: string;
  label: "wrong_party" | "correct" | "no_attribution";
  flagged: boolean;
  why: MissReason | string;
  parties: string[];
  actingInAnswer: string[];
  actingInQuote: string[];
  reason: string | null;
  source: string;
  question?: string;
  conclusion?: string;
  quotes?: string[];
  labelNote?: string;
}

export interface BreakRecord {
  schema: string;
  evaluation: Record<string, { file: string; sha256: string }>;
  headline: CaseRecord;
  rejectedFix: { commit: string; policy: string; function: string; rows: VerdictRow[] };
  counterexample: { caught: CaseRecord; falseAlarm: CaseRecord };
  /** How many email addresses are masked in the headline's input, as the Input panel shows it. */
  masking: { inInput: number; mask: string; names: number; nameMask: string };
}

/** A counterexample as the page renders it: the question, the source, and each session's finding and label. */
export interface CounterCase {
  id: string;
  question: string;
  source: SourceRecord;
  sessions: Pick<SessionRecord, "session" | "finding" | "adjudication">[];
}

export interface PageRecord extends Omit<BreakRecord, "counterexample"> {
  counterexample: { caught: CounterCase; falseAlarm: CounterCase };
}

/** The record without what the page never renders (the counterexamples' inputs, outputs and section texts). */
export function forPage(record: BreakRecord): PageRecord {
  const counter = (c: CaseRecord): CounterCase => ({
    id: c.id,
    question: c.question,
    source: c.source,
    sessions: c.sessions.map((s) => ({ session: s.session, finding: s.finding, adjudication: s.adjudication })),
  });
  return { ...record, counterexample: { caught: counter(record.counterexample.caught), falseAlarm: counter(record.counterexample.falseAlarm) } };
}

/** Shorter shared runs are coincidences of wording ("the Buyer"), not the passage. */
const MIN_SHARED = 20;

/**
 * The longest run of characters ``quote`` shares with any of ``passages``, trimmed to whole words; null when shorter
 * than MIN_SHARED. Used to mark the words of a model's quote that the case's pre-registered passages also cite.
 */
export function sharedRun(quote: string, passages: string[]): { start: number; end: number } | null {
  let best = { start: 0, end: 0 };
  for (const passage of passages) {
    let previous = new Array<number>(passage.length + 1).fill(0);
    for (let i = 1; i <= quote.length; i++) {
      const current = new Array<number>(passage.length + 1).fill(0);
      for (let j = 1; j <= passage.length; j++) {
        if (quote[i - 1] === passage[j - 1]) {
          current[j] = previous[j - 1] + 1;
          if (current[j] > best.end - best.start) best = { start: i - current[j], end: i };
        }
      }
      previous = current;
    }
  }
  let { start, end } = best;
  const word = /[\p{L}\p{N}]/u;
  // A run that begins or ends inside a word is cut back to the word boundary.
  if (start > 0 && word.test(quote[start - 1]) && word.test(quote[start])) while (start < end && word.test(quote[start])) start++;
  if (end < quote.length && word.test(quote[end]) && word.test(quote[end - 1])) while (end > start && word.test(quote[end - 1])) end--;
  while (start < end && !word.test(quote[start])) start++;
  while (end > start && !word.test(quote[end - 1])) end--;
  return end - start >= MIN_SHARED ? { start, end } : null;
}

/**
 * The words of a text, casefolded. A simpler comparison than the verifier's typed tier (backend/app/verify/spans.py),
 * which also keeps figures such as 1,500 and clause numbers whole: what a browser can check by itself.
 */
export function wordsOf(text: string): string[] {
  return (text.match(/[\p{L}\p{N}]+/gu) ?? []).map((w) => w.toLowerCase());
}

export interface DiffPiece {
  text: string;
  changed: boolean;
}

function pieces(text: string, kept: boolean[]): DiffPiece[] {
  const out: DiffPiece[] = [];
  for (let i = 0; i < text.length; i++) {
    const changed = !kept[i];
    const last = out[out.length - 1];
    if (last && last.changed === changed) last.text += text[i];
    else out.push({ text: text[i], changed });
  }
  return out;
}

/** Which characters of ``left`` and ``right`` lie outside their longest common subsequence: the differences. */
export function charDiff(left: string, right: string): { same: boolean; left: DiffPiece[]; right: DiffPiece[] } {
  const n = left.length;
  const m = right.length;
  const table = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i][j] = left[i] === right[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const keptLeft = new Array<boolean>(n).fill(false);
  const keptRight = new Array<boolean>(m).fill(false);
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (left[i] === right[j]) {
      keptLeft[i++] = true;
      keptRight[j++] = true;
    } else if (table[i + 1][j] >= table[i][j + 1]) i++;
    else j++;
  }
  return { same: left === right, left: pieces(left, keptLeft), right: pieces(right, keptRight) };
}

/**
 * The rejected check over one evaluation set, counted two ways. A question is a case; a finding is one answer the model
 * gave to it in one session, and a session can give several (P-14 gave two). Correct findings are counted apart: a
 * case can hold a wrong-party finding and a correct one, so the two question counts overlap and are not added.
 */
export function fixScore(rows: VerdictRow[], set: VerdictRow["set"]) {
  const wrong = rows.filter((r) => r.set === set && r.label === "wrong_party");
  const correct = rows.filter((r) => r.set === set && r.label === "correct");
  const cases = [...new Set(wrong.map((r) => r.case))];
  const caughtIn = (c: string) => wrong.filter((r) => r.case === c);
  return {
    questions: cases.length,
    caughtEverySession: cases.filter((c) => caughtIn(c).every((r) => r.flagged)).length,
    caughtAnySession: cases.filter((c) => caughtIn(c).some((r) => r.flagged)).length,
    findings: wrong.length,
    caughtFindings: wrong.filter((r) => r.flagged).length,
    correctFindings: correct.length,
    loweredFindings: correct.filter((r) => r.flagged).length,
  };
}

/** A party as the agreement defines it: the defined term between curly quotes, and the name the definition opens with. */
export interface DefinedParty {
  term: string;
  name: string;
  definition: string;
  heading: string;
}

/**
 * The parties the pre-registered answer cites from outside the clause the model quoted: their definitions, read from the
 * record's text. A display aid: the term is found by its curly quotes, not checked against the agreement.
 */
export function definedParties(c: CaseRecord, citedSectionId: string): DefinedParty[] {
  return c.decisivePassages.flatMap((p) => {
    if (p.sectionId === citedSectionId) return [];
    const term = /\((?:the\s+)?“([^”]+)”\)\s*$/u.exec(p.quote)?.[1];
    const name = p.quote.split(",")[0].trim();
    return term && name && name !== p.quote.trim() ? [{ term, name, definition: p.quote, heading: p.heading }] : [];
  });
}

/** Where each phrase first occurs in the text, in text order, dropping any that overlap an earlier one. */
export function firstOccurrences(text: string, phrases: { phrase: string; kind: number }[]): { start: number; end: number; kind: number }[] {
  const found = phrases
    .map(({ phrase, kind }) => ({ start: text.indexOf(phrase), end: text.indexOf(phrase) + phrase.length, kind }))
    .filter((r) => r.start >= 0)
    .sort((a, b) => a.start - b.start);
  return found.filter((r, i) => i === 0 || r.start >= found[i - 1].end);
}

export function listed(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** What the rejected check saw on one finding, in words, from the verdict's own fields. */
export function whyMissed(row: VerdictRow): string {
  switch (row.why) {
    case "flagged":
      return `It lowered the pass: ${row.reason}.`;
    case "no_parties":
      return "It read no parties from the contract's opening, so it had no one to compare.";
    case "no_quotes":
      return "The finding had no verified quote to compare with.";
    case "no_actor_in_answer":
      return "It found no party of the opening acting in the answer, so it had nothing to compare.";
    case "no_party_in_quote":
      return "The quote names none of the parties it read from the opening.";
    case "actor_also_in_quote":
      return `It read ${listed(row.actingInAnswer)} as acting in the answer, and ${listed(row.actingInQuote)} as acting in the quote too, so the two agreed.`;
    default:
      return row.why;
  }
}
