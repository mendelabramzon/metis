import { useEffect, useState } from "react";

import { getArtifactEvidence, getClaimEvidence } from "@/api/client";
import type { ArtifactEvidenceView, Citation, ClaimEvidenceView } from "@/api/types";
import { ScopeBadge, SensitivityBadge } from "@/components";
import { useSession } from "@/session/SessionContext";

import { scopeForCitation } from "./citationScope";
import styles from "./ask.module.css";

type Status = "loading" | "ready" | "error";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/**
 * The citation drawer body (D2): expands a citation back through the truth hierarchy — the quoted
 * source span(s) with page/char, the claim, and the source document + ingest date. Raw ids live
 * under a Developer-details disclosure, not the default view.
 */
export function CitationDrawerBody({ citation, index }: { citation: Citation; index: number }) {
  const { userBearer, activeWorkspaceId } = useSession();
  const [claim, setClaim] = useState<ClaimEvidenceView | null>(null);
  const [artifact, setArtifact] = useState<ArtifactEvidenceView | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    if (!userBearer || !activeWorkspaceId) {
      setStatus("error");
      return;
    }
    const controller = new AbortController();
    setStatus("loading");
    setClaim(null);
    setArtifact(null);
    void (async () => {
      try {
        const c = await getClaimEvidence(
          userBearer,
          activeWorkspaceId,
          citation.claim_id,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setClaim(c);
        const artifactId = citation.artifact_id ?? c.spans[0]?.artifact_id ?? null;
        if (artifactId) {
          try {
            const a = await getArtifactEvidence(
              userBearer,
              activeWorkspaceId,
              artifactId,
              controller.signal,
            );
            if (!controller.signal.aborted) setArtifact(a);
          } catch {
            /* the artifact lookup is optional — the quote + claim still render */
          }
        }
        if (!controller.signal.aborted) setStatus("ready");
      } catch {
        if (!controller.signal.aborted) setStatus("error");
      }
    })();
    return () => controller.abort();
  }, [citation, userBearer, activeWorkspaceId]);

  const scope = scopeForCitation(citation.scope);
  const artifactId = citation.artifact_id ?? artifact?.artifact_id;

  return (
    <div>
      <div className={styles.drawerBadges}>
        <strong>Source {index + 1}</strong>
        {scope && <ScopeBadge scope={scope} />}
        {citation.sensitivity && <SensitivityBadge level={citation.sensitivity} />}
      </div>

      {status === "loading" && (
        <p style={{ color: "var(--color-text-muted)" }} role="status">
          Loading source…
        </p>
      )}
      {status === "error" && (
        <p style={{ color: "var(--status-danger-fg)" }}>Couldn’t load this source.</p>
      )}

      {status === "ready" && claim && (
        <>
          {claim.spans.length > 0 ? (
            claim.spans.map((span) => (
              <div key={span.source_span_id}>
                {span.quote ? (
                  <blockquote className={styles.quote}>{span.quote}</blockquote>
                ) : (
                  <p style={{ color: "var(--color-text-muted)" }}>No quote resolved for this span.</p>
                )}
                <div className={styles.quoteMeta}>
                  {span.page != null ? `Page ${span.page} · ` : ""}characters {span.char_start}–
                  {span.char_end}
                </div>
              </div>
            ))
          ) : (
            <p style={{ color: "var(--color-text-muted)" }}>No source spans on this claim.</p>
          )}

          <div className={styles.drawerLabel}>Claim</div>
          <div className={styles.sourceLine}>
            {claim.negated ? "Not: " : ""}
            {claim.text}
          </div>

          <div className={styles.drawerLabel}>Source</div>
          <div className={styles.sourceLine}>
            {artifact ? (artifact.filename ?? "(untitled document)") : "—"}
            {artifact && ` · ${formatDate(artifact.created_at)}`}
          </div>

          <details className={styles.devDetails}>
            <summary>Developer details</summary>
            <div className={styles.devRow}>
              <span>claim</span>
              <code>{citation.claim_id}</code>
            </div>
            {citation.source_span_id && (
              <div className={styles.devRow}>
                <span>span</span>
                <code>{citation.source_span_id}</code>
              </div>
            )}
            {artifactId && (
              <div className={styles.devRow}>
                <span>artifact</span>
                <code>{artifactId}</code>
              </div>
            )}
          </details>
        </>
      )}
    </div>
  );
}
