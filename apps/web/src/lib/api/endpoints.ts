/*
 * One typed function per API endpoint the web app uses. Components call these (via
 * hooks) and never build URLs themselves.
 */
import { apiRequest, setCsrfToken } from "./client";
import type {
  ColumnType,
  DatasetColumn,
  DatasetDetail,
  DatasetSummary,
  Page,
  PreviewResponse,
  QueryHistoryItem,
  QueryOrigin,
  ReportDetail,
  ReportSummary,
  SessionInfo,
  SessionStatus,
  SessionSummary,
  UploadReview,
} from "./types";

const UPLOAD_TIMEOUT_MS = 120_000; // big files: analysis and loading happen in the request

async function session(path: string, body?: unknown): Promise<SessionInfo> {
  const res = await apiRequest<SessionInfo>(path, {
    method: body === undefined ? "GET" : "POST",
    body,
    retryOnAuth: false,
  });
  setCsrfToken(res.data.csrf_token);
  return res.data;
}

export const auth = {
  me: async (): Promise<SessionInfo> => {
    try {
      return await session("/auth/me");
    } catch (error) {
      // An expired access token is normal after a while: try the refresh cookie once.
      const res = await apiRequest<SessionInfo>("/auth/refresh", {
        method: "POST",
        retryOnAuth: false,
      }).catch(() => {
        throw error;
      });
      setCsrfToken(res.data.csrf_token);
      return res.data;
    }
  },
  login: (email: string, password: string) => session("/auth/login", { email, password }),
  register: (email: string, password: string, full_name: string) =>
    session("/auth/register", { email, password, full_name }),
  logout: async (): Promise<void> => {
    await apiRequest("/auth/logout", { method: "POST", retryOnAuth: false });
    setCsrfToken(null);
  },
};

export const datasets = {
  list: async () => (await apiRequest<{ items: DatasetSummary[] }>("/datasets")).data.items,
  get: async (id: string) => (await apiRequest<DatasetDetail>(`/datasets/${id}`)).data,
  upload: async (file: File, name: string, description?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (name.trim()) form.append("name", name.trim());
    if (description?.trim()) form.append("description", description.trim());
    return (
      await apiRequest<UploadReview>("/datasets/uploads", {
        method: "POST",
        body: form,
        timeoutMs: UPLOAD_TIMEOUT_MS,
      })
    ).data;
  },
  finalize: async (id: string, columnTypes: Record<string, ColumnType>) =>
    (
      await apiRequest<DatasetDetail>(`/datasets/${id}/finalize`, {
        method: "POST",
        body: { column_types: columnTypes },
        timeoutMs: UPLOAD_TIMEOUT_MS,
      })
    ).data,
  loadSample: async () =>
    (
      await apiRequest<{ dataset: DatasetDetail; created: boolean }>("/datasets/demo", {
        method: "POST",
        timeoutMs: 60_000,
      })
    ).data,
  preview: async (
    id: string,
    table: string,
    opts: { limit: number; offset: number; reveal?: boolean },
  ) =>
    (
      await apiRequest<PreviewResponse>(
        `/datasets/${id}/tables/${encodeURIComponent(table)}/preview`,
        {
          query: { limit: opts.limit, offset: opts.offset, reveal_sensitive: opts.reveal ?? false },
        },
      )
    ).data,
  updateColumn: async (
    id: string,
    columnId: string,
    patch: { description?: string | null; is_sensitive?: boolean },
  ) =>
    (
      await apiRequest<DatasetColumn>(`/datasets/${id}/columns/${columnId}`, {
        method: "PATCH",
        body: patch,
      })
    ).data,
  update: async (id: string, patch: { name?: string; description?: string | null }) =>
    (await apiRequest<DatasetDetail>(`/datasets/${id}`, { method: "PATCH", body: patch })).data,
  remove: async (id: string) => {
    await apiRequest(`/datasets/${id}`, { method: "DELETE", timeoutMs: 30_000 });
  },
};

export const history = {
  queries: async (opts: {
    cursor?: string | null;
    origin?: QueryOrigin | "";
    datasetId?: string;
  }) =>
    (
      await apiRequest<Page<QueryHistoryItem>>("/history/queries", {
        query: { limit: 25, cursor: opts.cursor, origin: opts.origin, dataset_id: opts.datasetId },
      })
    ).data,
  sessions: async (opts: { cursor?: string | null; status?: SessionStatus | ""; q?: string }) =>
    (
      await apiRequest<Page<SessionSummary>>("/history/sessions", {
        query: { limit: 25, cursor: opts.cursor, status: opts.status, q: opts.q },
      })
    ).data,
};

export const reports = {
  list: async (cursor?: string | null) =>
    (await apiRequest<Page<ReportSummary>>("/reports", { query: { limit: 25, cursor } })).data,
  get: async (id: string) => (await apiRequest<ReportDetail>(`/reports/${id}`)).data,
  remove: async (id: string) => {
    await apiRequest(`/reports/${id}`, { method: "DELETE" });
  },
  markdown: async (id: string) =>
    (await apiRequest<string>(`/reports/${id}/export.md`, { responseType: "text" })).data,
};
