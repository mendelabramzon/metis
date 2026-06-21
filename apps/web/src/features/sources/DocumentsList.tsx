import { useCallback, useEffect, useState } from "react";

import { ApiError, deleteDocument, listDocuments } from "@/api/client";
import type { ArtifactEvidenceView } from "@/api/types";
import { Button, Card } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./sources.module.css";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function DocumentRow({
  doc,
  onDelete,
}: {
  doc: ArtifactEvidenceView;
  onDelete: () => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function remove() {
    setDeleting(true);
    try {
      await onDelete(); // the row unmounts when the list reloads
    } catch {
      setDeleting(false);
    }
  }

  return (
    <div className={styles.fileRow}>
      <div>
        <div className={styles.fileName}>{doc.filename ?? "Untitled document"}</div>
        <div className={styles.fileMeta}>
          {doc.media_type} · {formatBytes(doc.byte_size)}
        </div>
      </div>
      <span className={styles.fileSpacer} />
      {confirming ? (
        <div className={styles.confirmActions}>
          <Button variant="danger" size="sm" onClick={() => void remove()} disabled={deleting}>
            {deleting ? "Deleting…" : "Delete everywhere"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirming(false)}
            disabled={deleting}
          >
            Cancel
          </Button>
        </div>
      ) : (
        <Button variant="secondary" size="sm" onClick={() => setConfirming(true)}>
          Delete
        </Button>
      )}
    </div>
  );
}

/**
 * The uploaded-documents list (I1): the files this member uploaded into the active workspace, each
 * removable. Uploads register no source, so they never show under Sources — this is where you see
 * and erase them. Reloads on `refreshKey` (bumped after a successful upload) and after each delete.
 */
export function DocumentsList({ refreshKey }: { refreshKey: number }) {
  const { userBearer, activeWorkspaceId } = useSession();
  const [docs, setDocs] = useState<ArtifactEvidenceView[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!userBearer || !activeWorkspaceId) return;
    try {
      setDocs(await listDocuments(userBearer, activeWorkspaceId));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn’t load documents.");
    }
  }, [userBearer, activeWorkspaceId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  async function remove(artifactId: string) {
    if (!userBearer || !activeWorkspaceId) return;
    await deleteDocument(userBearer, activeWorkspaceId, artifactId);
    await load();
  }

  if (error) return <div className={styles.fileError}>{error}</div>;
  if (docs.length === 0) return null; // nothing uploaded yet — keep the screen calm

  return (
    <Card compact>
      <div className={styles.subhead}>Documents in this workspace</div>
      <div className={styles.uploadResults}>
        {docs.map((doc) => (
          <DocumentRow
            key={doc.artifact_id}
            doc={doc}
            onDelete={() => remove(doc.artifact_id)}
          />
        ))}
      </div>
    </Card>
  );
}
