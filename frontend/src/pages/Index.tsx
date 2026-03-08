import { useQuery } from "@tanstack/react-query";
import { Activity, Clock, FileText, Image, Layers, Lightbulb, Trash2, Video } from "lucide-react";
import { Link } from "react-router-dom";
import BadgeStatus from "@/components/BadgeStatus";
import { ErrorState, LoadingState } from "@/components/PageState";
import StatCard from "@/components/StatCard";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { formatDisplayDate } from "@/lib/datetime";

const DashboardPage = () => {
  const { t } = useSession();
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.getDashboard,
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

  const { daily, recent_events: recentEvents } = query.data;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Link to="/suggestions">
          <StatCard
            title={t("pendingSuggestions")}
            value={query.data.suggestions_count}
            icon={Lightbulb}
          />
        </Link>
        <Link to="/batch">
          <StatCard title={t("itemsInBatch")} value={query.data.batch_count} icon={Layers} />
        </Link>
        <Link to="/queue">
          <StatCard
            title={t("scheduledPosts")}
            value={query.data.scheduled_count}
            icon={Clock}
            description={
              query.data.next_scheduled_at
                ? formatDisplayDate(query.data.next_scheduled_at)
                : undefined
            }
          />
        </Link>
        <Link to="/posts">
          <StatCard title={t("pendingPosts")} value={query.data.posts_count} icon={FileText} />
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <StatCard
          title={t("mediaReceived")}
          value={Number(daily.media_received ?? 0)}
          icon={Image}
        />
        <StatCard
          title={t("videosProcessed")}
          value={Number(daily.videos_processed ?? 0)}
          icon={Video}
        />
        <StatCard
          title={t("trashItems")}
          value={query.data.trash_count}
          icon={Trash2}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="glass-card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">{t("recentEvents")}</h3>
            <Link to="/events" className="text-xs text-primary hover:underline">
              {t("events")}
            </Link>
          </div>
          <div className="space-y-3">
            {recentEvents.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noPosts")}</p>
            ) : (
              recentEvents.map((event, index) => (
                <div key={`${event.timestamp}-${index}`} className="flex gap-3">
                  <div className="mt-1">
                    <Activity className="h-4 w-4 text-primary" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">
                      {event.action} {event.origin ? `· ${event.origin}` : ""}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatDisplayDate(event.timestamp)}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="glass-card p-5">
          <h3 className="mb-4 text-sm font-semibold">{t("dashboard")}</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
              <span className="text-sm">{t("itemsInBatch")}</span>
              <BadgeStatus variant="primary">{query.data.batch_count}</BadgeStatus>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
              <span className="text-sm">{t("scheduledPosts")}</span>
              <BadgeStatus variant="warning">{query.data.scheduled_count}</BadgeStatus>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
              <span className="text-sm">{t("trashItems")}</span>
              <BadgeStatus variant="destructive">{query.data.trash_count}</BadgeStatus>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
              <span className="text-sm">{t("nextPost")}</span>
              <BadgeStatus variant="default">
                {formatDisplayDate(query.data.next_scheduled_at)}
              </BadgeStatus>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;
