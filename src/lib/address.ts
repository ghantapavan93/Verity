/**
 * What the address carries, read so that nothing in it can throw: a fragment or a parameter is whatever the link that
 * opened the page says, damaged or crafted. decodeURIComponent threw on "%E0%A4%A": in the access gate the invite was
 * already gone from the address and the page said "Opening the workbench" for good, and on /state React unmounted the
 * whole page (stress test, 2026-10-30).
 */

/** The value decoded, or null when it is not a valid escape sequence. */
export function safeDecode(value: string): string | null {
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}
