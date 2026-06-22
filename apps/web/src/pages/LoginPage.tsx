import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, listAccounts } from "@/api/client";
import type { AccountView } from "@/api/types";
import { useSession } from "@/session/SessionContext";

import styles from "./auth.module.css";

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return "We couldn’t verify that account. Try again, or check your operator token.";
    }
    if (err.status === 403) return "That operator token doesn’t grant operator access.";
    if (err.status === 0) return err.message;
    return err.message || "Sign-in failed. Please try again.";
  }
  return "Something went wrong. Please try again.";
}

/**
 * Sign-in (B3, C2). A picker over the deployment's accounts — no raw user-id typing. Picking an
 * account signs in with its id as the bearer (a dev stand-in until real sessions/SSO land); an
 * optional operator token, behind a disclosure, additionally holds the operator principal for
 * Operations. Invited members arrive via a redeem link; a fresh deployment routes to setup.
 */
export function LoginPage() {
  const { signIn } = useSession();
  const opField = useId();
  const [accounts, setAccounts] = useState<AccountView[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [operatorToken, setOperatorToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void listAccounts(controller.signal)
      .then((rows) => setAccounts(rows))
      .catch(() => {
        if (!controller.signal.aborted) setLoadFailed(true);
      });
    return () => controller.abort();
  }, []);

  async function onPick(account: AccountView) {
    if (pending) return;
    setPending(account.id);
    setError(null);
    try {
      const op = operatorToken.trim();
      await signIn({ userId: account.id, ...(op ? { operatorToken: op } : {}) });
      // On success the app re-renders into the shell; this component unmounts.
    } catch (err) {
      setError(friendlyError(err));
      setPending(null);
    }
  }

  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <div className={styles.brand}>Metis</div>
        <p className={styles.subtitle}>Choose your account to sign in.</p>

        {error != null && (
          <div className={styles.error} role="alert">
            {error}
          </div>
        )}

        {accounts === null && !loadFailed && <p className={styles.muted}>Loading accounts…</p>}

        {loadFailed && (
          <p className={styles.muted}>
            Couldn’t load accounts. <Link to="/setup">Set up a new deployment</Link>.
          </p>
        )}

        {accounts !== null && accounts.length === 0 && (
          <p className={styles.muted}>
            No accounts yet. <Link to="/setup">Set up a new deployment</Link>.
          </p>
        )}

        {accounts !== null && accounts.length > 0 && (
          <div className={styles.accounts}>
            {accounts.map((account) => (
              <button
                key={account.id}
                type="button"
                className={styles.account}
                onClick={() => void onPick(account)}
                disabled={pending !== null}
              >
                <span className={styles.accountName}>
                  {pending === account.id ? "Signing in…" : account.display_name}
                </span>
                <span className={styles.accountEmail}>{account.email}</span>
              </button>
            ))}
          </div>
        )}

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
                Held with the account you pick — adds the operator principal for Operations (provider
                config, jobs, audit).
              </span>
            </div>
          </div>
        </details>

        <p className={styles.footnote}>
          Have an invite link? Open it to join your team. Or{" "}
          <Link to="/setup">set up a new deployment</Link>.
        </p>
      </div>
    </div>
  );
}
