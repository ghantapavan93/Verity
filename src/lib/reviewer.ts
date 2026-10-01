/**
 * The reviewer's name is a per-browser convenience, typed once; the decision itself is a record on the API.
 * Shared by the Findings table and the evidence drawer so one name serves both.
 */

export const REVIEWER_KEY = "workbench.reviewer";

export function rememberedReviewer(): string {
  try {
    return window.localStorage.getItem(REVIEWER_KEY) ?? "";
  } catch {
    return "";
  }
}

export function rememberReviewer(name: string): void {
  try {
    window.localStorage.setItem(REVIEWER_KEY, name);
  } catch {
    // Storage may be unavailable; the review is still recorded by the API.
  }
}
