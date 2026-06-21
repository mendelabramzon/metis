/*
 * Activation instrumentation (H6).
 *
 * Activation = a user who has connected a dense source, asked a question, AND opened a citation.
 * The three milestones are tracked per user in localStorage (idempotent), and a single "activated"
 * event fires when all three are first met. Events are dispatched on `window` (a hook a real
 * analytics sink can subscribe to without wiring one now) and logged for dev visibility.
 */

export type ActivationMilestone = "connected_source" | "asked_question" | "opened_citation";

const MILESTONES: readonly ActivationMilestone[] = [
  "connected_source",
  "asked_question",
  "opened_citation",
];

const key = (userId: string): string => `metis.activation.${userId}`;

interface ActivationState {
  milestones: ActivationMilestone[];
  activatedAt?: string;
}

function read(userId: string): ActivationState {
  try {
    const raw = localStorage.getItem(key(userId));
    if (raw) return JSON.parse(raw) as ActivationState;
  } catch {
    /* storage unavailable / corrupt — start fresh */
  }
  return { milestones: [] };
}

function write(userId: string, state: ActivationState): void {
  try {
    localStorage.setItem(key(userId), JSON.stringify(state));
  } catch {
    /* storage unavailable — the in-session event still fires */
  }
}

function emit(name: string, detail: Record<string, unknown>): void {
  try {
    window.dispatchEvent(new CustomEvent(`metis:${name}`, { detail }));
  } catch {
    /* no window (non-browser) — nothing to dispatch to */
  }
  console.info(`[activation] ${name}`, detail);
}

/** Whether this user has hit all three activation milestones. */
export function isActivated(userId: string): boolean {
  return read(userId).activatedAt != null;
}

/** Record an activation milestone for a user; emits "activated" once all three are met. */
export function trackActivation(userId: string, milestone: ActivationMilestone): void {
  const state = read(userId);
  if (state.milestones.includes(milestone)) return;
  state.milestones = [...state.milestones, milestone];
  emit("activation_milestone", { userId, milestone, milestones: state.milestones });
  if (state.activatedAt == null && MILESTONES.every((m) => state.milestones.includes(m))) {
    state.activatedAt = new Date().toISOString();
    emit("activated", { userId, at: state.activatedAt });
  }
  write(userId, state);
}
