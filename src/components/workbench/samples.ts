/**
 * The agreements bundled for "try the sample". The standard one is real and unmodified: Common Paper's Cloud Service
 * Agreement, CC BY 4.0, attributed under the document when it is loaded. The amended one is synthetic, written for
 * Verity's first-visitor tests with fictional parties: an amendment replaces one of its clauses, so a reader can ask the
 * same point three ways and see what code says each time (owner's request, 2026-10-15: easy for a reviewer to challenge).
 */
export type SampleKind = "standard" | "amended";

export interface Sample {
  path: string;
  name: string;
  /** Shown under the document while the sample is open. */
  note: string;
  /** Offered first in the question panel and the command palette, in place of the general suggestions. */
  questions?: readonly string[];
}

export const SAMPLES: Record<SampleKind, Sample> = {
  standard: {
    path: "/samples/cloud-service-agreement.docx",
    name: "Cloud Service Agreement (Common Paper).docx",
    note: "Sample · Common Paper Cloud Service Agreement · CC BY 4.0 · a real standard agreement, unmodified",
  },
  amended: {
    path: "/samples/linen-services-agreement-amended.pdf",
    name: "Linen and Laundry Services Agreement with Amendment No 1 (synthetic).pdf",
    note: "Sample · a synthetic agreement with an amendment, written for Verity's tests · fictional parties",
    // The same point as it stands, as first signed, and at a time before the amendment took effect.
    questions: [
      "What is the deadline now for giving notice that we do not want the agreement to renew?",
      "What did the agreement originally require for a notice of non-renewal, before it was amended?",
      "What was the deadline for giving a notice of non-renewal in June 2026?",
    ],
  },
};

/** The questions to offer first: the open sample's own, or the general ones. */
export function suggestionsFor(sample: SampleKind | null, general: readonly string[]): readonly string[] {
  return (sample && SAMPLES[sample].questions) || general;
}
