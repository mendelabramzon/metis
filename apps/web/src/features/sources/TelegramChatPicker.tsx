import { useEffect, useState } from "react";

import { createSource, listTelegramChats } from "@/api/client";
import type { TelegramChatView } from "@/api/types";
import { Badge, Button } from "@/components";
import type { Sensitivity } from "@/domain/types";
import { SENSITIVITY_ORDER } from "@/domain/types";
import { useSession } from "@/session/SessionContext";

import styles from "./sources.module.css";

/**
 * Telegram chat selection (E4). The bot has no "list my chats" API, so the worker records chats as
 * messages arrive and `GET /telegram/chats` surfaces them. The user adds *specific* chats as
 * sources (each with its own sensitivity default) — unselected conversations are never ingested.
 */
export function TelegramChatPicker({
  defaultSensitivity,
  onChanged,
}: {
  defaultSensitivity: Sensitivity;
  onChanged: () => void;
}) {
  const { operatorToken, activeWorkspaceId } = useSession();
  const [chats, setChats] = useState<TelegramChatView[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [added, setAdded] = useState<ReadonlySet<number>>(new Set());
  const [sensitivities, setSensitivities] = useState<Record<number, Sensitivity>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    if (!operatorToken) return;
    const controller = new AbortController();
    void listTelegramChats(operatorToken, controller.signal)
      .then((list) => {
        if (controller.signal.aborted) return;
        setChats(list);
        setStatus("ready");
      })
      .catch(() => !controller.signal.aborted && setStatus("error"));
    return () => controller.abort();
  }, [operatorToken]);

  async function add(chat: TelegramChatView) {
    if (!operatorToken) return;
    setBusyId(chat.chat_id);
    try {
      await createSource(operatorToken, {
        name: chat.title || `Telegram ${chat.chat_id}`,
        connector: "telegram",
        sensitivity: sensitivities[chat.chat_id] ?? defaultSensitivity,
        config: {
          business_connection_id: chat.business_connection_id,
          chat_id: chat.chat_id,
          chat_type: chat.chat_type,
        },
        ...(activeWorkspaceId ? { workspace_id: activeWorkspaceId } : {}),
      });
      setAdded((prev) => new Set(prev).add(chat.chat_id));
      onChanged();
    } catch {
      /* leave the row addable; the gateway error surfaces in Operations */
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <p className={styles.formNote}>
        Connect your bot to a chat in Telegram’s Business settings — chats it has seen appear here.
        Add only the chats you want ingested; the rest stay private.
      </p>

      {status === "loading" && (
        <p style={{ color: "var(--color-text-muted)" }} role="status">
          Loading chats…
        </p>
      )}
      {status === "error" && (
        <p style={{ color: "var(--status-danger-fg)" }}>Couldn’t load chats.</p>
      )}
      {status === "ready" && chats.length === 0 && (
        <p style={{ color: "var(--color-text-muted)" }}>
          No chats discovered yet. Once your bot sees messages on a connected chat, they’ll show up
          here.
        </p>
      )}

      {chats.length > 0 && (
        <div className={styles.chatList}>
          {chats.map((chat) => (
            <div key={chat.chat_id} className={styles.chatRow}>
              <div className={styles.chatInfo}>
                <div className={styles.chatTitle}>{chat.title || `Chat ${chat.chat_id}`}</div>
                <div className={styles.chatMeta}>{chat.chat_type}</div>
              </div>
              <span style={{ flex: 1 }} />
              {added.has(chat.chat_id) ? (
                <Badge variant="success" dot>
                  Added
                </Badge>
              ) : (
                <div className={styles.chatControls}>
                  <select
                    className={styles.chatSelect}
                    aria-label={`Sensitivity for ${chat.title || chat.chat_id}`}
                    value={sensitivities[chat.chat_id] ?? defaultSensitivity}
                    onChange={(e) =>
                      setSensitivities((prev) => ({
                        ...prev,
                        [chat.chat_id]: e.target.value as Sensitivity,
                      }))
                    }
                  >
                    {SENSITIVITY_ORDER.map((level) => (
                      <option key={level} value={level}>
                        {level}
                      </option>
                    ))}
                  </select>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void add(chat)}
                    disabled={busyId === chat.chat_id}
                  >
                    {busyId === chat.chat_id ? "Adding…" : "Add as source"}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
