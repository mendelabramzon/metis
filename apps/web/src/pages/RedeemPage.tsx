import { useId, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { ApiError, redeemInvite } from "@/api/client";
import { Button } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./auth.module.css";

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return "This invite link is invalid or has expired.";
    if (err.status === 409) {
      return "This invite was already used, or an account already exists for that email.";
    }
    if (err.status === 0) return err.message;
    return err.message || "Couldn’t redeem this invite. Please try again.";
  }
  return "Something went wrong. Please try again.";
}

/**
 * Invited-member path (H2, consumes A6). Redeem → provision the user + personal workspace → join
 * the invited shared workspace → sign straight in, with no org/setup steps. On success the active
 * workspace switches to the one they joined (it has the team's content) and a one-line note confirms
 * which workspace before they start asking.
 */
export function RedeemPage() {
  const { token } = useParams<{ token: string }>();
  const { status, signIn, setActiveWorkspace, workspaces } = useSession();
  const navigate = useNavigate();
  const emailField = useId();
  const nameField = useId();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [joinedWorkspaceId, setJoinedWorkspaceId] = useState<string | null>(null);

  // Just joined — confirm which workspace, then send them in to ask.
  if (joinedWorkspaceId !== null) {
    const name = workspaces.find((w) => w.id === joinedWorkspaceId)?.name ?? "your team’s workspace";
    return (
      <div className={styles.screen}>
        <div className={styles.card}>
          <div className={styles.brand}>You’re in</div>
          <p className={styles.subtitle}>
            You’ve joined <strong>{name}</strong>. Ask it anything — answers cite the team’s sources.
          </p>
          <Button variant="primary" block onClick={() => navigate("/ask")}>
            Start asking
          </Button>
        </div>
      </div>
    );
  }

  if (status === "authenticated") return <Navigate to="/" replace />;
  if (!token) return <Navigate to="/" replace />;

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!email.trim() || !displayName.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await redeemInvite(token as string, {
        email: email.trim(),
        display_name: displayName.trim(),
      });
      await signIn({ userId: res.user_id });
      setActiveWorkspace(res.workspace_id); // land where the team's content is
      setJoinedWorkspaceId(res.workspace_id);
    } catch (err) {
      setError(friendlyError(err));
      setBusy(false);
    }
  }

  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <div className={styles.brand}>Join on Metis</div>
        <p className={styles.subtitle}>
          You’ve been invited to a shared workspace. Tell us who you are to get started — no setup
          steps.
        </p>

        <form className={styles.form} onSubmit={(e) => void onSubmit(e)}>
          {error != null && (
            <div className={styles.error} role="alert">
              {error}
            </div>
          )}

          <div className={styles.field}>
            <label className={styles.label} htmlFor={nameField}>
              Your name
            </label>
            <input
              id={nameField}
              className={styles.input}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="name"
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor={emailField}>
              Email
            </label>
            <input
              id={emailField}
              className={styles.input}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
            />
          </div>

          <Button
            type="submit"
            variant="primary"
            block
            disabled={busy || !email.trim() || !displayName.trim()}
          >
            {busy ? "Joining…" : "Join workspace"}
          </Button>
        </form>
      </div>
    </div>
  );
}
