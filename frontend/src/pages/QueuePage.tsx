import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, Hash, Layers3 } from "lucide-react";
import { toast } from "sonner";
import PagePagination from "@/components/PagePagination";
import { ErrorState, LoadingState } from "@/components/PageState";
import QueueItemCard from "@/components/QueueItemCard";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api, type QueueItem } from "@/lib/api";
import { formatDateTimeForApi, parseDateTimeValue } from "@/lib/datetime";

function QueueSummaryCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Clock3;
  label: string;
  value: string | number;
}) {
  return (
    <div className="glass-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.24em] text-muted-foreground">
            {label}
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{value}</p>
        </div>
        <div className="rounded-xl bg-primary/10 p-2 text-primary">
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}

const QueuePage = () => {
  const [page, setPage] = useState(1);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const queryClient = useQueryClient();
  const { t } = useSession();

  const refreshQueue = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["queue"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  };

  const getDraftValue = (item: QueueItem) => drafts[item.path] ?? item.scheduled_at;

  const query = useQuery({
    queryKey: ["queue", page],
    queryFn: () => api.getQueue(page),
    placeholderData: (previousData) => previousData,
  });

  const scheduleMutation = useMutation({
    mutationFn: (payload: { path: string; scheduled_at: string }) =>
      api.scheduleQueue(payload.path, payload.scheduled_at),
    onSuccess: async (_data, variables) => {
      setDrafts((current) => {
        const next = { ...current };
        delete next[variables.path];
        return next;
      });
      await refreshQueue();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const unscheduleMutation = useMutation({
    mutationFn: api.unscheduleQueue,
    onSuccess: async (_data, path) => {
      setDrafts((current) => {
        if (!(path in current)) {
          return current;
        }
        const next = { ...current };
        delete next[path];
        return next;
      });
      await refreshQueue();
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            {t("totalItems", { count: query.data.total_items })}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("pageOf", { page: query.data.page, total: query.data.total_pages })}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
          {t("refresh")}
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <QueueSummaryCard
          icon={Layers3}
          label={t("scheduledPosts")}
          value={query.data.total_items}
        />
        <QueueSummaryCard
          icon={Clock3}
          label={t("count")}
          value={query.data.items.length}
        />
        <QueueSummaryCard
          icon={Hash}
          label={t("queue")}
          value={t("pageOf", { page: query.data.page, total: query.data.total_pages })}
        />
      </div>

      {query.isFetching ? <p className="text-xs text-muted-foreground">{t("loading")}</p> : null}

      {query.data.items.length === 0 ? (
        <LoadingState label={t("noQueue")} />
      ) : (
        <div className="space-y-4">
          {query.data.items.map((item) => {
            const draftValue = getDraftValue(item);
            const isSavingItem =
              scheduleMutation.isPending && scheduleMutation.variables?.path === item.path;
            const isUnschedulingItem =
              unscheduleMutation.isPending && unscheduleMutation.variables === item.path;

            return (
              <QueueItemCard
                key={item.path}
                item={item}
                draftValue={draftValue}
                onDraftChange={(nextValue) =>
                  setDrafts((current) => ({
                    ...current,
                    [item.path]: nextValue,
                  }))
                }
                onSave={() =>
                  scheduleMutation.mutate({
                    path: item.path,
                    scheduled_at:
                      draftValue ??
                      formatDateTimeForApi(parseDateTimeValue(item.scheduled_at) ?? new Date()),
                  })
                }
                onUnschedule={() => unscheduleMutation.mutate(item.path)}
                isSaving={isSavingItem}
                isUnscheduling={isUnschedulingItem}
              />
            );
          })}
        </div>
      )}

      <PagePagination
        page={query.data.page}
        totalPages={query.data.total_pages}
        onPageChange={setPage}
      />
    </div>
  );
};

export default QueuePage;
