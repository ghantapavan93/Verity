"use client";

import { useState } from "react";
import styles from "../Workbench.module.css";
import { absolute, attachment, errorMessage } from "@/lib/api";

/**
 * The run's evidence pack: what it holds is said beside the link, the wait is shown, and a refusal stays on this page
 * (a plain link replaced the workbench with the API's error). The link keeps its address, so it can still be copied
 * or saved; a click reads the file and saves it under the name the API gave it.
 */
export function PackLink({ runId, className }: { runId: string; className: string }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const path = `/api/runs/${runId}/evidence-pack`;

  const save = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const { blob, name } = await attachment(path, `evidence-${runId}.zip`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setProblem(`The evidence pack could not be made: ${errorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className={styles.packLink}>
      <a
        className={className}
        href={absolute(path)}
        aria-disabled={busy || undefined}
        onClick={(event) => {
          event.preventDefault();
          if (!busy) void save();
        }}
      >
        Download evidence pack
      </a>
      <span className={styles.packNote} role="status">
        {busy ? "Preparing the zip…" : "A zip with the document, every quote and verify.py, which checks them without this service."}
      </span>
      {problem && (
        <span className={styles.packProblem} role="alert">
          {problem}
        </span>
      )}
    </span>
  );
}
