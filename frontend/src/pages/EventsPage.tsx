import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import DataTable from "@/components/DataTable";
import { ErrorState, LoadingState } from "@/components/PageState";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { formatDisplayDate } from "@/lib/datetime";

const EventsPage = () => {
  const queryClient = useQueryClient();
  const { t } = useSession();

  const query = useQuery({
    queryKey: ["events"],
    queryFn: () => api.getEvents(),
  });

  const resetMutation = useMutation({
    mutationFn: api.resetEvents,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      toast.success(t("resetDone"));
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
          {t("totalItems", { count: query.data.items.length })}
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            {t("refresh")}
          </Button>
          <Button variant="outline" size="sm" onClick={() => resetMutation.mutate()}>
            {t("clearHistory")}
          </Button>
        </div>
      </div>

      <DataTable
        headers={[t("timestamp"), t("action"), t("actor"), t("source"), t("count")]}
        rows={query.data.items.map((event) => [
          formatDisplayDate(event.timestamp),
          `${event.action ?? "—"}${event.origin ? ` · ${event.origin}` : ""}`,
          String(event.actor ?? "—"),
          event.items[0]?.submitter?.source ?? "—",
          event.items.length,
        ])}
        emptyMessage={t("recentEvents")}
      />
    </div>
  );
};

export default EventsPage;
