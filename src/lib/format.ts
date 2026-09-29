/** Deterministic formatting for dates, durations and hashes. No locale lookups, so server and client agree. */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function pad(value: number, width = 2): string {
  return String(value).padStart(width, "0");
}

/** "27 Sep 2026, 21:43" in the viewer's local time. */
export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}, ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** "21:43:19.683" for stage timelines. */
export function formatClock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(), 3)}`;
}

/** Milliseconds between two ISO timestamps, as "+1.2 s" or "+340 ms". */
export function formatDelta(fromIso: string, toIso: string): string {
  const ms = new Date(toIso).getTime() - new Date(fromIso).getTime();
  if (!Number.isFinite(ms)) return "";
  return ms >= 1000 ? `+${(ms / 1000).toFixed(1)} s` : `+${Math.round(ms)} ms`;
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "";
  return ms >= 10_000 ? `${Math.round(ms / 1000)} s` : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

export function shortHash(digest: string | null | undefined, length = 12): string {
  return digest ? digest.slice(0, length) : "";
}

export function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}
