import { useId, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { ApiError, createOrganization, createUser } from "@/api/client";
import { Button } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./auth.module.css";

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 403) {
      return "That operator token isn’t valid for this deployment.";
    }
    if (err.status === 409) {
      return "An organization or that email already exists — try signing in instead.";
    }
    if (err.status === 0) return err.message;
    return err.message || "Setup failed. Please try again.";
  }
  return "Something went wrong. Please try again.";
}

/**
 * First-admin bootstrap (H1). Claim a fresh deployment with the operator token: name the org (one
 * field), create yourself as the first user, and land in your personal workspace. Team and shared
 * workspaces aren't pushed here — that's offered later, after the first verified answer (H3).
 */
export function BootstrapPage() {
  const { status, signIn } = useSession();
  const opField = useId();
  const orgField = useId();
  const nameField = useId();
  const emailField = useId();
  const [operatorToken, setOperatorToken] = useState("");
  const [orgName, setOrgName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "authenticated") return <Navigate to="/" replace />;

  const ready = operatorToken.trim() && orgName.trim() && name.trim() && email.trim();

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    const op = operatorToken.trim();
    try {
      const org = await createOrganization(op, orgName.trim());
      const user = await createUser(op, {
        organization_id: org.id,
        email: email.trim(),
        display_name: name.trim(),
      });
      // Sign in as the new admin, holding the operator token; the app re-renders into the shell.
      await signIn({ userId: user.id, operatorToken: op });
    } catch (err) {
      setError(friendlyError(err));
      setBusy(false);
    }
  }

  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <div className={styles.brand}>Set up Metis</div>
        <p className={styles.subtitle}>Claim this deployment and create your account.</p>

        <form className={styles.form} onSubmit={(e) => void onSubmit(e)}>
          {error != null && (
            <div className={styles.error} role="alert">
              {error}
            </div>
          )}

          <div className={styles.field}>
            <label className={styles.label} htmlFor={opField}>
              Operator token
            </label>
            <input
              id={opField}
              className={styles.input}
              type="password"
              value={operatorToken}
              onChange={(e) => setOperatorToken(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
            <span className={styles.hint}>From your deployment configuration — proves you own it.</span>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor={orgField}>
              Organization name
            </label>
            <input
              id={orgField}
              className={styles.input}
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="Acme"
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor={nameField}>
              Your name
            </label>
            <input
              id={nameField}
              className={styles.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor={emailField}>
              Your email
            </label>
            <input
              id={emailField}
              className={styles.input}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              placeholder="you@example.com"
            />
          </div>

          <Button type="submit" variant="primary" block disabled={busy || !ready}>
            {busy ? "Setting up…" : "Create my workspace"}
          </Button>
        </form>

        <p className={styles.footnote}>
          Already have an account? <Link to="/">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
