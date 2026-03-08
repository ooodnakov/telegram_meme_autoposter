import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Trophy,
  Users,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import { ErrorState, LoadingState } from "@/components/PageState";
import StatCard from "@/components/StatCard";
import { useSession } from "@/components/SessionProvider";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type LeaderboardEntry, type LeaderboardPayload } from "@/lib/api";
import { cn } from "@/lib/utils";

type LeaderboardCategory = keyof LeaderboardPayload;
type LeaderboardMetric = "submissions" | "approved" | "rejected";

interface CategoryConfig {
  key: LeaderboardCategory;
  label: string;
  metric: LeaderboardMetric;
  icon: LucideIcon;
  accent: string;
  badgeClassName: string;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function sumEntries(entries: LeaderboardEntry[], key: LeaderboardMetric): number {
  return entries.reduce((total, entry) => total + Number(entry[key] ?? 0), 0);
}

function getMetricShare(value: number, total: number): number {
  if (total <= 0) {
    return 0;
  }
  return (value / total) * 100;
}

function dedupeEntries(payload: LeaderboardPayload): LeaderboardEntry[] {
  const entries = new Map<string, LeaderboardEntry>();

  for (const list of Object.values(payload)) {
    for (const entry of list) {
      if (!entries.has(entry.source)) {
        entries.set(entry.source, entry);
      }
    }
  }

  return Array.from(entries.values());
}

function RankBadge({ rank, className }: { rank: number; className?: string }) {
  return (
    <div
      className={cn(
        "inline-flex h-8 min-w-8 items-center justify-center rounded-full border border-border/70 bg-background/70 px-2 text-xs font-semibold text-muted-foreground",
        rank === 1 && "border-primary/40 bg-primary/10 text-primary",
        rank === 2 && "border-success/40 bg-success/10 text-success",
        rank === 3 && "border-warning/40 bg-warning/10 text-warning",
        className,
      )}
    >
      #{rank}
    </div>
  );
}

function LeaderboardSpotlight({
  title,
  source,
  value,
  description,
  icon: Icon,
  accentClassName,
}: {
  title: string;
  source?: string;
  value: string;
  description: string;
  icon: LucideIcon;
  accentClassName: string;
}) {
  return (
    <Card className="glass-card h-full overflow-hidden border-border/60">
      <CardContent className="flex h-full flex-col gap-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              {title}
            </p>
            <p className="mt-2 text-lg font-semibold text-foreground">
              {source ?? "—"}
            </p>
          </div>
          <div className={cn("rounded-2xl p-3", accentClassName)}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
        <div className="text-3xl font-semibold tracking-tight">{value}</div>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}

function PodiumCard({
  entry,
  rank,
  totalMetric,
  config,
  acceptanceLabel,
  shareLabel,
}: {
  entry: LeaderboardEntry;
  rank: number;
  totalMetric: number;
  config: CategoryConfig;
  acceptanceLabel: string;
  shareLabel: string;
}) {
  const metricValue = entry[config.metric];
  const share = getMetricShare(metricValue, totalMetric);

  return (
    <Card
      className={cn(
        "glass-card overflow-hidden border-border/60 transition-transform duration-200 hover:-translate-y-1",
        rank === 1 && "border-primary/30 bg-primary/[0.08]",
      )}
    >
      <CardContent className="space-y-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <RankBadge rank={rank} />
            <p className="mt-3 truncate text-lg font-semibold text-foreground">
              {entry.source}
            </p>
          </div>
          <div className={cn("rounded-2xl p-3", config.accent)}>
            <config.icon className="h-5 w-5" />
          </div>
        </div>

        <div>
          <div className="text-3xl font-semibold tracking-tight">
            {formatNumber(metricValue)}
          </div>
          <p className="text-sm text-muted-foreground">{config.label}</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-2xl bg-secondary/50 px-3 py-2.5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              {shareLabel}
            </p>
            <p className="mt-1 font-medium tabular-nums">{formatPercent(share)}</p>
          </div>
          <div className="rounded-2xl bg-secondary/50 px-3 py-2.5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              {acceptanceLabel}
            </p>
            <p className="mt-1 font-medium tabular-nums">
              {formatPercent(entry.approved_pct)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function LeaderboardTable({
  rows,
  config,
  emptyMessage,
  acceptanceLabel,
  approvedLabel,
  rejectedLabel,
  shareLabel,
  sourceLabel,
}: {
  rows: LeaderboardEntry[];
  config: CategoryConfig;
  emptyMessage: string;
  acceptanceLabel: string;
  approvedLabel: string;
  rejectedLabel: string;
  shareLabel: string;
  sourceLabel: string;
}) {
  if (rows.length === 0) {
    return (
      <div className="glass-card p-12 text-center">
        <p className="text-muted-foreground">{emptyMessage}</p>
      </div>
    );
  }

  const totalMetric = sumEntries(rows, config.metric);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        {rows.slice(0, 3).map((entry, index) => (
          <PodiumCard
            key={`${config.key}-${entry.source}`}
            entry={entry}
            rank={index + 1}
            totalMetric={totalMetric}
            config={config}
            acceptanceLabel={acceptanceLabel}
            shareLabel={shareLabel}
          />
        ))}
      </div>

      <div className="space-y-3 md:hidden">
        {rows.map((entry, index) => {
          const metricValue = entry[config.metric];
          const share = getMetricShare(metricValue, totalMetric);

          return (
            <Card key={`${config.key}-mobile-${entry.source}`} className="glass-card border-border/60">
              <CardContent className="space-y-4 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <RankBadge rank={index + 1} />
                    <p className="mt-3 truncate text-base font-semibold text-foreground">
                      {entry.source}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-semibold tracking-tight">
                      {formatNumber(metricValue)}
                    </p>
                    <p className="text-xs text-muted-foreground">{config.label}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded-xl bg-secondary/50 px-3 py-2.5">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      {shareLabel}
                    </p>
                    <p className="mt-1 font-medium tabular-nums">{formatPercent(share)}</p>
                  </div>
                  <div className="rounded-xl bg-secondary/50 px-3 py-2.5">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      {acceptanceLabel}
                    </p>
                    <p className="mt-1 font-medium tabular-nums">
                      {formatPercent(entry.approved_pct)}
                    </p>
                  </div>
                  <div className="rounded-xl bg-secondary/50 px-3 py-2.5">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      {approvedLabel}
                    </p>
                    <p className="mt-1 font-medium tabular-nums">
                      {formatNumber(entry.approved)}
                    </p>
                  </div>
                  <div className="rounded-xl bg-secondary/50 px-3 py-2.5">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      {rejectedLabel}
                    </p>
                    <p className="mt-1 font-medium tabular-nums">
                      {formatNumber(entry.rejected)}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card className="glass-card hidden overflow-hidden border-border/60 md:block">
        <Table>
          <TableHeader>
            <TableRow className="border-border/60 hover:bg-transparent">
              <TableHead className="w-20">#</TableHead>
              <TableHead>{sourceLabel}</TableHead>
              <TableHead>{config.label}</TableHead>
              <TableHead>{shareLabel}</TableHead>
              <TableHead>{approvedLabel}</TableHead>
              <TableHead>{rejectedLabel}</TableHead>
              <TableHead>{acceptanceLabel}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((entry, index) => {
              const metricValue = entry[config.metric];
              const share = getMetricShare(metricValue, totalMetric);

              return (
                <TableRow key={`${config.key}-row-${entry.source}`} className="border-border/40">
                  <TableCell>
                    <RankBadge rank={index + 1} />
                  </TableCell>
                  <TableCell className="font-medium text-foreground">
                    <div className="max-w-[16rem] truncate">{entry.source}</div>
                  </TableCell>
                  <TableCell className="font-semibold tabular-nums">
                    {formatNumber(metricValue)}
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {formatPercent(share)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className="bg-success/10 font-medium text-success hover:bg-success/10"
                    >
                      {formatNumber(entry.approved)} · {formatPercent(entry.approved_pct)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className="bg-destructive/10 font-medium text-destructive hover:bg-destructive/10"
                    >
                      {formatNumber(entry.rejected)} · {formatPercent(entry.rejected_pct)}
                    </Badge>
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {formatPercent(entry.approved_pct)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

const LeaderboardPage = () => {
  const queryClient = useQueryClient();
  const { t } = useSession();

  const query = useQuery({
    queryKey: ["leaderboard"],
    queryFn: api.getLeaderboard,
  });

  const resetMutation = useMutation({
    mutationFn: api.resetLeaderboard,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["leaderboard"] });
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

  const allEntries = dedupeEntries(query.data);
  const totalSources = allEntries.length;
  const totalSubmissions = sumEntries(allEntries, "submissions");
  const totalApproved = sumEntries(allEntries, "approved");
  const totalRejected = sumEntries(allEntries, "rejected");
  const overallApprovalRate = getMetricShare(totalApproved, totalSubmissions);
  const overallRejectionRate = getMetricShare(totalRejected, totalSubmissions);
  const topSource = [...allEntries].sort((left, right) => right.submissions - left.submissions)[0];
  const bestApprovalSource = [...allEntries]
    .filter((entry) => entry.submissions > 0)
    .sort((left, right) => right.approved_pct - left.approved_pct)[0];
  const highestRejectionSource = [...allEntries]
    .filter((entry) => entry.submissions > 0)
    .sort((left, right) => right.rejected_pct - left.rejected_pct)[0];

  const categories: CategoryConfig[] = [
    {
      key: "submissions",
      label: t("submissions"),
      metric: "submissions",
      icon: Trophy,
      accent: "bg-primary/12 text-primary",
      badgeClassName: "bg-primary/10 text-primary border-primary/20",
    },
    {
      key: "approved",
      label: t("approved"),
      metric: "approved",
      icon: CheckCircle2,
      accent: "bg-success/12 text-success",
      badgeClassName: "bg-success/10 text-success border-success/20",
    },
    {
      key: "rejected",
      label: t("rejected"),
      metric: "rejected",
      icon: XCircle,
      accent: "bg-destructive/12 text-destructive",
      badgeClassName: "bg-destructive/10 text-destructive border-destructive/20",
    },
  ];

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-[28px] border border-primary/20 bg-[radial-gradient(circle_at_top_left,_hsl(var(--primary)/0.18),_transparent_36%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--card)/0.88)_100%)] px-6 py-6 shadow-[0_24px_80px_-40px_hsl(var(--primary)/0.45)]">
        <div className="absolute inset-y-0 right-0 hidden w-1/3 bg-[radial-gradient(circle_at_center,_hsl(var(--chart-2)/0.16),_transparent_60%)] lg:block" />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <Badge className="border-primary/20 bg-primary/10 text-primary hover:bg-primary/10">
              {t("leaderboard")}
            </Badge>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight text-foreground">
              {t("leaderboard")}
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
              {t("leaderboardSubtitle")}
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
              <RefreshCw className="h-4 w-4" />
              {t("refresh")}
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" disabled={resetMutation.isPending}>
                  <RotateCcw className="h-4 w-4" />
                  {resetMutation.isPending ? t("resetting") : t("resetLeaderboard")}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t("leaderboardResetTitle")}</AlertDialogTitle>
                  <AlertDialogDescription>
                    {t("leaderboardResetDescription")}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
                  <AlertDialogAction
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    onClick={() => resetMutation.mutate()}
                  >
                    {t("resetLeaderboard")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title={t("trackedSources")}
          value={formatNumber(totalSources)}
          icon={Users}
          description={t("totalItems", { count: totalSubmissions })}
        />
        <StatCard
          title={t("submissions")}
          value={formatNumber(totalSubmissions)}
          icon={Trophy}
          description={topSource ? `${t("source")}: ${topSource.source}` : undefined}
        />
        <StatCard
          title={t("overallApprovalRate")}
          value={formatPercent(overallApprovalRate)}
          icon={CheckCircle2}
          description={`${t("approved")}: ${formatNumber(totalApproved)}`}
        />
        <StatCard
          title={t("overallRejectionRate")}
          value={formatPercent(overallRejectionRate)}
          icon={ShieldAlert}
          description={`${t("rejected")}: ${formatNumber(totalRejected)}`}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <LeaderboardSpotlight
          title={t("topSource")}
          source={topSource?.source}
          value={topSource ? formatNumber(topSource.submissions) : "—"}
          description={
            topSource
              ? `${t("acceptanceRate")}: ${formatPercent(topSource.approved_pct)}`
              : t("noLeaderboardData")
          }
          icon={Trophy}
          accentClassName="bg-primary/12 text-primary"
        />
        <LeaderboardSpotlight
          title={t("bestApprovalSource")}
          source={bestApprovalSource?.source}
          value={bestApprovalSource ? formatPercent(bestApprovalSource.approved_pct) : "—"}
          description={
            bestApprovalSource
              ? `${formatNumber(bestApprovalSource.approved)} ${t("approved")}`
              : t("noLeaderboardData")
          }
          icon={CheckCircle2}
          accentClassName="bg-success/12 text-success"
        />
        <LeaderboardSpotlight
          title={t("highestRejectionRate")}
          source={highestRejectionSource?.source}
          value={
            highestRejectionSource
              ? formatPercent(highestRejectionSource.rejected_pct)
              : "—"
          }
          description={
            highestRejectionSource
              ? `${formatNumber(highestRejectionSource.rejected)} ${t("rejected")}`
              : t("noLeaderboardData")
          }
          icon={ShieldAlert}
          accentClassName="bg-destructive/12 text-destructive"
        />
      </div>

      <Tabs defaultValue="submissions" className="space-y-4">
        <TabsList className="h-auto flex-wrap gap-2 rounded-2xl bg-secondary/60 p-1">
          {categories.map((category) => {
            const count = query.data[category.key].length;

            return (
              <TabsTrigger
                key={category.key}
                value={category.key}
                className="rounded-xl px-4 py-2.5 data-[state=active]:bg-background"
              >
                <span className="flex items-center gap-2">
                  <category.icon className="h-4 w-4" />
                  {category.label}
                  <Badge
                    variant="outline"
                    className={cn("border text-[10px] font-semibold", category.badgeClassName)}
                  >
                    {count}
                  </Badge>
                </span>
              </TabsTrigger>
            );
          })}
        </TabsList>

        {categories.map((category) => (
          <TabsContent key={category.key} value={category.key} className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-foreground">{category.label}</h2>
                <p className="text-sm text-muted-foreground">
                  {t("totalItems", { count: query.data[category.key].length })}
                </p>
              </div>
            </div>

            <LeaderboardTable
              rows={query.data[category.key]}
              config={category}
              emptyMessage={t("noLeaderboardData")}
              acceptanceLabel={t("acceptanceRate")}
              approvedLabel={t("approved")}
              rejectedLabel={t("rejected")}
              shareLabel={t("share")}
              sourceLabel={t("source")}
            />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
};

export default LeaderboardPage;
