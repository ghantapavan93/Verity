/**
 * Where two texts differ, by their longest common subsequence: the /break page compares a quote with the text at its
 * offsets character by character, and a replaced clause is compared with its replacement word by word. Presentation
 * only: what is marked is what the two stored texts say, and no meaning is read into it.
 */

export interface DiffPiece {
  text: string;
  changed: boolean;
}

/** Which items of `left` and `right` belong to one longest common subsequence. Quadratic: callers bound the sizes. */
export function commonItems<T>(left: readonly T[], right: readonly T[]): { left: boolean[]; right: boolean[] } {
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
  return { left: keptLeft, right: keptRight };
}

/** Consecutive items with the same mark, joined: the pieces give back the text exactly. */
export function joinPieces(items: readonly string[], changed: readonly boolean[]): DiffPiece[] {
  const out: DiffPiece[] = [];
  items.forEach((text, i) => {
    const last = out[out.length - 1];
    if (last && last.changed === changed[i]) last.text += text;
    else out.push({ text, changed: changed[i] });
  });
  return out;
}

const TOKEN = /\s+|\S+/g;
// Word-by-word comparison of the part the two texts do not share at their ends; above this, nothing is marked.
const MAX_CELLS = 250_000;

/**
 * The words in which a replaced clause and its replacement differ, as pieces of each text. Whitespace between two
 * changed words is part of the change. Null when the texts differ in no word, or are too long to compare at a bounded
 * cost: the caller then shows the texts unmarked.
 */
export function wordContrast(original: string, replacement: string): { original: DiffPiece[]; replacement: DiffPiece[] } | null {
  const a = original.match(TOKEN) ?? [];
  const b = replacement.match(TOKEN) ?? [];
  const wordsA = a.filter((t) => /\S/.test(t));
  const wordsB = b.filter((t) => /\S/.test(t));
  let head = 0;
  while (head < wordsA.length && head < wordsB.length && wordsA[head] === wordsB[head]) head++;
  let tail = 0;
  while (tail < wordsA.length - head && tail < wordsB.length - head && wordsA[wordsA.length - 1 - tail] === wordsB[wordsB.length - 1 - tail]) tail++;
  const midA = wordsA.slice(head, wordsA.length - tail);
  const midB = wordsB.slice(head, wordsB.length - tail);
  if (midA.length === 0 && midB.length === 0) return null;
  if (midA.length * midB.length > MAX_CELLS) return null;
  const kept = commonItems(midA, midB);
  const keptA = [...new Array<boolean>(head).fill(true), ...kept.left, ...new Array<boolean>(tail).fill(true)];
  const keptB = [...new Array<boolean>(head).fill(true), ...kept.right, ...new Array<boolean>(tail).fill(true)];
  return { original: piecesOf(a, keptA), replacement: piecesOf(b, keptB) };
}

/** Tokens of one text with each word's mark; a whitespace token is changed when the words on both sides of it are. */
function piecesOf(tokens: readonly string[], keptWords: readonly boolean[]): DiffPiece[] {
  const wordChanged: boolean[] = [];
  let w = 0;
  for (const token of tokens) wordChanged.push(/\S/.test(token) ? !keptWords[w++] : false);
  const changed = tokens.map((token, i) => {
    if (/\S/.test(token)) return wordChanged[i];
    return i > 0 && i < tokens.length - 1 && wordChanged[i - 1] && wordChanged[i + 1];
  });
  return joinPieces(tokens, changed);
}

/**
 * The part of one text a reader needs first: a few words before its first change to a few after its last, with "…"
 * where text is left out. Within `maxChars` of the first change; the rest stays in the full text.
 */
export function aroundChanges(pieces: readonly DiffPiece[], contextWords = 8, maxChars = 360): DiffPiece[] {
  const first = pieces.findIndex((p) => p.changed);
  if (first < 0) return [...pieces];
  let last = pieces.length - 1;
  while (!pieces[last].changed) last--;
  const out: DiffPiece[] = [];
  const before = pieces[first - 1]?.text ?? "";
  const lead = before
    .split(/(?<=\s)/)
    .slice(-contextWords)
    .join("");
  out.push({ text: (lead.length < before.length ? "…" : "") + lead, changed: false });
  out.push(...pieces.slice(first, last + 1));
  const after = pieces[last + 1]?.text ?? "";
  const trail = after
    .split(/(?<=\s)/)
    .slice(0, contextWords)
    .join("");
  out.push({ text: trail + (trail.length < after.length ? "…" : ""), changed: false });
  return clip(
    out.filter((p) => p.text.length > 0),
    maxChars,
  );
}

function clip(pieces: DiffPiece[], maxChars: number): DiffPiece[] {
  const out: DiffPiece[] = [];
  let used = 0;
  for (const piece of pieces) {
    if (used + piece.text.length <= maxChars) {
      out.push(piece);
      used += piece.text.length;
      continue;
    }
    const room = Math.max(0, maxChars - used);
    const cut = piece.text.slice(0, room).replace(/\s+\S*$/, "");
    if (cut) out.push({ text: cut, changed: piece.changed });
    out.push({ text: "…", changed: false });
    break;
  }
  return out;
}
