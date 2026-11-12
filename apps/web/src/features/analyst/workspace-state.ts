/*
 * Analyst workspace state (pure reducer, unit-tested).
 *
 * Phase 2: a "run" either replays a recorded sample scenario step by step or, for
 * any other question, is marked `unmatched` (the UI explains that live analysis
 * is not connected yet). In Phase 7 the TICK action is replaced by SSE events.
 */
import type { AgentNode, Conversation, SampleScenario, TimelineStep } from "@/types/domain";

export type ThreadRunStatus = "running" | "done" | "cancelled" | "unmatched";

export interface ThreadRun {
  id: string;
  conversationId: string;
  question: string;
  datasetId: string;
  scenarioId: string | null;
  status: ThreadRunStatus;
  /** Number of timeline steps revealed so far. */
  revealed: number;
}

export interface WorkspaceConversation extends Pick<
  Conversation,
  "id" | "title" | "datasetId" | "updatedAt"
> {
  isNew?: boolean;
}

export interface WorkspaceState {
  datasetId: string;
  conversations: WorkspaceConversation[];
  activeConversationId: string | null;
  runs: ThreadRun[];
  /** Run shown in the execution inspector. */
  focusedRunId: string | null;
  counter: number;
}

export type WorkspaceAction =
  | { type: "select_dataset"; datasetId: string }
  | { type: "new_conversation" }
  | {
      type: "open_conversation";
      conversationId: string;
      scenario: SampleScenario | undefined;
      question: string;
    }
  | { type: "ask"; question: string; scenario: SampleScenario | undefined; nowIso: string }
  | { type: "tick"; runId: string; totalSteps: number }
  | { type: "cancel"; runId: string }
  | { type: "focus_run"; runId: string };

export function initialWorkspace(
  datasetId: string,
  conversations: WorkspaceConversation[],
): WorkspaceState {
  return {
    datasetId,
    conversations,
    activeConversationId: null,
    runs: [],
    focusedRunId: null,
    counter: 0,
  };
}

function titleFrom(question: string): string {
  const trimmed = question.trim().replace(/\?$/, "");
  return trimmed.length > 48 ? `${trimmed.slice(0, 46).trimEnd()}…` : trimmed;
}

export function workspaceReducer(state: WorkspaceState, action: WorkspaceAction): WorkspaceState {
  switch (action.type) {
    case "select_dataset":
      return {
        ...state,
        datasetId: action.datasetId,
        activeConversationId: null,
        focusedRunId: null,
      };

    case "new_conversation":
      return { ...state, activeConversationId: null, focusedRunId: null };

    case "open_conversation": {
      const existing = state.runs.filter((r) => r.conversationId === action.conversationId);
      const conversation = state.conversations.find((c) => c.id === action.conversationId);
      if (existing.length > 0 || !conversation) {
        return {
          ...state,
          activeConversationId: action.conversationId,
          datasetId: conversation?.datasetId ?? state.datasetId,
          focusedRunId: existing.at(-1)?.id ?? null,
        };
      }
      // Past conversations open fully completed (no replay).
      const id = `run_${state.counter + 1}`;
      const run: ThreadRun = {
        id,
        conversationId: action.conversationId,
        question: action.question,
        datasetId: conversation.datasetId,
        scenarioId: action.scenario?.id ?? null,
        status: action.scenario ? "done" : "unmatched",
        revealed: action.scenario?.result.timeline.length ?? 0,
      };
      return {
        ...state,
        counter: state.counter + 1,
        datasetId: conversation.datasetId,
        activeConversationId: action.conversationId,
        runs: [...state.runs, run],
        focusedRunId: id,
      };
    }

    case "ask": {
      const question = action.question.trim();
      if (!question) return state;
      let counter = state.counter;
      let conversations = state.conversations;
      let conversationId = state.activeConversationId;
      if (!conversationId) {
        counter += 1;
        conversationId = `cv_new_${counter}`;
        conversations = [
          {
            id: conversationId,
            title: titleFrom(question),
            datasetId: state.datasetId,
            updatedAt: action.nowIso,
            isNew: true,
          },
          ...conversations,
        ];
      } else {
        conversations = conversations.map((c) =>
          c.id === conversationId ? { ...c, updatedAt: action.nowIso } : c,
        );
      }
      counter += 1;
      const run: ThreadRun = {
        id: `run_${counter}`,
        conversationId,
        question,
        datasetId: state.datasetId,
        scenarioId: action.scenario?.id ?? null,
        status: action.scenario ? "running" : "unmatched",
        revealed: 0,
      };
      return {
        ...state,
        counter,
        conversations,
        activeConversationId: conversationId,
        runs: [...state.runs, run],
        focusedRunId: run.id,
      };
    }

    case "tick":
      return {
        ...state,
        runs: state.runs.map((r) => {
          if (r.id !== action.runId || r.status !== "running") return r;
          const revealed = Math.min(r.revealed + 1, action.totalSteps);
          return { ...r, revealed, status: revealed >= action.totalSteps ? "done" : "running" };
        }),
      };

    case "cancel":
      return {
        ...state,
        runs: state.runs.map((r) =>
          r.id === action.runId && r.status === "running" ? { ...r, status: "cancelled" } : r,
        ),
      };

    case "focus_run":
      return { ...state, focusedRunId: action.runId };
  }
}

/** What a run has produced so far, given how many steps are revealed. */
export function revealedOutputs(timeline: TimelineStep[], revealed: number) {
  const done = timeline.slice(0, revealed);
  const reached = (node: AgentNode) => done.some((s) => s.node === node && s.status !== "failed");
  return {
    understood: reached("understand_query"),
    planned: reached("plan_analysis"),
    executed: reached("execute_sql"),
    charted: reached("generate_visualization"),
    verified: reached("verify_insights"),
    complete: revealed >= timeline.length,
  };
}

/** Delay before revealing the next step: proportional to its recorded duration, bounded for readability. */
export function replayDelay(step: TimelineStep | undefined, reducedMotion: boolean): number {
  if (reducedMotion) return 40;
  if (!step) return 300;
  return Math.round(Math.min(1100, Math.max(260, step.durationMs * 0.4)));
}
