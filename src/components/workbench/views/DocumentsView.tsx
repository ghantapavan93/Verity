"use client";

import { useEffect, useState } from "react";
import wb from "../Workbench.module.css";
import styles from "./Views.module.css";
import { listDocuments } from "@/lib/api";
import { formatWhen, plural } from "@/lib/format";
import type { DocumentSummary } from "@/lib/types";

export function DocumentsView({
  currentId,
  notice,
  onOpen,
  onAdd,
}: {
  currentId: string | null;
  notice: string | null;
  onOpen: (id: string) => void;
  onAdd: () => void;
}) {
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listDocuments()
      .then((rows) => !cancelled && setDocuments(rows))
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className={styles.pane}>
      <div className={styles.inner}>
        <div className={styles.kicker}>Documents</div>
        <h1 className={styles.title}>
          Contracts in this workbench
          {documents && <span className={styles.count}>{documents.length}</span>}
        </h1>
        <p className={styles.lede}>Each upload is parsed into numbered sections and stored with its SHA-256. Open one to review it in the workspace.</p>
        {(notice || error) && <p className={styles.notice}>{notice ?? error}</p>}

        {documents && documents.length === 0 && (
          <div className={styles.empty}>
            <p>No documents yet.</p>
            <button type="button" className={wb.ghostButton} onClick={onAdd}>
              Add a contract
            </button>
          </div>
        )}

        {documents && documents.length > 0 && (
          <ul className={styles.list}>
            {documents.map((d) => (
              <li key={d.id}>
                <button type="button" className={styles.row} onClick={() => onOpen(d.id)}>
                  <div className={styles.rowMain}>
                    <div className={styles.rowTitle}>{d.name}</div>
                    <div className={styles.rowMeta}>
                      {d.pages !== null && <span>{plural(d.pages, "page")}</span>}
                      <span>{plural(d.sections, "section")}</span>
                      <span>Uploaded {formatWhen(d.createdAt)}</span>
                      {d.findings > 0 ? (
                        <span>
                          {plural(d.findings, "finding")}
                          {d.reviewedFindings > 0 ? ` · ${d.reviewedFindings} reviewed by a person` : " · awaiting review"}
                          {d.lastRunAt ? ` · analysed ${formatWhen(d.lastRunAt)}` : ""}
                        </span>
                      ) : (
                        <span>Not analysed</span>
                      )}
                    </div>
                  </div>
                  <div className={styles.rowSide}>{d.id === currentId ? "Open now" : "Open"}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
