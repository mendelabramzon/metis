import styles from "../settings.module.css";

export function SectionHeader({ title, lede }: { title: string; lede?: string }) {
  return (
    <header>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {lede != null && <p className={styles.sectionLede}>{lede}</p>}
    </header>
  );
}
