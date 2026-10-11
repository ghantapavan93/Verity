import styles from "./Landing.module.css";

export const SOURCE = "https://github.com/ghantapavan93/Verity";

/** The ways out of the workbench's first screens, open to everyone: a recorded failure, the recorded research, the source. */
export function TopLinks() {
  return (
    <nav aria-label="Elsewhere" className={styles.topLinks}>
      <a className={styles.topLink} href="/break">
        Break it
      </a>
      <a className={styles.topLink} href="/state">
        Research
      </a>
      <a className={styles.topLink} href={SOURCE}>
        Source
      </a>
    </nav>
  );
}
