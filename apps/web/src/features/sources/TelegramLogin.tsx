import { useEffect, useState } from "react";

import {
  ApiError,
  getTdlibStatus,
  startTdlibConnect,
  submitTdlibCode,
  submitTdlibPassword,
} from "@/api/client";
import type { TelegramConnectView } from "@/api/types";
import { Badge, Button } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "./sources.module.css";

const POLL_MS = 2500;
// Backend states where we wait on an out-of-band action (the QR scan) and poll for the transition.
const POLL_STATES = new Set(["wait_qr", "wait_parameters"]);

/**
 * The TDLib personal-account login sub-flow (E5). Guided states — connect → scan a QR (or enter a
 * phone) → login code → 2FA password → ready / failed — over `POST`/`GET /telegram/tdlib/connect`
 * with the user bearer (it's the user's own account). Stays inline in Sources and never blocks the
 * rest of the screen; the code and 2FA password are cleared on submit and never shown again.
 */
export function TelegramLogin() {
  const { userBearer } = useSession();
  const [view, setView] = useState<TelegramConnectView | null>(null); // null = not started
  const [usePhone, setUsePhone] = useState(false);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const state = view?.state ?? "idle";

  // While waiting for the user to approve on their phone, poll for the next step (code / 2FA / ready).
  useEffect(() => {
    if (!userBearer || !POLL_STATES.has(state)) return;
    const controller = new AbortController();
    const id = window.setInterval(() => {
      void getTdlibStatus(userBearer, controller.signal)
        .then((next) => !controller.signal.aborted && setView(next))
        .catch(() => undefined);
    }, POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(id);
    };
  }, [userBearer, state]);

  async function start(useQr: boolean) {
    if (!userBearer || (!useQr && phone.trim() === "")) return;
    setBusy(true);
    setError(null);
    try {
      setView(
        await startTdlibConnect(userBearer, { use_qr: useQr, phone: useQr ? null : phone.trim() }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn’t start the Telegram login.");
    } finally {
      setBusy(false);
    }
  }

  async function sendCode() {
    if (!userBearer || !code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const next = await submitTdlibCode(userBearer, code.trim());
      setCode(""); // never shown after entry
      setView(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That code didn’t work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function sendPassword() {
    if (!userBearer || !password) return;
    setBusy(true);
    setError(null);
    try {
      const next = await submitTdlibPassword(userBearer, password);
      setPassword(""); // never shown after entry
      setView(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That password didn’t work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setView(null);
    setError(null);
    setCode("");
    setPassword("");
  }

  return (
    <div className={styles.loginGroup}>
      {state === "idle" && (
        <>
          <p className={styles.formNote}>
            Connect your Telegram account to back-fill history and followed channels. Only the session
            key is stored — never your password.
          </p>
          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={usePhone}
              onChange={(e) => setUsePhone(e.target.checked)}
            />
            Use my phone number instead of a QR code
          </label>
          {usePhone && (
            <div className={styles.field}>
              <label className={styles.label} htmlFor="tg-phone">
                Phone number
              </label>
              <input
                id="tg-phone"
                className={styles.control}
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 555 000 1234"
                inputMode="tel"
                autoComplete="tel"
              />
            </div>
          )}
          <div className={styles.formActions}>
            <Button
              variant="primary"
              onClick={() => void start(!usePhone)}
              disabled={busy || (usePhone && phone.trim() === "")}
            >
              {busy ? "Connecting…" : "Connect Telegram"}
            </Button>
          </div>
        </>
      )}

      {state === "wait_parameters" && (
        <p className={styles.loginStatus} role="status">
          Connecting…
        </p>
      )}

      {state === "wait_qr" && (
        <div className={styles.qrBox}>
          <p className={styles.formNote}>
            On your phone, open Telegram →{" "}
            <strong>Settings → Devices → Link Desktop Device</strong> and scan, or open this link on a
            device where you’re already signed in:
          </p>
          {view?.qr_link && (
            <a
              className={styles.qrToken}
              href={view.qr_link}
              target="_blank"
              rel="noopener noreferrer"
            >
              {view.qr_link}
            </a>
          )}
          <p className={styles.loginStatus} role="status">
            Waiting for you to approve the login…
          </p>
        </div>
      )}

      {state === "wait_phone" && (
        <>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="tg-phone-2">
              Phone number
            </label>
            <input
              id="tg-phone-2"
              className={styles.control}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              inputMode="tel"
              autoComplete="tel"
            />
          </div>
          <div className={styles.formActions}>
            <Button
              variant="primary"
              onClick={() => void start(false)}
              disabled={busy || phone.trim() === ""}
            >
              {busy ? "Sending…" : "Continue"}
            </Button>
          </div>
        </>
      )}

      {state === "wait_code" && (
        <>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="tg-code">
              Login code
            </label>
            <input
              id="tg-code"
              className={styles.control}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
            />
          </div>
          <div className={styles.formActions}>
            <Button variant="primary" onClick={() => void sendCode()} disabled={busy || !code.trim()}>
              {busy ? "Checking…" : "Submit code"}
            </Button>
          </div>
        </>
      )}

      {state === "wait_password" && (
        <>
          <p className={styles.formNote}>
            This account has two-step verification. Enter your cloud password.
          </p>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="tg-pw">
              2FA password
            </label>
            <input
              id="tg-pw"
              className={styles.control}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div className={styles.formActions}>
            <Button
              variant="primary"
              onClick={() => void sendPassword()}
              disabled={busy || !password}
            >
              {busy ? "Checking…" : "Submit password"}
            </Button>
          </div>
        </>
      )}

      {state === "ready" && (
        <p className={styles.loginStatus}>
          <Badge variant="success" dot>
            Connected
          </Badge>{" "}
          Your Telegram account is linked — history and followed channels will sync.
        </p>
      )}

      {state === "closed" && (
        <>
          <p className={styles.formError}>The Telegram login didn’t complete.</p>
          <div className={styles.formActions}>
            <Button variant="secondary" onClick={reset}>
              Try again
            </Button>
          </div>
        </>
      )}

      {error && <div className={styles.formError}>{error}</div>}
    </div>
  );
}
