import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Hash, Layers3, Send } from "lucide-react";
import { toast } from "sonner";
import BatchGroupCard from "@/components/BatchGroupCard";
import PagePagination from "@/components/PagePagination";
import { ErrorState, LoadingState } from "@/components/PageState";
import SectionHeader from "@/components/SectionHeader";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";

type BatchAction = "push" | "schedule" | "remove_batch";

function BatchSummaryCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Layers3;
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

const getGroupKey = (paths: string[]) => paths.join("|");

const BatchPage = () => {
  const [page, setPage] = useState(1);
  const [scheduleInputs, setScheduleInputs] = useState<Record<string, string>>({});
  const queryClient = useQueryClient();
  const { t } = useSession();

  const refreshBatch = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["batch"] }),
      queryClient.invalidateQueries({ queryKey: ["queue"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["stats"] }),
      queryClient.invalidateQueries({ queryKey: ["events"] }),
    ]);
  };

  const actionMutation = useMutation({
    mutationFn: (payload: { action: BatchAction; paths: string[]; groupKey: string }) =>
      api.postAction({ action: payload.action, origin: "batch", paths: payload.paths }),
    onSuccess: async () => {
      await refreshBatch();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const sendMutation = useMutation({
    mutationFn: api.sendBatch,
    onSuccess: async () => {
      setPage(1);
      await refreshBatch();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const scheduleMutation = useMutation({
    mutationFn: (payload: { groupKey: string; paths: string[]; scheduled_at: string }) =>
      api.manualSchedule({
        origin: "batch",
        paths: payload.paths,
        scheduled_at: payload.scheduled_at,
      }),
    onSuccess: async (_data, variables) => {
      setScheduleInputs((current) => {
        const next = { ...current };
        delete next[variables.groupKey];
        return next;
      });
      await refreshBatch();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const query = useQuery({
    queryKey: ["batch", page],
    queryFn: () => api.getBatch(page),
    placeholderData: (previousData) => previousData,
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
      <SectionHeader
        badge={t("batch")}
        title={t("itemsInBatch")}
        description={`${t("totalItems", { count: query.data.total_items })} · ${t("pageOf", {
          page: query.data.page,
          total: query.data.total_pages,
        })}`}
        icon={Layers3}
        actions={
          <>
            <Button
              size="sm"
              onClick={() => sendMutation.mutate()}
              disabled={sendMutation.isPending || query.data.items.length === 0}
            >
              <Send className="h-4 w-4" />
              {sendMutation.isPending ? t("loading") : t("sendBatchNow")}
            </Button>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
              {t("refresh")}
            </Button>
          </>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <BatchSummaryCard
          icon={Layers3}
          label={t("batchQueue")}
          value={query.data.total_items}
        />
        <BatchSummaryCard
          icon={Hash}
          label={t("count")}
          value={query.data.items.length}
        />
        <BatchSummaryCard
          icon={Send}
          label={t("batch")}
          value={t("pageOf", { page: query.data.page, total: query.data.total_pages })}
        />
      </div>

      {query.isFetching ? <p className="text-xs text-muted-foreground">{t("loading")}</p> : null}

      {query.data.items.length === 0 ? (
        <LoadingState label={t("noBatch")} />
      ) : (
        <div className="space-y-4">
          {query.data.items.map((group) => {
            const groupKey = getGroupKey(group.items.map((item) => item.path));
            const activeAction =
              actionMutation.isPending && actionMutation.variables?.groupKey === groupKey
                ? actionMutation.variables.action
                : null;
            const isSchedulingGroup =
              scheduleMutation.isPending && scheduleMutation.variables?.groupKey === groupKey;

            return (
              <BatchGroupCard
                key={groupKey}
                group={group}
                scheduleValue={scheduleInputs[groupKey] ?? ""}
                onScheduleChange={(nextValue) =>
                  setScheduleInputs((current) => ({
                    ...current,
                    [groupKey]: nextValue,
                  }))
                }
                onManualSchedule={() =>
                  scheduleMutation.mutate({
                    groupKey,
                    paths: group.items.map((item) => item.path),
                    scheduled_at: scheduleInputs[groupKey] ?? "",
                  })
                }
                onAction={(action) =>
                  actionMutation.mutate({
                    action,
                    groupKey,
                    paths: group.items.map((item) => item.path),
                  })
                }
                activeAction={activeAction}
                isScheduling={isSchedulingGroup}
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

export default BatchPage;
