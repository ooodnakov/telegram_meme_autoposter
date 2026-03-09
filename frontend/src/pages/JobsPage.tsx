import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, ScanSearch, Workflow } from "lucide-react";
import { toast } from "sonner";
import BadgeStatus from "@/components/BadgeStatus";
import { ErrorState, LoadingState } from "@/components/PageState";
import SectionHeader from "@/components/SectionHeader";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useSession } from "@/components/SessionProvider";
import { api, type JobRecord } from "@/lib/api";
import { formatDisplayDate } from "@/lib/datetime";
import type { TranslationKey } from "@/lib/i18n";

const statLabels: Partial<Record<string, TranslationKey>> = {
  images_total: "imagesTotal",
  images_missing_ocr: "imagesMissingOcr",
  images_ocred: "imagesOcred",
  images_with_text: "imagesWithText",
  images_without_text: "imagesWithoutText",
  images_failed: "errors",
  scheduled_total: "scheduledQueue",
  failed: "errors",
};

function startCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatDuration(seconds?: number | null): string {
  if (seconds == null) {
    return "—";
  }
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  if (seconds < 3600) {
    return `${(seconds / 60).toFixed(1)}m`;
  }
  return `${(seconds / 3600).toFixed(1)}h`;
}

function formatMetric(value: number | string | undefined): string {
  if (typeof value === "number") {
    return new Intl.NumberFormat().format(value);
  }
  if (typeof value === "string") {
    return value;
  }
  return "0";
}

function formatDetailValue(value: string | number | boolean | null | undefined): string {
  if (typeof value === "number") {
    return new Intl.NumberFormat().format(value);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return "—";
}

function metricLabel(key: string, t: (key: TranslationKey, values?: Record<string, string | number>) => string): string {
  const translationKey = statLabels[key];
  if (translationKey) {
    return t(translationKey);
  }
  return startCase(key);
}

function resolveProgress(job: JobRecord, stats: Record<string, number | string>) {
  const progress = job.runtime.progress;
  if (!progress) {
    return null;
  }

  const total = Number(stats[progress.total_key] ?? 0);
  const current = Number(stats[progress.current_key] ?? 0);
  if (!Number.isFinite(total) || !Number.isFinite(current) || total <= 0) {
    return null;
  }

  return {
    label: progress.label ?? "Progress",
    current,
    total,
    value: Math.min(100, (current / total) * 100),
  };
}

function statusVariant(status: JobRecord["status"]): "default" | "primary" | "success" | "destructive" {
  if (status === "running") {
    return "primary";
  }
  if (status === "paused") {
    return "default";
  }
  if (status === "succeeded") {
    return "success";
  }
  if (status === "failed") {
    return "destructive";
  }
  return "default";
}

function statusLabel(status: JobRecord["status"]): TranslationKey {
  if (status === "running") {
    return "jobRunning";
  }
  if (status === "paused") {
    return "jobPausedStatus";
  }
  if (status === "succeeded") {
    return "jobSucceeded";
  }
  if (status === "failed") {
    return "jobFailed";
  }
  return "jobIdle";
}

function statusTone(
  status: JobRecord["status"],
): "primary" | "success" | "warning" | "destructive" | "neutral" {
  if (status === "running") {
    return "primary";
  }
  if (status === "paused") {
    return "warning";
  }
  if (status === "succeeded") {
    return "success";
  }
  if (status === "failed") {
    return "destructive";
  }
  return "neutral";
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-secondary/40 px-3 py-2.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}

const JobsPage = () => {
  const queryClient = useQueryClient();
  const { t } = useSession();

  const query = useQuery({
    queryKey: ["jobs"],
    queryFn: api.getJobs,
    refetchInterval: (queryState) =>
      queryState.state.data?.items.some(
        (item) => item.status === "running" || item.status === "paused",
      )
        ? 3000
        : 15000,
  });

  const runMutation = useMutation({
    mutationFn: api.runJob,
    onSuccess: async () => {
      toast.success(t("jobStarted"));
      await queryClient.invalidateQueries();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const pauseMutation = useMutation({
    mutationFn: api.pauseJob,
    onSuccess: async () => {
      toast.success(t("jobPaused"));
      await queryClient.invalidateQueries();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const resumeMutation = useMutation({
    mutationFn: api.resumeJob,
    onSuccess: async () => {
      toast.success(t("jobResumed"));
      await queryClient.invalidateQueries();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (query.isLoading) {
    return <LoadingState label={t("loading")} />;
  }

  if (query.isError || !query.data) {
    return (
      <ErrorState
        message={t("errorPrefix", { message: query.error?.message ?? "Unknown error" })}
        retryLabel={t("retry")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  if (query.data.items.length === 0) {
    return <LoadingState label={t("noJobs")} />;
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        badge={t("jobs")}
        title={t("jobs")}
        description={t("jobsLiveHint")}
        icon={Workflow}
        actions={
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            {t("refresh")}
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {query.data.items.map((job) => {
          const stats =
            job.status === "running" || job.status === "paused"
              ? job.current_stats
              : job.last_run_stats;
          const progress = resolveProgress(job, stats);
          const runtimeDetails = job.runtime.details ?? [];
          const statEntries = Object.entries(stats);
          const isMutating = runMutation.isPending || pauseMutation.isPending || resumeMutation.isPending;
          const actionButton = job.can_pause ? (
            <Button
              size="sm"
              variant="outline"
              className="gap-2"
              disabled={isMutating}
              onClick={() => pauseMutation.mutate(job.name)}
            >
              <Pause className="h-4 w-4" />
              {t("pauseJob")}
            </Button>
          ) : job.can_resume ? (
            <Button
              size="sm"
              className="gap-2"
              disabled={isMutating}
              onClick={() => resumeMutation.mutate(job.name)}
            >
              <Play className="h-4 w-4" />
              {t("resumeJob")}
            </Button>
          ) : (
            <Button
              size="sm"
              className="gap-2"
              disabled={!job.can_run || isMutating}
              onClick={() => runMutation.mutate(job.name)}
            >
              <Play className="h-4 w-4" />
              {t("runJob")}
            </Button>
          );

          return (
            <section key={job.name} className="glass-card space-y-5 p-5">
              <SectionHeader
                as="div"
                badge={t(statusLabel(job.status))}
                title={job.title}
                description={job.description}
                icon={ScanSearch}
                tone={statusTone(job.status)}
                compact
                actions={actionButton}
              />

              <BadgeStatus variant={statusVariant(job.status)}>
                {t(statusLabel(job.status))}
              </BadgeStatus>

              {job.runtime.reason ? (
                <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
                  {job.runtime.reason}
                </div>
              ) : null}

              {(job.status === "running" || job.status === "paused") && progress ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{progress.label}</span>
                    <span className="font-medium">
                      {progress.current}/{progress.total}
                    </span>
                  </div>
                  <Progress value={progress.value} />
                </div>
              ) : null}

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <InfoRow
                  label={t("runningNow")}
                  value={formatDuration(job.current_run_duration_seconds)}
                />
                <InfoRow
                  label={t("lastDuration")}
                  value={formatDuration(job.last_run_duration_seconds)}
                />
                <InfoRow
                  label={t("currentRun")}
                  value={job.current_run_started_at ? formatDisplayDate(job.current_run_started_at) : "—"}
                />
                <InfoRow
                  label={t("lastRun")}
                  value={job.last_run_finished_at ? formatDisplayDate(job.last_run_finished_at) : t("neverRun")}
                />
                {runtimeDetails.map((detail, index) => (
                  <InfoRow
                    key={`${detail.label}-${index}`}
                    label={detail.label}
                    value={formatDetailValue(detail.value)}
                  />
                ))}
              </div>

              {job.status_detail ? (
                <div className="rounded-lg bg-secondary/40 px-3 py-2 text-sm text-muted-foreground">
                  {job.status_detail}
                </div>
              ) : null}

              {statEntries.length > 0 ? (
                <div className="space-y-3">
                  <div className="text-sm font-semibold">{t("jobStats")}</div>
                  <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                    {statEntries.map(([key, value]) => (
                      <div key={key} className="rounded-xl border border-border/60 bg-secondary/25 px-3 py-3">
                        <div className="text-xs uppercase tracking-wide text-muted-foreground">
                          {metricLabel(key, t)}
                        </div>
                        <div className="mt-1 text-lg font-semibold">
                          {formatMetric(value)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {job.last_error ? (
                <div className="rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                  <div className="font-medium">{t("lastError")}</div>
                  <div className="mt-1 break-words">{job.last_error}</div>
                </div>
              ) : null}
            </section>
          );
        })}
      </div>
    </div>
  );
};

export default JobsPage;
