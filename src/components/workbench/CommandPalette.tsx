"use client";

/**
 * Command palette: one text field, a filtered list, arrow keys, Enter, Escape. Commands are
 * supplied by the workbench so the palette knows nothing about documents or runs.
 */

import { motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./CommandPalette.module.css";

export interface Command {
  id: string;
  label: string;
  hint?: string;
  group: "Ask" | "Guidance" | "Evidence" | "Go to" | "Jump to";
  run: () => void;
}

const EASE = [0.2, 0, 0, 1] as const;

export function CommandPalette({ getCommands, onClose, reduceMotion }: { getCommands: () => Command[]; onClose: () => void; reduceMotion: boolean }) {
  const [commands] = useState(getCommands);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands.slice(0, 40);
    const terms = q.split(/\s+/);
    return commands.filter((c) => terms.every((t) => `${c.group} ${c.label} ${c.hint ?? ""}`.toLowerCase().includes(t))).slice(0, 40);
  }, [commands, query]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const item = listRef.current?.children[index] as HTMLElement | undefined;
    item?.scrollIntoView({ block: "nearest" });
  }, [index]);

  const choose = (command: Command | undefined) => {
    if (!command) return;
    onClose();
    command.run();
  };

  return (
    <div className={styles.scrim} onMouseDown={onClose}>
      <motion.div
        className={styles.palette}
        role="dialog"
        aria-label="Commands"
        onMouseDown={(e) => e.stopPropagation()}
        initial={{ opacity: 0, scale: reduceMotion ? 1 : 0.98, y: reduceMotion ? 0 : -6 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.16, ease: EASE }}
      >
        <input
          ref={inputRef}
          className={styles.input}
          placeholder="Type a command or a clause"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIndex(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setIndex((i) => Math.min(matches.length - 1, i + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setIndex((i) => Math.max(0, i - 1));
            } else if (e.key === "Enter") {
              e.preventDefault();
              choose(matches[index]);
            } else if (e.key === "Escape") {
              e.preventDefault();
              onClose();
            } else if (e.key === "Tab") {
              e.preventDefault(); // a dialog keeps focus: the list is reached through the arrow keys
            }
          }}
          aria-activedescendant={matches[index] ? `cmd-${matches[index].id}` : undefined}
          aria-controls="command-list"
          role="combobox"
          aria-expanded="true"
          aria-autocomplete="list"
        />
        <ul className={styles.list} id="command-list" role="listbox" ref={listRef}>
          {matches.length === 0 && <li className={styles.empty}>Nothing matches</li>}
          {matches.map((command, i) => (
            <li
              key={command.id}
              id={`cmd-${command.id}`}
              role="option"
              aria-selected={i === index}
              className={`${styles.item} ${i === index ? styles.itemActive : ""}`}
              onMouseEnter={() => setIndex(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(command);
              }}
            >
              <span className={styles.group}>{command.group}</span>
              <span className={styles.label}>{command.label}</span>
              {command.hint && <span className={styles.hint}>{command.hint}</span>}
            </li>
          ))}
        </ul>
        <div className={styles.footer}>
          <span>↑↓ move</span>
          <span>↵ run</span>
          <span>esc close</span>
        </div>
      </motion.div>
    </div>
  );
}
