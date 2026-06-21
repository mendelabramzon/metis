import { useEffect, useId, useState } from "react";

import { trackActivation } from "@/analytics/activation";
import { ApiError, createSource, getOAuthAuthorizeUrl, listConnectors } from "@/api/client";
import type { ConnectorView } from "@/api/types";
import { Button } from "@/components";
import type { Sensitivity } from "@/domain/types";
import { SENSITIVITY_ORDER } from "@/domain/types";
import { useSession } from "@/session/SessionContext";

import { TelegramChatPicker } from "./TelegramChatPicker";
import styles from "./sources.module.css";

/**
 * The catalog-driven add-source form (E3). Pick a connector, name it, confirm sensitivity — no
 * connector JSON. OAuth connectors (Drive/Gmail/Calendar) connect via Google consent; connectors
 * that need structured config (Telegram, IMAP, …) are pointed at their own flow rather than a raw
 * JSON field. Credentials are stored server-side and never shown back.
 */
export function AddSourceForm({
  onCreated,
  onChanged,
}: {
  onCreated: () => void;
  onChanged: () => void;
}) {
  const { operatorToken, activeWorkspaceId, user } = useSession();
  const nameField = useId();
  const sensField = useId();
  const [connectors, setConnectors] = useState<ConnectorView[]>([]);
  const [selected, setSelected] = useState<ConnectorView | null>(null);
  const [name, setName] = useState("");
  const [sensitivity, setSensitivity] = useState<Sensitivity>("internal");
  const [busy, setBusy] = useState(false);
  const [oauthMsg, setOauthMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!operatorToken) return;
    const controller = new AbortController();
    void listConnectors(operatorToken, controller.signal)
      .then((list) => !controller.signal.aborted && setConnectors(list))
      .catch(() => undefined);
    return () => controller.abort();
  }, [operatorToken]);

  function select(connector: ConnectorView) {
    setSelected(connector);
    setSensitivity(connector.default_sensitivity);
    setName(`My ${connector.name}`);
    setOauthMsg(null);
    setError(null);
  }

  async function connect() {
    if (!operatorToken || !selected) return;
    setOauthMsg(null);
    try {
      const view = await getOAuthAuthorizeUrl(operatorToken, selected.name);
      window.open(view.authorize_url, "_blank", "noopener,noreferrer");
      setOauthMsg("Consent opened in a new tab. Finish there, then create the source.");
    } catch (err) {
      setOauthMsg(
        err instanceof ApiError ? err.message : "Couldn’t start the connection. Try again.",
      );
    }
  }

  async function create() {
    if (!operatorToken || !selected || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createSource(operatorToken, {
        name: name.trim(),
        connector: selected.name,
        sensitivity,
        config: {},
        ...(activeWorkspaceId ? { workspace_id: activeWorkspaceId } : {}),
      });
      if (user) trackActivation(user.id, "connected_source");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn’t create the source.");
      setBusy(false);
    }
  }

  const isOAuth = selected?.auth_method === "oauth2";
  const needsConfig = (selected?.requires_config ?? false) && !isOAuth;
  const canCreate = selected !== null && name.trim() !== "" && !needsConfig;

  return (
    <div className={styles.form}>
      <div className={styles.field}>
        <span className={styles.label}>Connector</span>
        <div className={styles.connectorGrid}>
          {connectors.map((connector) => (
            <button
              key={connector.name}
              type="button"
              className={
                selected?.name === connector.name
                  ? `${styles.connectorOption} ${styles.connectorOptionOn}`
                  : styles.connectorOption
              }
              onClick={() => select(connector)}
            >
              <span className={styles.connectorName}>{connector.name}</span>
              <span className={styles.connectorAuth}>{connector.auth_method}</span>
            </button>
          ))}
        </div>
      </div>

      {selected?.name === "telegram" ? (
        <TelegramChatPicker
          defaultSensitivity={selected.default_sensitivity}
          onChanged={onChanged}
        />
      ) : selected ? (
        <>
          <div className={styles.field}>
            <label className={styles.label} htmlFor={nameField}>
              Name
            </label>
            <input
              id={nameField}
              className={styles.control}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor={sensField}>
              Sensitivity
            </label>
            <select
              id={sensField}
              className={styles.control}
              value={sensitivity}
              onChange={(e) => setSensitivity(e.target.value as Sensitivity)}
            >
              {SENSITIVITY_ORDER.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </div>

          {isOAuth && (
            <div className={styles.field}>
              <Button variant="secondary" onClick={() => void connect()}>
                Connect {selected.name}
              </Button>
              {oauthMsg && <span className={styles.formNote}>{oauthMsg}</span>}
            </div>
          )}

          {needsConfig && (
            <div className={styles.formNote}>
              The “{selected.name}” connector needs credentials that aren’t set up here yet.
            </div>
          )}

          {error && <div className={styles.formError}>{error}</div>}

          <div className={styles.formActions}>
            <Button variant="primary" onClick={() => void create()} disabled={!canCreate || busy}>
              {busy ? "Creating…" : "Create source"}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
