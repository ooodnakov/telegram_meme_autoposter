import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Clock,
  FileText,
  Hand,
  Image,
  Layers,
  LayoutDashboard,
  Lightbulb,
  Trash2,
  Video,
} from "lucide-react";
import { Link } from "react-router-dom";
import BadgeStatus from "@/components/BadgeStatus";
import EventFeed from "@/components/EventFeed";
import { ErrorState, LoadingState } from "@/components/PageState";
import SectionHeader from "@/components/SectionHeader";
import StatCard from "@/components/StatCard";
import { useSession } from "@/components/SessionProvider";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatDisplayDate } from "@/lib/datetime";

function joinInfo(...parts: Array<string | null | undefined>) {
  return parts.filter(Boolean).join(" · ");
}

function SummaryRow({
  label,
  value,
  detail,
  variant,
}: {
  label: string;
  value: ReactNode;
  detail?: string;
  variant: "success" | "warning" | "destructive" | "default" | "primary";
}) {
  return (
    <div className="rounded-lg bg-secondary/50 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm">{label}</span>
        <BadgeStatus variant={variant}>{value}</BadgeStatus>
      </div>
      {detail ? <p className="mt-1 text-xs text-muted-foreground">{detail}</p> : null}
    </div>
  );
}

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
  const mediaReceivedToday = Number(daily.media_received ?? 0);
  const photosProcessedToday = Number(daily.photos_processed ?? 0);
  const videosProcessedToday = Number(daily.videos_processed ?? 0);
  const approvedToday =
    Number(daily.photos_approved ?? 0) + Number(daily.videos_approved ?? 0);
  const rejectedToday =
    Number(daily.photos_rejected ?? 0) + Number(daily.videos_rejected ?? 0);
  const publishedToday = Number(daily.publish_events ?? 0);
  const deliveriesToday = Number(daily.channel_deliveries ?? 0);
  const errorsToday =
    Number(daily.processing_errors ?? 0) +
    Number(daily.storage_errors ?? 0) +
    Number(daily.telegram_errors ?? 0);
  const nextScheduledLabel = formatDisplayDate(query.data.next_scheduled_at);
  const recentEventsSummary = joinInfo(
    `${t("published")}: ${publishedToday}`,
    `${t("decisions")}: ${approvedToday + rejectedToday}`,
    `${t("errors")}: ${errorsToday}`,
  );
  const queueSummary = joinInfo(
    `${t("pendingSuggestions")}: ${query.data.suggestions_count}`,
    `${t("pendingPosts")}: ${query.data.posts_count}`,
    `${t("mediaReceived")}: ${mediaReceivedToday}`,
  );

  return (
    <div className="space-y-6">
      <SectionHeader
        badge={t("dashboard")}
        title={t("dashboard")}
        description={queueSummary}
        icon={LayoutDashboard}
        actions={
          <>
            <Button variant="outline" size="sm" asChild>
              <Link to="/queue">{t("queue")}</Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/swipe-review">{t("swipeReview")}</Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/events">{t("events")}</Link>
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Link to="/suggestions" className="block h-full">
          <StatCard
            title={t("pendingSuggestions")}
            value={query.data.suggestions_count}
            icon={Lightbulb}
            description={joinInfo(
              `${t("approved")}: ${approvedToday}`,
              `${t("rejected")}: ${rejectedToday}`,
            )}
          />
        </Link>
        <Link to="/batch" className="block h-full">
          <StatCard
            title={t("itemsInBatch")}
            value={query.data.batch_count}
            icon={Layers}
            description={joinInfo(
              `${t("published")}: ${publishedToday}`,
              `${t("channelDeliveries")}: ${deliveriesToday}`,
            )}
          />
        </Link>
        <Link to="/queue" className="block h-full">
          <StatCard
            title={t("scheduledPosts")}
            value={query.data.scheduled_count}
            icon={Clock}
            description={
              query.data.next_scheduled_at
                ? `${t("nextPost")}: ${nextScheduledLabel}`
                : t("noQueue")
            }
          />
        </Link>
        <Link to="/posts" className="block h-full">
          <StatCard
            title={t("pendingPosts")}
            value={query.data.posts_count}
            icon={FileText}
            description={joinInfo(
              `${t("itemsInBatch")}: ${query.data.batch_count}`,
              `${t("scheduledPosts")}: ${query.data.scheduled_count}`,
            )}
          />
        </Link>
      </div>

      <Link to="/swipe-review" className="block">
        <div className="glass-card border-primary/25 p-5 transition-colors hover:border-primary/50">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl bg-primary/10 p-3 text-primary">
              <Hand className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-semibold">{t("swipeReview")}</p>
              <p className="text-sm text-muted-foreground">
                {t("swipeReviewDescription")}
              </p>
            </div>
          </div>
        </div>
      </Link>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <StatCard
          title={t("mediaReceived")}
          value={mediaReceivedToday}
          icon={Image}
          description={joinInfo(
            `${t("photosProcessed")}: ${photosProcessedToday}`,
            `${t("videosProcessed")}: ${videosProcessedToday}`,
          )}
        />
        <StatCard
          title={t("videosProcessed")}
          value={videosProcessedToday}
          icon={Video}
          description={joinInfo(
            `${t("approved")}: ${approvedToday}`,
            `${t("rejected")}: ${rejectedToday}`,
          )}
        />
        <StatCard
          title={t("trashItems")}
          value={query.data.trash_count}
          icon={Trash2}
          description={joinInfo(
            `${t("errors")}: ${errorsToday}`,
            `${t("published")}: ${publishedToday}`,
          )}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="glass-card p-5">
          <SectionHeader
            badge={t("events")}
            title={t("recentEvents")}
            description={recentEventsSummary}
            className="mb-4"
            compact
          />
          <div className="space-y-3">
            <EventFeed
              events={recentEvents}
              emptyMessage={t("noEventsYet")}
              variant="compact"
            />
            <div>
              <Link to="/events" className="text-xs text-primary hover:underline">
                {t("events")}
              </Link>
            </div>
          </div>
        </div>

        <div className="glass-card p-5">
          <SectionHeader
            badge={t("dashboard")}
            title={t("operationalKpis")}
            description={queueSummary}
            icon={LayoutDashboard}
            className="mb-4"
            compact
          />
          <div className="space-y-3">
            <SummaryRow
              label={t("itemsInBatch")}
              value={query.data.batch_count}
              variant="primary"
              detail={joinInfo(
                `${t("pendingPosts")}: ${query.data.posts_count}`,
                `${t("published")}: ${publishedToday}`,
              )}
            />
            <SummaryRow
              label={t("scheduledPosts")}
              value={query.data.scheduled_count}
              variant="warning"
              detail={
                query.data.next_scheduled_at
                  ? `${t("nextPost")}: ${nextScheduledLabel}`
                  : t("noQueue")
              }
            />
            <SummaryRow
              label={t("trashItems")}
              value={query.data.trash_count}
              variant="destructive"
              detail={joinInfo(
                `${t("errors")}: ${errorsToday}`,
                `${t("rejected")}: ${rejectedToday}`,
              )}
            />
            <SummaryRow
              label={t("nextPost")}
              value={nextScheduledLabel}
              variant="default"
              detail={joinInfo(
                `${t("channelDeliveries")}: ${deliveriesToday}`,
                `${t("approved")}: ${approvedToday}`,
              )}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;
