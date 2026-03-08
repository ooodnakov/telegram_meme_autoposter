import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, Image, Inbox, Video, XCircle } from "lucide-react";
import { toast } from "sonner";
import { ErrorState, LoadingState } from "@/components/PageState";
import StatCard from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";

const StatsPage = () => {
  const queryClient = useQueryClient();
  const { t } = useSession();

  const query = useQuery({
    queryKey: ["stats"],
    queryFn: api.getStats,
  });

  const resetMutation = useMutation({
    mutationFn: api.resetStats,
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

  const daily = query.data.daily;
  const histogram = query.data.processing_histogram;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard title={t("mediaReceived")} value={Number(daily.media_received ?? 0)} icon={Inbox} />
        <StatCard title={t("photosProcessed")} value={Number(daily.photos_processed ?? 0)} icon={Image} />
        <StatCard title={t("videosProcessed")} value={Number(daily.videos_processed ?? 0)} icon={Video} />
        <StatCard title={t("photosApproved")} value={Number(daily.photos_approved ?? 0)} icon={CheckCircle} />
        <StatCard title={t("videosApproved")} value={Number(daily.videos_approved ?? 0)} icon={CheckCircle} />
        <StatCard title={t("photosRejected")} value={Number(daily.photos_rejected ?? 0)} icon={XCircle} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="glass-card p-6">
          <h3 className="mb-4 text-sm font-semibold">{t("analytics")}</h3>
          <div className="space-y-4">
            {Object.entries(histogram).map(([kind, buckets]) => (
              <div key={kind} className="space-y-2">
                <p className="text-sm font-medium capitalize">{kind}</p>
                {buckets.map((bucket) => {
                  const maxCount = Math.max(
                    1,
                    ...buckets.map((entry) => entry.count),
                  );
                  return (
                    <div key={bucket.label}>
                      <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                        <span>{bucket.label}</span>
                        <span>{bucket.count}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${(bucket.count / maxCount) * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card p-6 space-y-4">
          <h3 className="text-sm font-semibold">{t("dashboard")}</h3>
          <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
            <span className="text-sm">Approval 24h</span>
            <span className="font-medium">{query.data.approval_24h.toFixed(1)}%</span>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
            <span className="text-sm">Approval total</span>
            <span className="font-medium">{query.data.approval_total.toFixed(1)}%</span>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
            <span className="text-sm">Success 24h</span>
            <span className="font-medium">{query.data.success_24h.toFixed(1)}%</span>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
            <span className="text-sm">Daily errors</span>
            <span className="font-medium">{query.data.daily_errors}</span>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
            <span className="text-sm">Busiest hour</span>
            <span className="font-medium">
              {query.data.busiest_hour === null ? "—" : `${query.data.busiest_hour}:00`}
            </span>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <Button variant="outline" onClick={() => resetMutation.mutate()}>
          {t("resetStats")}
        </Button>
      </div>
    </div>
  );
};

export default StatsPage;
