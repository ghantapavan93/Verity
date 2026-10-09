import styles from "./Landing.module.css";

export const SOURCE = "https://github.com/ghantapavan93/Verity";

/** The two ways out of the workbench's first screens: the recorded research, open to everyone, and the source. */
export function TopLinks() {
  return (
    <nav aria-label="Elsewhere" className={styles.topLinks}>
      <a className={styles.topLink} href="/state">
        Research
      </a>
      <a className={styles.topLink} href={SOURCE}>
        Source
      </a>
    </nav>
  );
}
