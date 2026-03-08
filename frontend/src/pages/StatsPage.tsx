import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Gauge,
  Inbox,
  Layers3,
  RadioTower,
  Sparkles,
  Send,
  ShieldCheck,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";
import { ErrorState, LoadingState } from "@/components/PageState";
import StatCard from "@/components/StatCard";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { formatDisplayDate } from "@/lib/datetime";
import type { TranslationKey } from "@/lib/i18n";

function sumMetric<T extends Record<string, number | string>>(
  items: T[],
  key: keyof T,
): number {
  return items.reduce((total, item) => total + Number(item[key] ?? 0), 0);
}

function percentDelta(current: number, previous: number): number {
  if (previous === 0) {
    return current === 0 ? 0 : 100;
  }
  return ((current - previous) / previous) * 100;
}

function formatShortDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function formatHourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

function formatSeconds(value: number): string {
  return `${value.toFixed(2)}s`;
}

function formatHours(value: number): string {
  return `${value.toFixed(1)}h`;
}

function formatMinutes(value: number): string {
  return `${value.toFixed(1)}m`;
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function formatMetricValue(value: number): string {
  if (Number.isInteger(value)) {
    return formatNumber(value);
  }
  return value >= 100 ? formatNumber(Math.round(value)) : value.toFixed(1);
}

function truncateLabel(value: string, size = 16): string {
  return value.length <= size ? value : `${value.slice(0, size - 1)}…`;
}

const fallbackChartColors = [
  "hsl(var(--chart-1))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
  "hsl(var(--chart-5))",
];

const telegramGraphPalettes: Record<string, string[]> = {
  followers: ["#38bdf8", "#0ea5e9", "#0369a1"],
  interactions: ["#f59e0b", "#ef4444", "#ec4899"],
  top_hours: ["#22c55e", "#14b8a6", "#06b6d4"],
  views_by_source: ["#8b5cf6", "#ec4899", "#f97316", "#eab308"],
  members: ["#10b981", "#06b6d4", "#3b82f6"],
  messages: ["#f97316", "#ef4444", "#f43f5e"],
  weekdays: ["#8b5cf6", "#6366f1", "#3b82f6"],
};

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-secondary/40 px-3 py-2.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}

function normalizeTelegramColor(color?: string | null): string | null {
  if (!color) {
    return null;
  }
  const compact = color.replace(/\s+/g, "");
  const hexMatch = compact.match(/#(?:[0-9a-fA-F]{3,8})/);
  const candidate = hexMatch ? hexMatch[0] : compact;
  const normalized = candidate.toLowerCase();
  if (
    normalized === "#000" ||
    normalized === "#000000" ||
    normalized === "black" ||
    normalized === "rgb(0,0,0)" ||
    normalized === "rgba(0,0,0,1)"
  ) {
    return null;
  }
  return candidate;
}

function resolveTelegramSeriesColor(
  graphKey: string,
  color: string | null | undefined,
  index: number,
): string {
  return (
    normalizeTelegramColor(color) ??
    telegramGraphPalettes[graphKey]?.[index % telegramGraphPalettes[graphKey].length] ??
    fallbackChartColors[index % fallbackChartColors.length]
  );
}

function SectionCard({
  value,
  title,
  description,
  children,
}: {
  value: string;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <AccordionItem value={value} className="glass-card overflow-hidden border-none px-6">
      <AccordionTrigger className="py-5 text-left hover:no-underline">
        <div className="min-w-0">
          <div className="text-sm font-semibold">{title}</div>
          {description ? <div className="mt-1 text-xs text-muted-foreground">{description}</div> : null}
        </div>
      </AccordionTrigger>
      <AccordionContent className="pb-6 pt-1">{children}</AccordionContent>
    </AccordionItem>
  );
}

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

  const {
    activity_series: activitySeries,
    approval_24h: approval24h,
    approval_total: approvalTotal,
    current_batch_count: currentBatchCount,
    current_scheduled_count: currentScheduledCount,
    daily,
    daily_errors: dailyErrors,
    daily_post_counts: dailyPostCounts,
    deliveries_per_post_24h: deliveriesPerPost,
    error_rate_24h: errorRate24h,
    hourly_activity: hourlyActivity,
    performance,
    processing_histogram: histogram,
    publish_per_approval_24h: publishPerApproval,
    rejection_rate_24h: rejectionRate24h,
    schedule_delay_distribution: scheduleDelayDistribution,
    schedule_health: scheduleHealth,
    source_acceptance: rawSourceAcceptance,
    success_24h: success24h,
    total_errors: totalErrors,
  } = query.data;

  const sourceAcceptance = rawSourceAcceptance.map((entry) => ({
    source: String(entry.source ?? t("unknown")),
    acceptance_rate: Number(entry.acceptance_rate ?? 0),
    submissions: Number(entry.submissions ?? 0),
    approved: Number(entry.approved ?? 0),
    rejected: Number(entry.rejected ?? 0),
  }));

  const currentWindow = activitySeries.slice(-7);
  const previousWindow = activitySeries.slice(-14, -7);
  const receivedTrend = percentDelta(
    sumMetric(currentWindow, "received"),
    sumMetric(previousWindow, "received"),
  );
  const approvedTrend = percentDelta(
    sumMetric(currentWindow, "approved"),
    sumMetric(previousWindow, "approved"),
  );
  const publishedTrend = percentDelta(
    sumMetric(currentWindow, "published"),
    sumMetric(previousWindow, "published"),
  );
  const currentApprovalWindow =
    (sumMetric(currentWindow, "approved") / Math.max(1, sumMetric(currentWindow, "processed"))) *
    100;
  const previousApprovalWindow =
    (sumMetric(previousWindow, "approved") / Math.max(1, sumMetric(previousWindow, "processed"))) *
    100;
  const currentSuccessWindow =
    ((sumMetric(currentWindow, "received") - sumMetric(currentWindow, "errors")) /
      Math.max(1, sumMetric(currentWindow, "received"))) *
    100;
  const previousSuccessWindow =
    ((sumMetric(previousWindow, "received") - sumMetric(previousWindow, "errors")) /
      Math.max(1, sumMetric(previousWindow, "received"))) *
    100;
  const queuePressure = currentBatchCount + currentScheduledCount;
  const published14d = dailyPostCounts.reduce((total, item) => total + item.count, 0);
  const busiestHourLabel =
    query.data.busiest_hour === null ? "—" : formatHourLabel(query.data.busiest_hour);

  const activityChartConfig = {
    received: { label: t("mediaReceived"), color: "hsl(var(--chart-1))" },
    approved: { label: t("approved"), color: "hsl(var(--chart-2))" },
    published: { label: t("publications"), color: "hsl(var(--chart-3))" },
    errors: { label: t("errors"), color: "hsl(var(--destructive))" },
  };

  const hourlyChartConfig = {
    approved: { label: t("approvals"), color: "hsl(var(--chart-2))" },
    rejected: { label: t("rejected"), color: "hsl(var(--chart-5))" },
    published: { label: t("publications"), color: "hsl(var(--chart-1))" },
  };

  const sourceChartConfig = {
    acceptance_rate: { label: t("acceptanceRate"), color: "hsl(var(--chart-4))" },
  };
  const telegramChannelAnalytics = query.data.telegram_channel_analytics;
  const telegramMetricLabels: Record<string, TranslationKey> = {
    followers: "followers",
    viewsPerPost: "viewsPerPost",
    sharesPerPost: "sharesPerPost",
    reactionsPerPost: "reactionsPerPost",
    enabledNotifications: "enabledNotifications",
    members: "members",
    messages: "messagesMetric",
    viewers: "viewers",
    posters: "posters",
  };

  return (
    <div className="space-y-6">
      <Accordion
        type="multiple"
        defaultValue={[
          "telegram",
          "overview",
          "activity",
          "operations",
          "sources",
        ]}
        className="space-y-6"
      >
        <SectionCard
          value="telegram"
          title={t("telegramAnalytics")}
          description={
            telegramChannelAnalytics
              ? `${t("telegramAnalyticsCached")} · ${formatDisplayDate(telegramChannelAnalytics.fetched_at)}`
              : t("telegramAnalyticsCached")
          }
        >
          {!telegramChannelAnalytics || telegramChannelAnalytics.channels.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("telegramAnalyticsUnavailable")}</p>
          ) : (
            <div className="space-y-6">
              {telegramChannelAnalytics.channels.map((channel) => (
                <div
                  key={channel.peer}
                  className="rounded-2xl border border-sky-400/20 bg-gradient-to-br from-sky-500/8 via-cyan-500/6 to-transparent p-5"
                >
                  <div className="mb-4 flex flex-col gap-1">
                    <h4 className="text-base font-semibold">{channel.title}</h4>
                    <p className="text-xs text-sky-100/70">
                      {channel.username ? `@${channel.username}` : channel.peer}
                    </p>
                    <p className="text-xs text-sky-100/60">
                      {telegramChannelAnalytics
                        ? `${t("cacheExpiresAt")}: ${formatDisplayDate(telegramChannelAnalytics.expires_at)}`
                        : null}
                    </p>
                    {channel.period?.start || channel.period?.end ? (
                      <p className="text-xs text-sky-100/60">
                        {t("telegramPeriod")}: {formatDisplayDate(channel.period?.start)} -{" "}
                        {formatDisplayDate(channel.period?.end)}
                      </p>
                    ) : null}
                  </div>

                  {channel.error ? (
                    <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                      {t("telegramFetchError")}: {channel.error}
                    </div>
                  ) : (
                    <div className="space-y-5">
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
                        {channel.summary_metrics.map((metric, index) => {
                          const metricLabel = telegramMetricLabels[metric.key] ?? "unknown";
                          const accent = resolveTelegramSeriesColor("followers", undefined, index);
                          return (
                            <div
                              key={metric.key}
                              className="rounded-2xl border border-white/8 p-[1px]"
                              style={{
                                background: `linear-gradient(135deg, ${accent}, transparent 70%)`,
                              }}
                            >
                              <div className="rounded-[15px] bg-background/85">
                                <StatCard
                                  title={t(metricLabel)}
                                  value={formatMetricValue(metric.current)}
                                  icon={RadioTower}
                                  description={formatMetricValue(metric.previous)}
                                  trend={{
                                    value: Number(metric.delta_pct.toFixed(1)),
                                    positive: metric.delta >= 0,
                                  }}
                                />
                              </div>
                            </div>
                          );
                        })}
                        {channel.ratio_metrics.map((metric, index) => {
                          const metricLabel = telegramMetricLabels[metric.key] ?? "unknown";
                          const accent = resolveTelegramSeriesColor("interactions", undefined, index);
                          return (
                            <div
                              key={metric.key}
                              className="rounded-2xl border border-white/8 p-[1px]"
                              style={{
                                background: `linear-gradient(135deg, ${accent}, transparent 70%)`,
                              }}
                            >
                              <div className="rounded-[15px] bg-background/85">
                                <StatCard
                                  title={t(metricLabel)}
                                  value={formatPercent(metric.percentage)}
                                  icon={Sparkles}
                                  description={`${formatMetricValue(metric.part)} / ${formatMetricValue(metric.total)}`}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {channel.graphs.length > 0 ? (
                        <div className="grid gap-4 xl:grid-cols-2">
                          {channel.graphs.map((graph) => {
                            const series = graph.series ?? [];
                            const points = graph.points ?? [];
                            const seriesWithColors = series.map((item, index) => ({
                              ...item,
                              resolvedColor: resolveTelegramSeriesColor(
                                graph.key,
                                item.color,
                                index,
                              ),
                            }));
                            const graphConfig = Object.fromEntries(
                              seriesWithColors.map((item) => [
                                item.key,
                                {
                                  label: item.label,
                                  color: item.resolvedColor,
                                },
                              ]),
                            );
                            return (
                              <div
                                key={graph.key}
                                className="rounded-xl border border-white/8 bg-background/55 p-4"
                              >
                                <div className="mb-3">
                                  <h5 className="text-sm font-medium text-sky-100">
                                    {t(graph.title_key as TranslationKey)}
                                  </h5>
                                  {graph.error ? (
                                    <p className="text-xs text-muted-foreground">{graph.error}</p>
                                  ) : null}
                                </div>
                                {points.length === 0 || series.length === 0 ? (
                                  <p className="text-sm text-muted-foreground">{t("unknown")}</p>
                                ) : (
                                  <ChartContainer
                                    config={graphConfig}
                                    className="h-[260px] w-full aspect-auto"
                                  >
                                    <ComposedChart data={points}>
                                      <CartesianGrid vertical={false} />
                                      <XAxis dataKey="label" minTickGap={24} />
                                      <YAxis
                                        allowDecimals={!graph.percentage}
                                        tickFormatter={(value) =>
                                          graph.percentage && typeof value === "number"
                                            ? `${value}%`
                                            : String(value)
                                        }
                                      />
                                      <ChartTooltip content={<ChartTooltipContent />} />
                                      <ChartLegend content={<ChartLegendContent />} />
                                      {seriesWithColors.map((item) =>
                                        item.type === "bar" ? (
                                          <Bar
                                            key={item.key}
                                            dataKey={item.key}
                                            fill={item.resolvedColor}
                                            stackId={graph.stacked ? graph.key : undefined}
                                            radius={[4, 4, 0, 0]}
                                          />
                                        ) : (
                                          <Line
                                            key={item.key}
                                            type="monotone"
                                            dataKey={item.key}
                                            stroke={item.resolvedColor}
                                            strokeWidth={2.5}
                                            dot={false}
                                          />
                                        ),
                                      )}
                                    </ComposedChart>
                                  </ChartContainer>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : null}

                      <div className="rounded-xl border border-white/8 bg-background/55 p-4">
                        <div className="mb-3">
                          <h5 className="text-sm font-medium text-sky-100">{t("recentTopPosts")}</h5>
                        </div>
                        {channel.recent_posts.length === 0 ? (
                          <p className="text-sm text-muted-foreground">{t("noRecentTopPosts")}</p>
                        ) : (
                          <div className="space-y-2">
                            {channel.recent_posts.map((post, index) => {
                              const accent = resolveTelegramSeriesColor("views_by_source", undefined, index);
                              return (
                                <div
                                  key={post.message_id}
                                  className="flex items-center justify-between rounded-lg border border-white/6 px-3 py-2"
                                  style={{
                                    background: `linear-gradient(90deg, ${accent}22, transparent 65%)`,
                                  }}
                                >
                                  <div className="min-w-0">
                                    {post.link ? (
                                      <a
                                        href={post.link}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-sm font-medium text-sky-300 hover:underline"
                                      >
                                        #{post.message_id}
                                      </a>
                                    ) : (
                                      <span className="text-sm font-medium">#{post.message_id}</span>
                                    )}
                                  </div>
                                  <div className="flex gap-4 text-xs text-sky-100/70">
                                    <span>V {formatNumber(post.views)}</span>
                                    <span>F {formatNumber(post.forwards)}</span>
                                    <span>R {formatNumber(post.reactions)}</span>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard
          value="overview"
          title={t("dashboard")}
          description={t("operationalKpis")}
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <StatCard
              title={t("mediaReceived")}
              value={formatNumber(Number(daily.media_received ?? 0))}
              icon={Inbox}
              description={`${t("decisions")}: ${formatNumber(query.data.decision_total_24h)}`}
              trend={{
                value: Number(receivedTrend.toFixed(1)),
                positive: receivedTrend >= 0,
              }}
            />
            <StatCard
              title={t("approved")}
              value={formatNumber(Number(daily.photos_approved ?? 0) + Number(daily.videos_approved ?? 0))}
              icon={CheckCircle2}
              description={`${t("rejected")}: ${formatNumber(Number(daily.photos_rejected ?? 0) + Number(daily.videos_rejected ?? 0))}`}
              trend={{
                value: Number(approvedTrend.toFixed(1)),
                positive: approvedTrend >= 0,
              }}
            />
            <StatCard
              title={t("publishEvents")}
              value={formatNumber(Number(daily.publish_events ?? 0))}
              icon={Send}
              description={`${t("channelDeliveries")}: ${formatNumber(Number(daily.channel_deliveries ?? 0))}`}
              trend={{
                value: Number(publishedTrend.toFixed(1)),
                positive: publishedTrend >= 0,
              }}
            />
            <StatCard
              title={t("queuePressure")}
              value={formatNumber(queuePressure)}
              icon={Layers3}
              description={`${t("batchQueue")}: ${currentBatchCount} · ${t("scheduledQueue")}: ${currentScheduledCount}`}
            />
            <StatCard
              title={t("approvalRate24h")}
              value={formatPercent(approval24h)}
              icon={Gauge}
              description={`${t("errorRate24h")}: ${formatPercent(errorRate24h)}`}
              trend={{
                value: Number((currentApprovalWindow - previousApprovalWindow).toFixed(1)),
                positive: currentApprovalWindow >= previousApprovalWindow,
              }}
            />
            <StatCard
              title={t("successRate24h")}
              value={formatPercent(success24h)}
              icon={ShieldCheck}
              description={`${t("onTimePublishRate")}: ${formatPercent(scheduleHealth.on_time_publish_rate)}`}
              trend={{
                value: Number((currentSuccessWindow - previousSuccessWindow).toFixed(1)),
                positive: currentSuccessWindow >= previousSuccessWindow,
              }}
            />
          </div>
        </SectionCard>

        <SectionCard
          value="activity"
          title={t("activityTrend")}
          description={t("hourlyRhythm")}
        >
          <div className="grid gap-6 xl:grid-cols-3">
            <div className="rounded-xl border border-border/60 bg-background/35 p-6 xl:col-span-2">
          <div className="mb-4">
            <h3 className="text-sm font-semibold">{t("activityTrend")}</h3>
            <p className="text-xs text-muted-foreground">{t("analytics")}</p>
          </div>
          <ChartContainer config={activityChartConfig} className="h-[320px] w-full aspect-auto">
            <ComposedChart data={activitySeries}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" tickFormatter={formatShortDate} minTickGap={24} />
              <YAxis allowDecimals={false} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(value) =>
                      typeof value === "string" ? formatShortDate(value) : String(value)
                    }
                  />
                }
              />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar
                dataKey="received"
                fill="var(--color-received)"
                radius={[6, 6, 0, 0]}
                maxBarSize={28}
              />
              <Line
                type="monotone"
                dataKey="approved"
                stroke="var(--color-approved)"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="published"
                stroke="var(--color-published)"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="errors"
                stroke="var(--color-errors)"
                strokeDasharray="4 4"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ChartContainer>
        </div>

            <div className="rounded-xl border border-border/60 bg-background/35 p-6">
          <div className="mb-4">
            <h3 className="text-sm font-semibold">{t("hourlyRhythm")}</h3>
            <p className="text-xs text-muted-foreground">
              {t("busiestHour")}: {busiestHourLabel}
            </p>
          </div>
          <ChartContainer config={hourlyChartConfig} className="h-[320px] w-full aspect-auto">
            <BarChart data={hourlyActivity}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="hour" tickFormatter={formatHourLabel} interval={3} />
              <YAxis allowDecimals={false} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(value) =>
                      typeof value === "number" ? formatHourLabel(value) : String(value)
                    }
                  />
                }
              />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar dataKey="approved" stackId="decisions" fill="var(--color-approved)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="rejected" stackId="decisions" fill="var(--color-rejected)" radius={[4, 4, 0, 0]} />
              <Line
                type="monotone"
                dataKey="published"
                stroke="var(--color-published)"
                strokeWidth={2}
                dot={false}
              />
            </BarChart>
          </ChartContainer>
        </div>
          </div>
        </SectionCard>

        <SectionCard
          value="operations"
          title={t("processingSpeed")}
          description={t("scheduleHealth")}
        >
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-border/60 bg-background/35 p-6">
          <div className="mb-4">
            <h3 className="text-sm font-semibold">{t("processingSpeed")}</h3>
            <p className="text-xs text-muted-foreground">
              {t("photosProcessed")} / {t("videosProcessed")}
            </p>
          </div>
          <div className="space-y-5">
            {Object.entries(histogram).map(([kind, buckets]) => {
              const maxCount = Math.max(1, ...buckets.map((bucket) => bucket.count));
              return (
                <div key={kind} className="space-y-2">
                  <p className="text-sm font-medium capitalize">{kind}</p>
                  {buckets.map((bucket) => (
                    <div key={bucket.label}>
                      <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                        <span>{bucket.label}</span>
                        <span>{formatNumber(bucket.count)}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${(bucket.count / maxCount) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <MetricRow
              label={t("avgPhotoProcessing")}
              value={formatSeconds(performance.avg_photo_processing_time)}
            />
            <MetricRow
              label={t("avgVideoProcessing")}
              value={formatSeconds(performance.avg_video_processing_time)}
            />
            <MetricRow
              label={t("avgUploadTime")}
              value={formatSeconds(performance.avg_upload_time)}
            />
            <MetricRow
              label={t("avgDownloadTime")}
              value={formatSeconds(performance.avg_download_time)}
            />
          </div>
        </div>

            <div className="rounded-xl border border-border/60 bg-background/35 p-6">
          <div className="mb-4">
            <h3 className="text-sm font-semibold">{t("scheduleHealth")}</h3>
            <p className="text-xs text-muted-foreground">{t("trackedScheduledPublishes")}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <MetricRow
              label={t("avgScheduleLead")}
              value={formatHours(scheduleHealth.avg_schedule_lead_hours)}
            />
            <MetricRow
              label={t("avgScheduleDelay")}
              value={formatMinutes(scheduleHealth.avg_schedule_delay_minutes)}
            />
            <MetricRow
              label={t("onTimePublishRate")}
              value={formatPercent(scheduleHealth.on_time_publish_rate)}
            />
            <MetricRow
              label={t("trackedScheduledPublishes")}
              value={formatNumber(scheduleHealth.scheduled_publish_count)}
            />
            <MetricRow
              label={t("scheduledToday")}
              value={formatNumber(Number(daily.scheduled_posts ?? 0))}
            />
            <MetricRow
              label={t("rescheduledToday")}
              value={formatNumber(Number(daily.rescheduled_posts ?? 0))}
            />
            <MetricRow
              label={t("unscheduledToday")}
              value={formatNumber(Number(daily.unscheduled_posts ?? 0))}
            />
            <MetricRow
              label={t("scheduledQueue")}
              value={formatNumber(currentScheduledCount)}
            />
          </div>
          <div className="mt-5 space-y-3">
            {scheduleDelayDistribution.map((bucket) => {
              const maxCount = Math.max(
                1,
                ...scheduleDelayDistribution.map((entry) => entry.count),
              );
              return (
                <div key={bucket.label}>
                  <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                    <span>{bucket.label}</span>
                    <span>{formatNumber(bucket.count)}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-secondary">
                    <div
                      className="h-full rounded-full"
                      style={{
                        backgroundColor: "hsl(var(--chart-4))",
                        width: `${(bucket.count / maxCount) * 100}%`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
          </div>
        </SectionCard>

        <SectionCard
          value="sources"
          title={t("sourceQuality")}
          description={t("operationalKpis")}
        >
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-border/60 bg-background/35 p-6">
          <div className="mb-4">
            <h3 className="text-sm font-semibold">{t("sourceQuality")}</h3>
            <p className="text-xs text-muted-foreground">{t("topSourcesByAcceptance")}</p>
          </div>
          {sourceAcceptance.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noSourceData")}</p>
          ) : (
            <ChartContainer config={sourceChartConfig} className="h-[320px] w-full aspect-auto">
              <BarChart data={sourceAcceptance} layout="vertical" margin={{ left: 12 }}>
                <CartesianGrid horizontal={false} />
                <XAxis
                  type="number"
                  domain={[0, 100]}
                  tickFormatter={(value) => `${value}%`}
                />
                <YAxis
                  dataKey="source"
                  type="category"
                  width={110}
                  tickFormatter={(value) => truncateLabel(String(value))}
                />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      indicator="line"
                      formatter={(value, _name, item) => (
                        <div className="flex w-full items-center justify-between gap-4">
                          <span className="text-muted-foreground">
                            {truncateLabel(String(item.payload.source), 32)}
                          </span>
                          <span className="font-mono font-medium">
                            {formatPercent(Number(value))}
                          </span>
                        </div>
                      )}
                    />
                  }
                />
                <Bar dataKey="acceptance_rate" fill="var(--color-acceptance_rate)" radius={6} />
              </BarChart>
            </ChartContainer>
          )}
        </div>

            <div className="rounded-xl border border-border/60 bg-background/35 p-6 space-y-3">
          <div className="mb-1">
            <h3 className="text-sm font-semibold">{t("operationalKpis")}</h3>
            <p className="text-xs text-muted-foreground">{t("dashboard")}</p>
          </div>
          <MetricRow label={t("approvalRate24h")} value={formatPercent(approval24h)} />
          <MetricRow label={t("approvalTotal")} value={formatPercent(approvalTotal)} />
          <MetricRow label={t("rejectionRate24h")} value={formatPercent(rejectionRate24h)} />
          <MetricRow label={t("errorRate24h")} value={formatPercent(errorRate24h)} />
          <MetricRow label={t("publishPerApproval")} value={formatPercent(publishPerApproval)} />
          <MetricRow
            label={t("deliveriesPerPost")}
            value={deliveriesPerPost.toFixed(2)}
          />
          <MetricRow
            label={t("channelDeliveries")}
            value={formatNumber(Number(daily.channel_deliveries ?? 0))}
          />
          <MetricRow label={t("publishEvents")} value={formatNumber(Number(daily.publish_events ?? 0))} />
          <MetricRow label={t("busiestHour")} value={busiestHourLabel} />
          <MetricRow label={t("batchQueue")} value={formatNumber(currentBatchCount)} />
          <MetricRow label={t("errors")} value={formatNumber(dailyErrors)} />
          <MetricRow label={t("errorsTotal")} value={formatNumber(totalErrors)} />
          <MetricRow label={t("posts14d")} value={formatNumber(published14d)} />
        </div>
          </div>
        </SectionCard>
      </Accordion>

      <div className="flex justify-end">
        <Button variant="outline" onClick={() => resetMutation.mutate()}>
          {t("resetStats")}
        </Button>
      </div>
    </div>
  );
};

export default StatsPage;
