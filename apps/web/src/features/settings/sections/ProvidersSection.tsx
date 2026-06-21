import { useCallback, useEffect, useState } from "react";

import { getDeploymentConfig, updateDeploymentConfig } from "@/api/client";
import type { ConfigFieldView, DeploymentConfigView } from "@/api/types";
import { Badge, Button, ErrorState } from "@/components";
import { useSession } from "@/session/SessionContext";

import styles from "../settings.module.css";
import { SectionHeader } from "./SectionHeader";

interface FieldMeta {
  key: string;
  label: string;
  placeholder?: string;
}

interface Group {
  title: string;
  lede: string;
  keys: FieldMeta[];
}

// The runtime-configurable fields, grouped for the operator. Mirrors the gateway's CONFIG_KEYS.
const GROUPS: Group[] = [
  {
    title: "Chat model provider",
    lede: "Set one to answer with a model. With none set, answers are extractive — pulled straight from your sources, no synthesis.",
    keys: [
      { key: "anthropic_api_key", label: "Anthropic API key", placeholder: "sk-ant-…" },
      { key: "openai_api_key", label: "OpenAI API key", placeholder: "sk-…" },
      {
        key: "openai_base_url",
        label: "OpenAI-compatible base URL",
        placeholder: "https://api.openai.com/v1",
      },
      { key: "openai_chat_model", label: "OpenAI chat model", placeholder: "gpt-4o-mini" },
      {
        key: "model_endpoint",
        label: "Local model endpoint (Ollama)",
        placeholder: "http://localhost:11434",
      },
      { key: "chat_model", label: "Local chat model", placeholder: "gemma4:e4b" },
    ],
  },
  {
    title: "Google OAuth — Drive, Gmail, Calendar",
    lede: "From a Google Cloud OAuth client. Enables the OAuth connectors; the redirect URI must match this deployment.",
    keys: [
      { key: "google_client_id", label: "Client ID" },
      { key: "google_client_secret", label: "Client secret" },
      {
        key: "google_redirect_uri",
        label: "Redirect URI",
        placeholder: "https://your-host/oauth/callback",
      },
      { key: "google_scopes", label: "Scopes" },
    ],
  },
  {
    title: "Telegram — personal-account TDLib login",
    lede: "An app api_id/api_hash from my.telegram.org. Enables the Telegram history-backfill login.",
    keys: [
      { key: "telegram_api_id", label: "API ID" },
      { key: "telegram_api_hash", label: "API hash" },
    ],
  },
];

const SECRET_KEYS = new Set(["anthropic_api_key", "openai_api_key", "google_client_secret", "telegram_api_hash"]);

function StatusRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.row}>
      <div className={styles.rowMain}>
        <div className={styles.rowTitle}>{label}</div>
      </div>
      <span className={styles.rowSpacer} />
      {children}
    </div>
  );
}

function FieldRow({
  meta,
  field,
  value,
  disabled,
  onChange,
  onClear,
}: {
  meta: FieldMeta;
  field: ConfigFieldView | undefined;
  value: string;
  disabled: boolean;
  onChange: (v: string) => void;
  onClear: () => void;
}) {
  const isSet = field?.set ?? false;
  const secret = field?.secret ?? SECRET_KEYS.has(meta.key);
  const current = isSet ? (secret ? `Set (${field?.value})` : (field?.value ?? "")) : "Not set";
  return (
    <div className={styles.field} style={{ marginTop: "var(--space-3)" }}>
      <span className={styles.label}>{meta.label}</span>
      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
        <input
          className={styles.control}
          type={secret ? "password" : "text"}
          placeholder={isSet ? "Leave blank to keep" : (meta.placeholder ?? "")}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
        {isSet && !disabled && (
          <Button variant="ghost" size="sm" onClick={onClear}>
            Clear
          </Button>
        )}
      </div>
      <span className={styles.value} style={{ fontSize: "var(--text-xs)" }}>
        {current}
      </span>
    </div>
  );
}

/**
 * Providers (I2c/I3b, operator-only): set the chat-model provider keys and Google/Telegram
 * credentials at runtime. Changes apply to the live deployment (the chat plane + OAuth wiring are
 * rebuilt in place) — no redeploy. Secrets are never shown back; a blank input keeps the current
 * value, "Clear" removes it. Embeddings stay env-only (changing one is a re-index).
 */
export function ProvidersSection() {
  const { operatorToken } = useSession();
  const [config, setConfig] = useState<DeploymentConfigView | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!operatorToken) {
      setStatus("ready");
      return;
    }
    setStatus("loading");
    try {
      setConfig(await getDeploymentConfig(operatorToken));
      setStatus("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t load deployment config.");
      setStatus("error");
    }
  }, [operatorToken]);

  useEffect(() => {
    void load();
  }, [load]);

  async function apply(values: Record<string, string | null>) {
    if (!operatorToken) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      setConfig(await updateDeploymentConfig(operatorToken, values));
      setEdits({});
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t save. Check the values and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    // Send only fields the operator typed into (a blank input is "keep current", not "clear").
    const values = Object.fromEntries(
      Object.entries(edits).filter(([, v]) => v.trim() !== ""),
    );
    if (Object.keys(values).length === 0) {
      setError("Nothing to save — enter a value, or use Clear to remove one.");
      return;
    }
    await apply(values);
  }

  if (status === "error") {
    return (
      <>
        <SectionHeader title="Providers" />
        <ErrorState
          title="Couldn’t load deployment config"
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

  const fields = new Map((config?.fields ?? []).map((f) => [f.key, f]));
  const st = config?.status;
  const runtimeEnabled = st?.runtime_config_enabled ?? false;

  return (
    <>
      <SectionHeader
        title="Providers"
        lede="Connect a chat model and the Google/Telegram credentials for connectors. Changes apply live — no redeploy."
      />

      {st && (
        <>
          <StatusRow label="Answering model">
            {st.chat_provider ? (
              <Badge variant="success" dot>
                {st.chat_provider}
              </Badge>
            ) : (
              <Badge variant="warning" dot>
                None — answers are extractive
              </Badge>
            )}
          </StatusRow>
          <StatusRow label="Embeddings">
            <Badge variant="neutral">{st.embeddings_source}</Badge>
          </StatusRow>
          <StatusRow label="Google OAuth">
            <Badge variant={st.google_oauth_configured ? "success" : "neutral"} dot>
              {st.google_oauth_configured ? "Configured" : "Not configured"}
            </Badge>
          </StatusRow>
          <StatusRow label="Telegram TDLib">
            <Badge variant={st.telegram_tdlib_configured ? "success" : "neutral"} dot>
              {st.telegram_tdlib_configured ? "Configured" : "Not configured"}
            </Badge>
          </StatusRow>
        </>
      )}

      {!runtimeEnabled && (
        <div className={styles.note}>
          Runtime configuration is read-only here: set a credential-store key
          (<code>METIS_GATEWAY_CRED_STORE_KEY</code>) on the deployment to enable saving provider
          keys and credentials from this screen. The values below reflect the current environment.
        </div>
      )}

      {GROUPS.map((group) => (
        <div key={group.title} style={{ marginTop: "var(--space-5)" }}>
          <h3 className={styles.label}>{group.title}</h3>
          <p className={styles.value} style={{ maxWidth: "34rem" }}>
            {group.lede}
          </p>
          {group.keys.map((meta) => (
            <FieldRow
              key={meta.key}
              meta={meta}
              field={fields.get(meta.key)}
              value={edits[meta.key] ?? ""}
              disabled={!runtimeEnabled || busy}
              onChange={(v) => {
                setEdits((prev) => ({ ...prev, [meta.key]: v }));
                setSaved(false);
              }}
              onClear={() => void apply({ [meta.key]: "" })}
            />
          ))}
        </div>
      ))}

      {runtimeEnabled && (
        <div className={styles.actions} style={{ marginTop: "var(--space-5)" }}>
          <Button variant="primary" onClick={() => void save()} disabled={busy}>
            {busy ? "Applying…" : "Save & apply"}
          </Button>
          {saved && <span className={styles.saved}>Applied</span>}
        </div>
      )}
      {error && <div className={styles.error}>{error}</div>}
    </>
  );
}
