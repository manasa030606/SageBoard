/*
 * Data-access layer — the ONLY module components use to read data.
 *
 * Phase 2: every function reads the demo data in src/mocks. In later phases each
 * body is replaced by a call to the typed API client (src/lib/api), keeping the
 * same signatures, so pages and components do not change.
 */
import { DATASETS } from "@/mocks/datasets";
import { DEMO_NOW } from "@/mocks/sales";
import { SAMPLE_SCENARIOS } from "@/mocks/scenarios";
import { CONVERSATIONS, HISTORY, REPORTS, USAGE, USER_SETTINGS } from "@/mocks/workspace";
import type {
  Conversation,
  DashboardSummary,
  Dataset,
  HistoryEntry,
  Report,
  SampleScenario,
  UsageSummary,
  UserSettings,
} from "@/types/domain";

import { getDashboardSummary } from "./analytics";

/** True while the UI runs on demo data (shown as a badge in the app shell). */
export const DEMO_MODE = true;

/** Fixed "now" for demo data so relative times render identically on server and client. */
export const NOW = DEMO_NOW;

export function getDashboard(): DashboardSummary {
  return getDashboardSummary();
}

export function listDatasets(): readonly Dataset[] {
  return DATASETS;
}

export function getDataset(id: string): Dataset | undefined {
  return DATASETS.find((d) => d.id === id);
}

export function listHistory(): readonly HistoryEntry[] {
  return HISTORY;
}

export function listConversations(): readonly Conversation[] {
  return CONVERSATIONS;
}

export function listScenarios(datasetId?: string): readonly SampleScenario[] {
  return datasetId ? SAMPLE_SCENARIOS.filter((s) => s.datasetId === datasetId) : SAMPLE_SCENARIOS;
}

export function getScenario(id: string): SampleScenario | undefined {
  return SAMPLE_SCENARIOS.find((s) => s.id === id);
}

const normalise = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

/**
 * Demo mode only: find the recorded sample run for a question. Matching is
 * deliberately strict (same words, ignoring case and punctuation) so the demo never
 * presents a recorded answer as the response to a different question.
 */
export function findScenarioForQuestion(
  question: string,
  datasetId: string,
): SampleScenario | undefined {
  const wanted = normalise(question);
  return SAMPLE_SCENARIOS.find(
    (s) => s.datasetId === datasetId && normalise(s.question) === wanted,
  );
}

export function scenarioForConversation(conversationId: string): SampleScenario | undefined {
  const conversation = CONVERSATIONS.find((c) => c.id === conversationId);
  const run = HISTORY.find((h) => h.id === conversation?.runIds[0]);
  return run?.scenarioId ? getScenario(run.scenarioId) : undefined;
}

export function listReports(): readonly Report[] {
  return REPORTS;
}

export function getReport(id: string): Report | undefined {
  return REPORTS.find((r) => r.id === id);
}

export function getUserSettings(): UserSettings {
  return USER_SETTINGS;
}

export function getUsage(): UsageSummary {
  return USAGE;
}
