import { useRef, useState } from "react";

import type { Citation } from "@/api/types";
import {
  Badge,
  BlockedState,
  Button,
  Drawer,
  EmptyState,
  ErrorState,
  ScopeBadge,
  SensitivityBadge,
} from "@/components";
import type { BadgeVariant } from "@/components/Badge";
import type { WorkspaceScope } from "@/domain/types";
import { useSession } from "@/session/SessionContext";

import type { AskOutcome } from "./useAsk";
import { useAsk } from "./useAsk";
import styles from "./ask.module.css";

const MAX_TEXTAREA_PX = 192; // 12rem, matches the CSS max-height

const FRAMING: Record<AskOutcome, { label: string; variant: BadgeVariant }> = {
  sufficient: { label: "Answered from your sources", variant: "success" },
  insufficient: { label: "Not enough evidence yet", variant: "warning" },
  conflicting: { label: "Sources disagree", variant: "warning" },
  action_proposal: { label: "Needs your approval", variant: "info" },
};

const scopeForCitation = (scope: Citation["scope"]): WorkspaceScope | null =>
  scope === "personal" ? "personal" : scope === null ? null : "shared";

/** The Ask screen (D1): context strip, scrolling answer area with a full state machine, and a
 *  pinned composer. Citations open a drawer (D2 enriches the cards + drawer with source detail). */
export function AskScreen() {
  const { activeWorkspace, scope } = useSession();
  const { state, canAsk, ask, reset } = useAsk();
  const [draft, setDraft] = useState("");
  const [selected, setSelected] = useState<{ citation: Citation; index: number } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function autoGrow() {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_TEXTAREA_PX)}px`;
  }

  function submit() {
    const text = draft.trim();
    if (!text || !canAsk || state.kind === "asking") return;
    void ask(text);
    setDraft("");
    requestAnimationFrame(autoGrow);
  }

  return (
    <div className={styles.screen}>
      <div className={styles.strip}>
        <span className={styles.stripLabel}>Asking</span>
        <span className={styles.stripValue}>{activeWorkspace?.name ?? "No workspace"}</span>
        <span className={styles.stripLabel}>· scope</span>
        <span className={styles.stripValue}>{scope}</span>
      </div>

      <div className={styles.scroll}>
        <div className={styles.inner}>
          <AnswerArea
            state={state}
            canAsk={canAsk}
            onPickCitation={(citation, index) => setSelected({ citation, index })}
            onReset={reset}
          />
        </div>
      </div>

      <form
        className={styles.composer}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className={styles.composerInner}>
          <label htmlFor="ask-input" className="sr-only">
            Ask the workspace
          </label>
          <textarea
            id="ask-input"
            ref={textareaRef}
            className={styles.textarea}
            value={draft}
            rows={1}
            placeholder={canAsk ? "Ask anything about your sources…" : "Select a workspace to ask"}
            disabled={!canAsk}
            onChange={(e) => {
              setDraft(e.target.value);
              autoGrow();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <Button
            type="submit"
            variant="primary"
            disabled={!canAsk || !draft.trim() || state.kind === "asking"}
          >
            {state.kind === "asking" ? "Asking…" : "Ask"}
          </Button>
        </div>
        <p className={styles.hint}>Enter to send · Shift+Enter for a new line</p>
      </form>

      <Drawer open={selected !== null} onClose={() => setSelected(null)} title="Citation">
        {selected && <CitationDetail citation={selected.citation} index={selected.index} />}
      </Drawer>
    </div>
  );
}

interface AnswerAreaProps {
  state: ReturnType<typeof useAsk>["state"];
  canAsk: boolean;
  onPickCitation: (citation: Citation, index: number) => void;
  onReset: () => void;
}

function AnswerArea({ state, canAsk, onPickCitation, onReset }: AnswerAreaProps) {
  if (!canAsk) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Pick a workspace from the switcher to start asking grounded questions."
      />
    );
  }

  switch (state.kind) {
    case "idle":
      return (
        <EmptyState
          glyph="◆"
          title="Ask anything about your sources"
          description="Every answer is grounded in your evidence and shows the citations behind it — never a black-box reply."
        />
      );

    case "asking":
      return (
        <>
          <p className={styles.question}>{state.question}</p>
          <p className={styles.thinking} role="status">
            Looking through your sources…
          </p>
        </>
      );

    case "blocked":
      return (
        <BlockedState
          title="Held back by policy"
          description={state.message}
          actions={
            <Button variant="secondary" onClick={onReset}>
              Ask something else
            </Button>
          }
        />
      );

    case "error":
      return (
        <ErrorState
          title="Couldn’t get an answer"
          description={state.message}
          actions={
            <Button variant="secondary" onClick={onReset}>
              Try again
            </Button>
          }
        />
      );

    case "answered": {
      const { question, response, outcome } = state;
      const framing = FRAMING[outcome];
      return (
        <>
          <p className={styles.question}>{question}</p>
          <div className={styles.framing}>
            <Badge variant={framing.variant} dot>
              {framing.label}
            </Badge>
          </div>

          {response.answer ? (
            <p className={styles.answer}>{response.answer}</p>
          ) : (
            <p className={styles.answer} style={{ color: "var(--color-text-muted)" }}>
              No answer text was returned.
            </p>
          )}

          {outcome === "conflicting" && (
            <div className={styles.note}>
              The evidence disagrees on this. Both sides are kept — open Review to resolve it. (The
              full “sources disagree” panel arrives with D4.)
            </div>
          )}
          {outcome === "action_proposal" && (
            <div className={styles.note}>
              This request would take an action, so it’s waiting for your approval. (Action cards
              arrive with D7.)
            </div>
          )}

          {response.citations.length > 0 && (
            <>
              <div className={styles.sectionLabel}>
                {response.citations.length} citation{response.citations.length === 1 ? "" : "s"}
              </div>
              <div className={styles.citations}>
                {response.citations.map((citation, index) => {
                  const cScope = scopeForCitation(citation.scope);
                  return (
                    <button
                      key={`${citation.claim_id}-${index}`}
                      type="button"
                      className={styles.citationChip}
                      onClick={() => onPickCitation(citation, index)}
                    >
                      Source {index + 1}
                      {cScope && <ScopeBadge scope={cScope} />}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </>
      );
    }
  }
}

function CitationDetail({ citation, index }: { citation: Citation; index: number }) {
  const cScope = scopeForCitation(citation.scope);
  return (
    <div>
      <div className={styles.framing}>
        <strong>Source {index + 1}</strong>
        {cScope && <ScopeBadge scope={cScope} />}
        {citation.sensitivity && <SensitivityBadge level={citation.sensitivity} />}
      </div>
      <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>
        This citation points to claim <code>{citation.claim_id.slice(0, 16)}…</code>. The quoted
        source span, document, date, and page arrive with the evidence drill-down (D2).
      </p>
    </div>
  );
}
