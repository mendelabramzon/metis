import { useId, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/client";
import { Button } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./auth.module.css";

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return "We couldn’t verify that. Check your user ID (and operator token, if you set one).";
    }
    if (err.status === 403) return "That operator token doesn’t grant operator access.";
    if (err.status === 0) return err.message;
    return err.message || "Sign-in failed. Please try again.";
  }
  return "Something went wrong. Please try again.";
}

/**
 * Sign-in (B3). The user-id bearer is the primary credential (a dev stand-in until real
 * sessions/SSO land in the backend); an optional operator token additionally holds the operator
 * principal for Operations. Invited members arrive via a redeem link instead.
 */
export function LoginPage() {
  const { signIn } = useSession();
  const userField = useId();
  const opField = useId();
  const [userId, setUserId] = useState("");
  const [operatorToken, setOperatorToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const id = userId.trim();
    if (!id || busy) return;
    setBusy(true);
    setError(null);
    try {
      const op = operatorToken.trim();
      await signIn({ userId: id, ...(op ? { operatorToken: op } : {}) });
      // On success the app re-renders into the shell; this component unmounts.
    } catch (err) {
      setError(friendlyError(err));
      setBusy(false);
    }
  }

  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <div className={styles.brand}>Metis</div>
        <p className={styles.subtitle}>Sign in to your workspaces.</p>

        <form className={styles.form} onSubmit={(e) => void onSubmit(e)}>
          {error != null && (
            <div className={styles.error} role="alert">
              {error}
            </div>
          )}

          <div className={styles.field}>
            <label className={styles.label} htmlFor={userField}>
              User ID
            </label>
            <input
              id={userField}
              className={styles.input}
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              autoComplete="username"
              spellCheck={false}
              placeholder="usr_…"
            />
            <span className={styles.hint}>
              Your user ID is your bearer for now — real sessions and SSO come later.
            </span>
          </div>

          <details className={styles.disclosure}>
            <summary>Operator access (optional)</summary>
            <div className={styles.disclosureBody}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor={opField}>
                  Operator token
                </label>
                <input
                  id={opField}
                  className={styles.input}
                  value={operatorToken}
                  onChange={(e) => setOperatorToken(e.target.value)}
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                />
                <span className={styles.hint}>
                  Adds the operator principal for Operations (provider config, jobs, audit).
                </span>
              </div>
            </div>
          </details>

          <Button type="submit" variant="primary" block disabled={busy || !userId.trim()}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className={styles.footnote}>
          Have an invite link? Open it to join your team. Or{" "}
          <Link to="/setup">set up a new deployment</Link>.
        </p>
      </div>
    </div>
  );
}
