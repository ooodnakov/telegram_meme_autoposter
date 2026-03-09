import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import JobsPage from "@/pages/JobsPage";

const invalidateQueries = vi.fn();

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    invalidateQueries,
  }),
  useQuery: () => ({
    isLoading: false,
    isError: false,
    data: {
      items: [
        {
          name: "reconcile_scheduled_queue",
          title: "Reconcile scheduled queue",
          description: "Remove scheduled queue entries that no longer have a corresponding object in storage.",
          status: "running",
          status_detail: "Check 2/3: stale.jpg",
          current_run_started_at: "2026-03-08T10:00:00+00:00",
          current_run_duration_seconds: 42,
          current_stats: {
            scheduled_total: 3,
            items_checked: 2,
            missing_objects: 1,
            removed_stale: 1,
          },
          last_run_started_at: null,
          last_run_finished_at: null,
          last_run_duration_seconds: null,
          last_run_status: null,
          last_run_stats: {},
          last_error: null,
          can_run: false,
          can_pause: true,
          can_resume: false,
          runtime: {
            can_run: true,
            progress: {
              current_key: "items_checked",
              total_key: "scheduled_total",
              label: "Checked scheduled items",
              label_key: "checkedScheduledItemsProgress",
            },
            details: [
              {
                label: "Queue source",
                label_key: "jobDetailQueueSource",
                value: "Valkey scheduled_posts + MinIO objects",
                value_key: "jobValueValkeyScheduledMinioObjects",
              },
            ],
          },
        },
      ],
    },
    refetch: vi.fn(),
    error: null,
  }),
  useMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/components/SessionProvider", () => ({
  useSession: () => ({
    t: (key: string, params?: Record<string, string | number>) => {
      if (key === "currentRun") {
        return "Current run";
      }
      if (key === "lastRun") {
        return "Last run";
      }
      if (key === "runningNow") {
        return "Running now";
      }
      if (key === "lastDuration") {
        return "Last duration";
      }
      if (key === "neverRun") {
        return "Never run";
      }
      if (key === "jobRunning") {
        return "Running";
      }
      if (key === "jobStats") {
        return "Job stats";
      }
      if (key === "scheduledQueue") {
        return "Scheduled queue";
      }
      if (key === "checkedScheduledItemsProgress") {
        return "Checked scheduled items";
      }
      if (key === "jobDetailQueueSource") {
        return "Queue source";
      }
      if (key === "jobValueValkeyScheduledMinioObjects") {
        return "Valkey scheduled_posts + MinIO objects";
      }
      if (key === "removedStale") {
        return "Removed stale entries";
      }
      return params ? `${key}:${JSON.stringify(params)}` : key;
    },
  }),
}));

describe("JobsPage", () => {
  it("renders runtime details, generic progress, and fallback stat labels", () => {
    render(<JobsPage />);

    expect(screen.getByText("Reconcile scheduled queue")).toBeInTheDocument();
    expect(screen.getByText("Checked scheduled items")).toBeInTheDocument();
    expect(screen.getByText("2/3")).toBeInTheDocument();
    expect(screen.getByText("Queue source")).toBeInTheDocument();
    expect(
      screen.getByText("Valkey scheduled_posts + MinIO objects"),
    ).toBeInTheDocument();
    expect(screen.getByText("Scheduled queue")).toBeInTheDocument();
    expect(screen.getByText("Removed stale entries")).toBeInTheDocument();
  });
});
