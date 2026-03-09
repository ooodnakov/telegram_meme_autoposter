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

export interface PostsFilters {
  q: string;
  kind: "all" | "image" | "video";
  layout: "all" | "single" | "group";
  source: string;
}

export interface PostsFiltersPayload extends PostsFilters {
  sources: string[];
}

export interface PostsResponse extends PaginatedResponse<MediaGroup> {
  filters: PostsFiltersPayload;
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

export interface JobRuntime {
  can_run: boolean;
  reason?: string | null;
  ocr_enabled?: boolean;
  languages?: string | null;
  tesseract_available?: boolean;
  tesseract_version?: string | null;
  tesseract_error?: string | null;
}

export interface JobRecord {
  name: string;
  title: string;
  description: string;
  status: "idle" | "running" | "paused" | "succeeded" | "failed";
  status_detail?: string | null;
  pause_requested?: boolean;
  current_run_started_at?: string | null;
  current_run_duration_seconds?: number | null;
  current_stats: Record<string, number | string>;
  last_run_started_at?: string | null;
  last_run_finished_at?: string | null;
  last_run_duration_seconds?: number | null;
  last_run_status?: "idle" | "running" | "paused" | "succeeded" | "failed" | null;
  last_run_stats: Record<string, number | string>;
  last_error?: string | null;
  can_run: boolean;
  can_pause?: boolean;
  can_resume?: boolean;
  runtime: JobRuntime;
}

export interface JobsPayload {
  items: JobRecord[];
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
  activity_series: Array<{
    date: string;
    received: number;
    processed: number;
    approved: number;
    rejected: number;
    published: number;
    deliveries: number;
    scheduled: number;
    rescheduled: number;
    unscheduled: number;
    errors: number;
  }>;
  hourly_activity: Array<{
    hour: number;
    approved: number;
    rejected: number;
    published: number;
    decisions: number;
  }>;
  schedule_health: {
    avg_schedule_lead_hours: number;
    avg_schedule_delay_minutes: number;
    scheduled_publish_count: number;
    on_time_publish_rate: number;
  };
  schedule_delay_distribution: Array<{ label: string; count: number }>;
  current_batch_count: number;
  current_scheduled_count: number;
  decision_total_24h: number;
  rejection_rate_24h: number;
  error_rate_24h: number;
  publish_per_approval_24h: number;
  deliveries_per_post_24h: number;
  telegram_channel_analytics?: {
    fetched_at: string;
    expires_at: string;
    channels: Array<{
      peer: string;
      id?: number | null;
      title: string;
      username?: string | null;
      kind: string;
      error?: string;
      period?: {
        start?: string | null;
        end?: string | null;
      };
      summary_metrics: Array<{
        key: string;
        current: number;
        previous: number;
        delta: number;
        delta_pct: number;
      }>;
      ratio_metrics: Array<{
        key: string;
        part: number;
        total: number;
        percentage: number;
      }>;
      graphs: Array<{
        key: string;
        title_key: string;
        error?: string;
        stacked?: boolean;
        percentage?: boolean;
        series?: Array<{
          key: string;
          label: string;
          color?: string | null;
          type: string;
        }>;
        points?: Array<Record<string, string | number | null>>;
      }>;
      recent_posts: Array<{
        message_id: number;
        views: number;
        forwards: number;
        reactions: number;
        link?: string | null;
      }>;
    }>;
  } | null;
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

export type EventsPayload = PaginatedResponse<EventEntry>;

export interface ChannelSettingsPayload {
  selected_chats: string[];
  default_selected_chats: string[];
  valkey_key: string;
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
  getPosts: (page: number, filters?: Partial<PostsFilters>) => {
    const params = new URLSearchParams({ page: String(page) });
    if (filters?.q) {
      params.set("q", filters.q);
    }
    if (filters?.kind && filters.kind !== "all") {
      params.set("kind", filters.kind);
    }
    if (filters?.layout && filters.layout !== "all") {
      params.set("layout", filters.layout);
    }
    if (filters?.source && filters.source !== "all") {
      params.set("source", filters.source);
    }
    return apiRequest<PostsResponse>(`/api/posts?${params.toString()}`);
  },
  getBatch: (page: number) =>
    apiRequest<PaginatedResponse<MediaGroup>>(`/api/batch?page=${page}`),
  getTrash: (page: number) =>
    apiRequest<PaginatedResponse<MediaGroup>>(`/api/trash?page=${page}`),
  getQueue: (page: number) =>
    apiRequest<PaginatedResponse<QueueItem>>(`/api/queue?page=${page}`),
  getEvents: (page: number) =>
    apiRequest<EventsPayload>(`/api/events?page=${page}`),
  getStats: () => apiRequest<StatsPayload>("/api/stats"),
  getJobs: () => apiRequest<JobsPayload>("/api/jobs"),
  getChannelSettings: () =>
    apiRequest<ChannelSettingsPayload>("/api/settings/channels"),
  updateChannelSettings: (selected_chats: string[]) =>
    apiRequest<ChannelSettingsPayload>("/api/settings/channels", {
      method: "POST",
      body: JSON.stringify({ selected_chats }),
    }),
  runJob: (jobName: string) =>
    apiRequest<JobRecord>(`/api/jobs/${jobName}/run`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  pauseJob: (jobName: string) =>
    apiRequest<JobRecord>(`/api/jobs/${jobName}/pause`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  resumeJob: (jobName: string) =>
    apiRequest<JobRecord>(`/api/jobs/${jobName}/resume`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
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
