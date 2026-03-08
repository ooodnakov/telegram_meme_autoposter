export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

export interface SessionPayload {
  user_id: number;
  username?: string | null;
  language: string;
  languages: Record<string, string>;
  default_language: string;
  bot_username: string;
}

export interface SubmitterInfo {
  is_admin: boolean;
  is_suggestion: boolean;
  user_id?: number;
  source?: string;
}

export interface MediaAsset {
  path: string;
  name: string;
  url: string;
  mime_type?: string | null;
  kind: "image" | "video";
  caption?: string | null;
  source?: string | null;
  group_id?: string | null;
  trashed_at?: string | null;
  expires_at?: string | null;
}

export interface MediaGroup {
  items: MediaAsset[];
  count: number;
  is_group: boolean;
  caption?: string | null;
  source?: string | null;
  submitter?: SubmitterInfo | null;
  group_id?: string | null;
  trashed_at?: string | null;
  expires_at?: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  page: number;
  per_page: number;
  total_pages: number;
  total_items: number;
}

export interface DashboardSummary {
  suggestions_count: number;
  batch_count: number;
  posts_count: number;
  trash_count: number;
  scheduled_count: number;
  next_scheduled_at?: string | null;
  daily: Record<string, number | string>;
  recent_events: EventEntry[];
}

export interface QueueItem {
  path: string;
  name: string;
  url: string;
  mime_type?: string | null;
  kind: "image" | "video";
  caption?: string | null;
  source?: string | null;
  scheduled_at: string;
  scheduled_ts: number;
}

export interface EventEntry {
  timestamp?: string | null;
  action?: string | null;
  origin?: string | null;
  actor?: string | number | null;
  items: Array<{
    path: string;
    name: string;
    media_type?: string | null;
    submitter?: SubmitterInfo | null;
  }>;
  extra: Record<string, unknown>;
}

export interface StatsPayload {
  daily: Record<string, number | string>;
  total: Record<string, number>;
  performance: Record<string, number>;
  approval_24h: number;
  approval_total: number;
  success_24h: number;
  busiest_hour: number | null;
  busiest_count: number;
  daily_errors: number;
  total_errors: number;
  source_acceptance: Array<Record<string, number | string>>;
  processing_histogram: Record<
    string,
    Array<{ label: string; count: number }>
  >;
  daily_post_counts: Array<{ date: string; count: number }>;
}

export interface LeaderboardEntry {
  source: string;
  submissions: number;
  approved: number;
  rejected: number;
  approved_pct: number;
  rejected_pct: number;
}

export interface LeaderboardPayload {
  submissions: LeaderboardEntry[];
  approved: LeaderboardEntry[];
  rejected: LeaderboardEntry[];
}

export interface EventsPayload {
  items: EventEntry[];
  limit: number;
}

async function apiRequest<T>(
  input: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof data === "string"
        ? data
        : (data?.detail ?? data?.message ?? "Request failed");
    throw new ApiError(response.status, detail);
  }

  return data as T;
}

export const api = {
  getSession: () => apiRequest<SessionPayload>("/api/session"),
  setLanguage: (language: string) =>
    apiRequest<{ status: string; language: string }>("/api/session/language", {
      method: "POST",
      body: JSON.stringify({ language }),
    }),
  logout: () => apiRequest<{ status: string }>("/logout", { method: "POST" }),
  getDashboard: () => apiRequest<DashboardSummary>("/api/dashboard"),
  getSuggestions: (page: number) =>
    apiRequest<PaginatedResponse<MediaGroup>>(`/api/suggestions?page=${page}`),
  getPosts: (page: number) =>
    apiRequest<PaginatedResponse<MediaGroup>>(`/api/posts?page=${page}`),
  getBatch: (page: number) =>
    apiRequest<PaginatedResponse<MediaGroup>>(`/api/batch?page=${page}`),
  getTrash: (page: number) =>
    apiRequest<PaginatedResponse<MediaGroup>>(`/api/trash?page=${page}`),
  getQueue: (page: number) =>
    apiRequest<PaginatedResponse<QueueItem>>(`/api/queue?page=${page}`),
  getEvents: (limit = 50) =>
    apiRequest<EventsPayload>(`/api/events?limit=${limit}`),
  getStats: () => apiRequest<StatsPayload>("/api/stats"),
  getLeaderboard: () => apiRequest<LeaderboardPayload>("/api/leaderboard"),
  postAction: (payload: {
    action: string;
    origin: string;
    path?: string;
    paths?: string[];
  }) =>
    apiRequest<{ status: string }>("/api/actions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  sendBatch: () =>
    apiRequest<{ status: string; processed_groups: number }>("/api/batch/send", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  manualSchedule: (payload: {
    scheduled_at: string;
    origin: string;
    path?: string;
    paths?: string[];
  }) =>
    apiRequest<{ status: string; scheduled: number }>(
      "/api/batch/manual-schedule",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  scheduleQueue: (path: string, scheduled_at: string) =>
    apiRequest<{ status: string }>("/api/queue/schedule", {
      method: "POST",
      body: JSON.stringify({ path, scheduled_at }),
    }),
  unscheduleQueue: (path: string) =>
    apiRequest<{ status: string }>("/api/queue/unschedule", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  restoreTrash: (paths: string[]) =>
    apiRequest<{ status: string; restored: number }>("/api/trash/restore", {
      method: "POST",
      body: JSON.stringify({ paths }),
    }),
  deleteTrash: (paths: string[]) =>
    apiRequest<{ status: string; deleted: number }>("/api/trash/delete", {
      method: "POST",
      body: JSON.stringify({ paths }),
    }),
  resetEvents: () =>
    apiRequest<{ status: string }>("/api/events/reset", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  resetStats: () =>
    apiRequest<{ status: string; message: string }>("/api/stats/reset", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  resetLeaderboard: () =>
    apiRequest<{ status: string; message: string }>("/api/leaderboard/reset", {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
