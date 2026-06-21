import { useRef, useState } from "react";

import { Button } from "@/components";

import styles from "./sources.module.css";

/**
 * The upload dropzone (E1 presentational shell; E2 wires the POST + per-file parse status). Drag &
 * drop or click to choose files; both paths call `onFiles`. The button is the accessible path.
 */
export function UploadCard({
  workspaceName,
  onFiles,
  disabled = false,
}: {
  workspaceName: string;
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function pick(list: FileList | null) {
    if (!list || list.length === 0) return;
    onFiles(Array.from(list));
  }

  return (
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions -- the button below is the
    // accessible path; drag & drop is a progressive enhancement on this presentational region.
    <div
      className={styles.uploadCard}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (!disabled) pick(e.dataTransfer.files);
      }}
      style={dragOver ? { borderColor: "var(--color-accent)" } : undefined}
    >
      <div className={styles.uploadTitle}>Upload documents to {workspaceName}</div>
      <div className={styles.uploadHint}>
        PDF, DOCX, XLSX, CSV, TXT, MD, HTML, EML · drag &amp; drop or choose files
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        hidden
        onChange={(e) => pick(e.target.files)}
      />
      <Button variant="primary" onClick={() => inputRef.current?.click()} disabled={disabled}>
        Choose files
      </Button>
    </div>
  );
}
