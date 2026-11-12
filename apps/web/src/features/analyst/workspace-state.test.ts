import { describe, expect, it } from "vitest";

import { SAMPLE_SCENARIOS } from "@/mocks/scenarios";

import {
  initialWorkspace,
  replayDelay,
  revealedOutputs,
  workspaceReducer,
  type WorkspaceState,
} from "./workspace-state";

const trend = SAMPLE_SCENARIOS.find((s) => s.id === "sc_trend")!;
const now = "2026-11-12T14:30:00Z";

function start(): WorkspaceState {
  return initialWorkspace("ds_retail_demo", [
    { id: "cv_old", title: "Old", datasetId: "ds_retail_demo", updatedAt: now },
  ]);
}

describe("workspaceReducer", () => {
  it("asking without an active conversation creates one and a running run", () => {
    const s = workspaceReducer(start(), {
      type: "ask",
      question: trend.question,
      scenario: trend,
      nowIso: now,
    });
    expect(s.conversations[0]?.isNew).toBe(true);
    expect(s.activeConversationId).toBe(s.conversations[0]?.id);
    expect(s.runs).toHaveLength(1);
    expect(s.runs[0]).toMatchObject({ status: "running", revealed: 0, scenarioId: "sc_trend" });
  });

  it("a question with no recorded sample is marked unmatched, never answered", () => {
    const s = workspaceReducer(start(), {
      type: "ask",
      question: "Forecast next year",
      scenario: undefined,
      nowIso: now,
    });
    expect(s.runs[0]?.status).toBe("unmatched");
    expect(s.runs[0]?.scenarioId).toBeNull();
  });

  it("follow-ups stay in the same conversation", () => {
    let s = workspaceReducer(start(), {
      type: "ask",
      question: trend.question,
      scenario: trend,
      nowIso: now,
    });
    s = workspaceReducer(s, { type: "ask", question: "Another", scenario: undefined, nowIso: now });
    expect(new Set(s.runs.map((r) => r.conversationId)).size).toBe(1);
    expect(s.conversations.filter((c) => c.isNew)).toHaveLength(1);
  });

  it("ticks reveal steps one at a time and finish the run", () => {
    let s = workspaceReducer(start(), {
      type: "ask",
      question: trend.question,
      scenario: trend,
      nowIso: now,
    });
    const id = s.runs[0]!.id;
    const total = trend.result.timeline.length;
    for (let i = 0; i < total + 3; i++)
      s = workspaceReducer(s, { type: "tick", runId: id, totalSteps: total });
    expect(s.runs[0]).toMatchObject({ revealed: total, status: "done" });
  });

  it("cancel stops a running run and further ticks do nothing", () => {
    let s = workspaceReducer(start(), {
      type: "ask",
      question: trend.question,
      scenario: trend,
      nowIso: now,
    });
    const id = s.runs[0]!.id;
    s = workspaceReducer(s, { type: "tick", runId: id, totalSteps: 13 });
    s = workspaceReducer(s, { type: "cancel", runId: id });
    s = workspaceReducer(s, { type: "tick", runId: id, totalSteps: 13 });
    expect(s.runs[0]).toMatchObject({ status: "cancelled", revealed: 1 });
  });

  it("opening a past conversation shows it completed", () => {
    const s = workspaceReducer(start(), {
      type: "open_conversation",
      conversationId: "cv_old",
      scenario: trend,
      question: trend.question,
    });
    expect(s.runs[0]).toMatchObject({ status: "done", revealed: trend.result.timeline.length });
  });
});

describe("revealedOutputs", () => {
  it("results appear only after the steps that produce them", () => {
    const t = trend.result.timeline;
    const before = revealedOutputs(
      t,
      t.findIndex((s) => s.node === "execute_sql"),
    );
    expect(before.executed).toBe(false);
    const after = revealedOutputs(t, t.findIndex((s) => s.node === "execute_sql") + 1);
    expect(after.executed).toBe(true);
    expect(after.verified).toBe(false);
    expect(revealedOutputs(t, t.length).complete).toBe(true);
  });

  it("a failed validation step does not count as reaching that node", () => {
    const regions = SAMPLE_SCENARIOS.find((s) => s.id === "sc_regions")!.result.timeline;
    const firstExec = regions.findIndex((s) => s.node === "execute_sql");
    expect(regions[firstExec]?.status).toBe("failed");
    expect(revealedOutputs(regions, firstExec + 1).executed).toBe(false);
  });
});

describe("replayDelay", () => {
  it("is bounded and near-instant with reduced motion", () => {
    expect(replayDelay({ ...trend.result.timeline[0]!, durationMs: 99_999 }, false)).toBe(1100);
    expect(replayDelay({ ...trend.result.timeline[0]!, durationMs: 1 }, false)).toBe(260);
    expect(replayDelay(trend.result.timeline[0], true)).toBe(40);
  });
});
