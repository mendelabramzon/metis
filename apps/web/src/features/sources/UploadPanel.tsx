import { useState } from "react";

import { trackActivation } from "@/analytics/activation";
import { ApiError, uploadFiles } from "@/api/client";
import type { ParseStatus } from "@/api/types";
import { Badge, Button } from "@/components";
import type { BadgeVariant } from "@/components/Badge";
import { useSession } from "@/session/SessionContext";

import { UploadCard } from "./UploadCard";
import styles from "./sources.module.css";

interface UploadItem {
  id: string;
  file: File;
  /** null while in flight. */
  status: ParseStatus | null;
}

/** Map a parse status to a display tone — "parsed + warnings" reads as a warning, not a clean pass. */
function displayState(status: ParseStatus): { label: string; variant: BadgeVariant } {
  if (status.status === "parsed") {
    return (status.warnings?.length ?? 0) > 0
      ? { label: "Parsed with warnings", variant: "warning" }
      : { label: "Parsed", variant: "success" };
  }
  if (status.status === "unsupported") return { label: "Unsupported", variant: "warning" };
  if (status.status === "failed") return { label: "Failed", variant: "danger" };
  return { label: status.status, variant: "neutral" };
}

function parsedMeta(status: ParseStatus): string {
  const bits: string[] = [];
  if (status.claims != null) bits.push(`${status.claims} claim${status.claims === 1 ? "" : "s"}`);
  if (status.page_count != null) bits.push(`${status.page_count}p`);
  if (status.coverage != null) bits.push(`${Math.round(status.coverage * 100)}% coverage`);
  if (status.parse_path) bits.push(status.parse_path);
  return bits.join(" · ");
}

function FileRow({ item, onRetry }: { item: UploadItem; onRetry: () => void }) {
  const { file, status } = item;
  return (
    <div className={styles.fileRow}>
      <div>
        <div className={styles.fileName}>{file.name}</div>
        {status?.status === "parsed" && parsedMeta(status) && (
          <div className={styles.fileMeta}>{parsedMeta(status)}</div>
        )}
        {status && (status.warnings?.length ?? 0) > 0 && (
          <div className={styles.fileWarn}>{status.warnings?.join("; ")}</div>
        )}
        {status?.error && <div className={styles.fileError}>{status.error}</div>}
      </div>
      <span className={styles.fileSpacer} />
      {status === null ? (
        <Badge variant="info" dot>
          Uploading…
        </Badge>
      ) : (
        <>
          <Badge variant={displayState(status).variant} dot>
            {displayState(status).label}
          </Badge>
          {status.status === "failed" && (
            <Button variant="secondary" size="sm" onClick={onRetry}>
              Retry
            </Button>
          )}
        </>
      )}
    </div>
  );
}

/**
 * The upload flow (E2): batch upload to `/workspaces/{ws}/upload` with a per-file parse status and
 * a retry for failures. One bad file surfaces its own status without failing the batch.
 */
export function UploadPanel() {
  const { userBearer, activeWorkspace, activeWorkspaceId, user } = useSession();
  const [items, setItems] = useState<UploadItem[]>([]);

  function patch(id: string, status: ParseStatus | null) {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, status } : it)));
  }

  async function send(toUpload: UploadItem[]) {
    if (!userBearer || !activeWorkspaceId) return;
    try {
      const res = await uploadFiles(
        userBearer,
        activeWorkspaceId,
        toUpload.map((it) => it.file),
      );
      toUpload.forEach((it, i) => patch(it.id, res.files[i] ?? null));
      if (user && res.files.some((f) => f.status === "parsed")) {
        trackActivation(user.id, "connected_source"); // a dense source landed
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Upload failed.";
      toUpload.forEach((it) => patch(it.id, { filename: it.file.name, status: "failed", error: message }));
    }
  }

  function onFiles(files: File[]) {
    const fresh = files.map((file) => ({ id: crypto.randomUUID(), file, status: null }));
    setItems((prev) => [...fresh, ...prev]);
    void send(fresh);
  }

  function retry(item: UploadItem) {
    patch(item.id, null);
    void send([item]);
  }

  if (!activeWorkspace) return null;
  return (
    <>
      <UploadCard workspaceName={activeWorkspace.name} onFiles={onFiles} />
      {items.length > 0 && (
        <div className={styles.uploadResults}>
          {items.map((item) => (
            <FileRow key={item.id} item={item} onRetry={() => retry(item)} />
          ))}
        </div>
      )}
    </>
  );
}
