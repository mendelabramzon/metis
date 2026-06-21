import { useCallback, useEffect, useState } from "react";

import { createWorkspaceInvite, listMembers } from "@/api/client";
import type { MembershipRole, MembershipView } from "@/api/types";
import { MEMBERSHIP_ROLES } from "@/api/types";
import { Badge, Button, ErrorState } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "../settings.module.css";
import { SectionHeader } from "./SectionHeader";

/** Members (G2): list members, mint an invite link, assign the invited role. */
export function MembersSection() {
  const { userBearer, activeWorkspaceId, user } = useSession();
  const [members, setMembers] = useState<MembershipView[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [inviteRole, setInviteRole] = useState<MembershipRole>("member");
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!userBearer || !activeWorkspaceId) {
      setStatus("ready");
      return;
    }
    setStatus("loading");
    try {
      setMembers(await listMembers(userBearer, activeWorkspaceId));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t load members.");
      setStatus("error");
    }
  }, [userBearer, activeWorkspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function mint() {
    if (!userBearer || !activeWorkspaceId) return;
    setBusy(true);
    setError("");
    setCopied(false);
    try {
      const invite = await createWorkspaceInvite(userBearer, activeWorkspaceId, inviteRole);
      setInviteLink(`${window.location.origin}/redeem/${invite.token}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t mint an invite.");
    } finally {
      setBusy(false);
    }
  }

  function copy() {
    if (!inviteLink) return;
    void navigator.clipboard?.writeText(inviteLink).then(() => setCopied(true));
  }

  if (status === "error") {
    return (
      <>
        <SectionHeader title="Members" />
        <ErrorState
          title="Couldn’t load members"
          description={error}
          actions={
            <Button variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      </>
    );
  }

  return (
    <>
      <SectionHeader title="Members" lede="Invite people, set the role they join with, and see who’s in." />

      <div className={styles.field}>
        <span className={styles.label}>Invite a new member</span>
        <div className={styles.actions}>
          <select
            className={styles.control}
            aria-label="Invited role"
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value as MembershipRole)}
          >
            {MEMBERSHIP_ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
          <Button variant="primary" onClick={() => void mint()} disabled={busy}>
            {busy ? "Creating…" : "Create invite link"}
          </Button>
        </div>
      </div>

      {inviteLink && (
        <div className={styles.field}>
          <span className={styles.label}>Single-use invite link</span>
          <div className={styles.actions}>
            <input className={styles.control} readOnly value={inviteLink} style={{ flex: 1 }} />
            <Button variant="secondary" onClick={copy}>
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </div>
      )}

      {error && <div className={styles.error}>{error}</div>}

      <h3 className={styles.label} style={{ marginTop: "var(--space-5)" }}>
        {members.length} member{members.length === 1 ? "" : "s"}
      </h3>
      {members.map((member) => (
        <div key={member.id} className={styles.row}>
          <div className={styles.rowMain}>
            <div className={styles.rowTitle}>
              {member.user_id === user?.id ? "You" : member.user_id}
            </div>
            <div className={styles.rowMeta}>{member.user_id}</div>
          </div>
          <span className={styles.rowSpacer} />
          <Badge variant="neutral">{member.role}</Badge>
        </div>
      ))}

      <div className={styles.note}>
        Removing a member and changing an existing member’s role aren’t available yet — the gateway
        has no member-remove or role-update endpoint (a backend follow-up). Roles are set when a
        person is invited.
      </div>
    </>
  );
}
