import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import DataTable from "@/components/DataTable";
import ClickableImage from "@/components/ClickableImage";
import PagePagination from "@/components/PagePagination";
import { ErrorState, LoadingState } from "@/components/PageState";
import ScheduleDateTimePicker from "@/components/ScheduleDateTimePicker";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import {
  formatDateTimeForApi,
  formatDisplayDate,
  parseDateTimeValue,
} from "@/lib/datetime";

const QueuePage = () => {
  const [page, setPage] = useState(1);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const queryClient = useQueryClient();
  const { t } = useSession();

  const query = useQuery({
    queryKey: ["queue", page],
    queryFn: () => api.getQueue(page),
  });

  const scheduleMutation = useMutation({
    mutationFn: (payload: { path: string; scheduled_at: string }) =>
      api.scheduleQueue(payload.path, payload.scheduled_at),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const unscheduleMutation = useMutation({
    mutationFn: api.unscheduleQueue,
    onSuccess: async () => {
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {t("totalItems", { count: query.data.total_items })}
        </p>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
          {t("refresh")}
        </Button>
      </div>

      <DataTable
        headers={[t("file"), t("caption"), t("scheduledAt"), t("preview"), t("actions")]}
        rows={query.data.items.map((item) => [
          <span className="font-mono text-xs text-muted-foreground">{item.path}</span>,
          item.caption || "—",
          <div className="flex min-w-[240px] items-center gap-2">
            <ScheduleDateTimePicker
              value={drafts[item.path] ?? item.scheduled_at}
              onChange={(nextValue) =>
                setDrafts((current) => ({
                  ...current,
                  [item.path]: nextValue,
                }))
              }
            />
            <Button
              size="sm"
              onClick={() =>
                scheduleMutation.mutate({
                  path: item.path,
                  scheduled_at:
                    drafts[item.path] ??
                    formatDateTimeForApi(parseDateTimeValue(item.scheduled_at) ?? new Date()),
                })
              }
            >
              {t("save")}
            </Button>
          </div>,
          <div className="min-w-[180px]">
            {item.kind === "image" ? (
              <ClickableImage
                src={item.url}
                alt={item.caption ?? item.name}
                className="max-h-40 rounded-lg object-contain"
              />
            ) : (
              <video
                className="max-h-40 rounded-lg"
                controls
                preload="metadata"
                src={item.url}
              />
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              {formatDisplayDate(item.scheduled_at)}
            </p>
          </div>,
          <Button
            size="sm"
            variant="destructive"
            onClick={() => unscheduleMutation.mutate(item.path)}
          >
            {t("unschedule")}
          </Button>,
        ])}
        emptyMessage={t("noQueue")}
      />

      <PagePagination
        page={query.data.page}
        totalPages={query.data.total_pages}
        onPageChange={setPage}
      />
    </div>
  );
};

export default QueuePage;
