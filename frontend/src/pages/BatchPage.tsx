import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import MediaGroupCard from "@/components/MediaGroupCard";
import PagePagination from "@/components/PagePagination";
import { ErrorState, LoadingState } from "@/components/PageState";
import ScheduleDateTimePicker from "@/components/ScheduleDateTimePicker";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";

const BatchPage = () => {
  const [page, setPage] = useState(1);
  const [scheduleInputs, setScheduleInputs] = useState<Record<string, string>>({});
  const queryClient = useQueryClient();
  const { t } = useSession();

  const query = useQuery({
    queryKey: ["batch", page],
    queryFn: () => api.getBatch(page),
  });

  const refreshAll = async () => {
    await queryClient.invalidateQueries();
  };

  const actionMutation = useMutation({
    mutationFn: (payload: { action: string; paths: string[] }) =>
      api.postAction({ action: payload.action, origin: "batch", paths: payload.paths }),
    onSuccess: refreshAll,
    onError: (error: Error) => toast.error(error.message),
  });

  const sendMutation = useMutation({
    mutationFn: api.sendBatch,
    onSuccess: refreshAll,
    onError: (error: Error) => toast.error(error.message),
  });

  const scheduleMutation = useMutation({
    mutationFn: (payload: { paths: string[]; scheduled_at: string }) =>
      api.manualSchedule({
        origin: "batch",
        paths: payload.paths,
        scheduled_at: payload.scheduled_at,
      }),
    onSuccess: refreshAll,
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
        <p className="text-sm text-muted-foreground">
          {t("totalItems", { count: query.data.total_items })}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => sendMutation.mutate()}>
            {t("sendBatchNow")}
          </Button>
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            {t("refresh")}
          </Button>
        </div>
      </div>

      {query.data.items.length === 0 ? (
        <LoadingState label={t("noBatch")} />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {query.data.items.map((group) => {
            const groupKey = group.items.map((item) => item.path).join("|");
            return (
              <MediaGroupCard
                key={groupKey}
                group={group}
                scheduleInput={
                  <div className="flex flex-col gap-2 md:flex-row">
                    <ScheduleDateTimePicker
                      value={scheduleInputs[groupKey] ?? ""}
                      onChange={(nextValue) =>
                        setScheduleInputs((current) => ({
                          ...current,
                          [groupKey]: nextValue,
                        }))
                      }
                    />
                    <Button
                      variant="outline"
                      onClick={() =>
                        scheduleMutation.mutate({
                          paths: group.items.map((item) => item.path),
                          scheduled_at: scheduleInputs[groupKey] ?? "",
                        })
                      }
                      disabled={!scheduleInputs[groupKey]}
                    >
                      {t("manualSchedule")}
                    </Button>
                  </div>
                }
                actions={
                  <>
                    <Button
                      size="sm"
                      onClick={() =>
                        actionMutation.mutate({
                          action: "push",
                          paths: group.items.map((item) => item.path),
                        })
                      }
                    >
                      {t("pushNow")}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        actionMutation.mutate({
                          action: "schedule",
                          paths: group.items.map((item) => item.path),
                        })
                      }
                    >
                      {t("schedule")}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() =>
                        actionMutation.mutate({
                          action: "remove_batch",
                          paths: group.items.map((item) => item.path),
                        })
                      }
                    >
                      {t("remove")}
                    </Button>
                  </>
                }
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
