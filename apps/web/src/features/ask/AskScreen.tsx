import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { trackActivation } from "@/analytics/activation";
import type { Citation } from "@/api/types";
import {
  Badge,
  BlockedState,
  Button,
  Drawer,
  EmptyState,
  ErrorState,
  RoutingBadge,
} from "@/components";
import type { BadgeVariant } from "@/components/Badge";
import { WhileYouWereAway } from "@/features/digest/WhileYouWereAway";
import { useSession } from "@/session/SessionContext";

import { ActionCard } from "./ActionCard";
import { CitationCards } from "./CitationCards";
import { DisagreementPanel } from "./DisagreementPanel";
import { CitationDrawerBody } from "./CitationDrawerBody";
import { InsufficientActions } from "./InsufficientActions";
import type { AskOutcome } from "./useAsk";
import { useAsk } from "./useAsk";
import { useStarterQuestions } from "./useStarterQuestions";
import styles from "./ask.module.css";

const MAX_TEXTAREA_PX = 192; // 12rem, matches the CSS max-height

const FRAMING: Record<AskOutcome, { label: string; variant: BadgeVariant }> = {
  sufficient: { label: "Answered from your sources", variant: "success" },
  insufficient: { label: "Not enough evidence yet", variant: "warning" },
  conflicting: { label: "Sources disagree", variant: "warning" },
  action_proposal: { label: "Needs your approval", variant: "info" },
};

/** The Ask screen (D1): context strip, scrolling answer area with a full state machine, and a
 *  pinned composer. Citations render as scope/sensitivity cards that open a source drawer (D2). */
export function AskScreen() {
  const { activeWorkspace, scope, user } = useSession();
  const { state, canAsk, ask, decideAction, reset } = useAsk();
  const starterQuestions = useStarterQuestions();
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

      <WhileYouWereAway />

      <div className={styles.scroll}>
        <div className={styles.inner}>
          <AnswerArea
            state={state}
            canAsk={canAsk}
            starterQuestions={starterQuestions}
            onAsk={(q) => void ask(q)}
            onPickCitation={(citation, index) => {
              setSelected({ citation, index });
              if (user) trackActivation(user.id, "opened_citation");
            }}
            onDecide={(approve) => void decideAction(approve)}
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
        {selected && <CitationDrawerBody citation={selected.citation} index={selected.index} />}
      </Drawer>
    </div>
  );
}

interface AnswerAreaProps {
  state: ReturnType<typeof useAsk>["state"];
  canAsk: boolean;
  starterQuestions: string[];
  onAsk: (question: string) => void;
  onPickCitation: (citation: Citation, index: number) => void;
  onDecide: (approve: boolean) => void;
  onReset: () => void;
}

function AnswerArea({
  state,
  canAsk,
  starterQuestions,
  onAsk,
  onPickCitation,
  onDecide,
  onReset,
}: AnswerAreaProps) {
  const navigate = useNavigate();

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
      // First Value loop (H3): suggest grounded questions once there's evidence; otherwise
      // foreground adding the first source.
      if (starterQuestions.length > 0) {
        return (
          <>
            <EmptyState
              glyph="◆"
              title="Ask anything about your sources"
              description="Every answer is grounded in your evidence and shows the citations behind it — never a black-box reply."
            />
            <div className={styles.starterLabel}>Try one of these to get started</div>
            <div className={styles.starters}>
              {starterQuestions.map((question) => (
                <button
                  key={question}
                  type="button"
                  className={styles.starterChip}
                  onClick={() => onAsk(question)}
                >
                  {question}
                </button>
              ))}
            </div>
          </>
        );
      }
      return (
        <EmptyState
          glyph="◆"
          title="Let’s get your first answer"
          description="Add a source — upload a few documents or connect a mailbox — and Metis will suggest questions you can ask over it, each answer citing the evidence."
          actions={
            <Button variant="primary" onClick={() => navigate("/sources")}>
              Add your first source
            </Button>
          }
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

    case "action":
      return (
        <>
          <p className={styles.question}>{state.question}</p>
          <div className={styles.framing}>
            <Badge variant="info" dot>
              Needs your approval
            </Badge>
          </div>
          <ActionCard
            action={state.action}
            busy={false}
            onApprove={() => onDecide(true)}
            onReject={() => onDecide(false)}
          />
        </>
      );

    case "executing":
      return (
        <>
          <p className={styles.question}>{state.question}</p>
          <ActionCard action={state.action} busy onApprove={() => {}} onReject={() => {}} />
        </>
      );

    case "executed": {
      const { result } = state;
      const resultId = result.job_id
        ? `Queued sync job ${result.job_id.slice(0, 12)}…`
        : result.doc_id
          ? `Created memory ${result.doc_id.slice(0, 12)}…`
          : result.patch_id
            ? `Wiki patch ${result.patch_id.slice(0, 12)}… proposed for review`
            : result.source_id
              ? `Source ${result.source_id.slice(0, 12)}… registered`
              : null;
      return (
        <>
          <p className={styles.question}>{state.question}</p>
          <div className={styles.resultDetail}>
            <span aria-hidden="true">✓</span> {result.detail}
          </div>
          {resultId && <div className={styles.resultMeta}>{resultId}</div>}
          <Button variant="secondary" onClick={onReset}>
            Ask something else
          </Button>
        </>
      );
    }

    case "blocked": {
      const isExternal = state.reason === "external";
      return (
        <BlockedState
          title={isExternal ? "This needs approval" : "Held back by policy"}
          description={
            isExternal
              ? `${state.message} An operator can review and approve it in Operations.`
              : `${state.message || "This request touches restricted data, so it was held back."} Try narrowing your question, or ask an admin about the workspace’s model policy.`
          }
          actions={
            <Button variant="secondary" onClick={onReset}>
              Ask something else
            </Button>
          }
        />
      );
    }

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

          {response.routed_local !== null && (
            <div className={styles.routingNote}>
              <RoutingBadge outcome={response.routed_local ? "local" : "external"} />
              <span>
                {response.routed_local
                  ? "Kept on your device — restricted evidence never left."
                  : "Used an external model for this answer."}
              </span>
            </div>
          )}

          {outcome === "conflicting" && response.disagreements.length > 0 && (
            <DisagreementPanel
              disagreements={response.disagreements}
              onViewSource={onPickCitation}
            />
          )}
          {outcome === "action_proposal" && (
            <div className={styles.note}>
              This request would take an action, so it’s waiting for your approval. (Action cards
              arrive with D7.)
            </div>
          )}

          {outcome === "insufficient" && (
            <InsufficientActions onRetry={() => onAsk(question)} />
          )}

          {response.citations.length > 0 && (
            <>
              <div className={styles.sectionLabel}>
                {response.citations.length} citation{response.citations.length === 1 ? "" : "s"}
              </div>
              <CitationCards citations={response.citations} onOpen={onPickCitation} />
              {outcome === "sufficient" && (
                <div className={styles.verifyNudge}>
                  Tap a source to see the exact line it came from — that’s how you verify an answer.
                </div>
              )}
            </>
          )}
        </>
      );
    }
  }
}
