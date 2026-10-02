"use client";

import type { ReactNode } from "react";
import styles from "../Workbench.module.css";
import { IconAssistant, IconDocuments, IconFindings, IconRuns, IconSearch, VerityMark } from "../icons";
import type { View } from "./constants";

export function Rail({
  active,
  hasDocument,
  onNavigate,
  onSearch,
}: {
  active: View;
  hasDocument: boolean;
  onNavigate: (view: View) => void;
  onSearch: () => void;
}) {
  return (
    <nav className={styles.rail} aria-label="Primary">
      <span className={styles.railMark} title="Verity">
        <VerityMark size={20} />
      </span>
      <RailButton label="Search (Ctrl K)" icon={<IconSearch />} onClick={onSearch} />
      <RailButton label="Documents" icon={<IconDocuments />} active={active === "documents"} onClick={() => onNavigate("documents")} />
      <RailButton
        label={hasDocument ? "Review" : "Review · add a contract"}
        icon={<IconAssistant />}
        active={active === "assistant"}
        onClick={() => onNavigate("assistant")}
      />
      <RailButton label="Findings" icon={<IconFindings />} active={active === "findings"} onClick={() => onNavigate("findings")} />
      <RailButton label="Runs" icon={<IconRuns />} active={active === "runs"} onClick={() => onNavigate("runs")} />
      <div className={styles.railSpacer} />
    </nav>
  );
}

function RailButton({ label, icon, active = false, onClick }: { label: string; icon: ReactNode; active?: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      className={`${styles.railButton} ${active ? styles.railActive : ""}`}
      aria-label={label}
      title={label}
      aria-current={active ? "page" : undefined}
      onClick={onClick}
    >
      {icon}
    </button>
  );
}
