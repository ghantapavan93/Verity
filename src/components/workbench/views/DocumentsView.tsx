"use client";

import { useEffect, useState } from "react";
import wb from "../Workbench.module.css";
import styles from "./Views.module.css";
import { Figures } from "./Figures";
import { IconArrowRight } from "../icons";
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
        <p className={styles.lede}>Each upload is read into numbered sections and stored with its SHA-256. Open one to ask about it.</p>
        {documents && documents.length > 0 && (
          <Figures
            label="The contracts in this workbench"
            items={[
              { label: "Contracts", value: documents.length },
              { label: "Sections read", value: documents.reduce((n, d) => n + d.sections, 0) },
              { label: "Findings", value: documents.reduce((n, d) => n + d.findings, 0) },
              {
                label: "Reviewed by a person",
                value: documents.reduce((n, d) => n + d.reviewedFindings, 0),
                note: "confirmed or dismissed, under a name",
              },
            ]}
          />
        )}
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
            {documents.map((d, i) => (
              <li key={d.id}>
                <button type="button" className={`${styles.row} ${styles.indexed}`} onClick={() => onOpen(d.id)}>
                  <span className={styles.rowIndex} aria-hidden="true">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className={styles.rowMain}>
                    <div className={styles.rowTitle}>
                      <span className={styles.rowTitleText}>{d.name.replace(/\.[^.]+$/, "")}</span>
                      <span className={styles.fileType}>{d.name.split(".").pop()}</span>
                    </div>
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
                  <div className={styles.rowSide}>
                    <span className={`${styles.openHint} ${d.id === currentId ? styles.openNow : ""}`}>
                      {d.id === currentId ? "Open now" : "Open"} <IconArrowRight />
                    </span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
