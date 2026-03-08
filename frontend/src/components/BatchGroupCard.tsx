import { Clock3, FileText, Layers3, Send, Trash2 } from "lucide-react";
import BadgeStatus from "@/components/BadgeStatus";
import ClickableImage from "@/components/ClickableImage";
import ScheduleDateTimePicker from "@/components/ScheduleDateTimePicker";
import { useSession } from "@/components/SessionProvider";
import { Button } from "@/components/ui/button";
import { formatDisplayDate } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type { MediaGroup } from "@/lib/api";

type BatchAction = "push" | "schedule" | "remove_batch";

interface BatchGroupCardProps {
  group: MediaGroup;
  scheduleValue: string;
  onScheduleChange: (value: string) => void;
  onManualSchedule: () => void;
  onAction: (action: BatchAction) => void;
  activeAction?: BatchAction | null;
  isScheduling?: boolean;
}

const BatchGroupCard = ({
  group,
  scheduleValue,
  onScheduleChange,
  onManualSchedule,
  onAction,
  activeAction = null,
  isScheduling = false,
}: BatchGroupCardProps) => {
  const { t } = useSession();
  const primaryItem = group.items[0];
  const title = group.caption || primaryItem?.caption || primaryItem?.name || t("unknown");
  const source = group.source || primaryItem?.source || null;
  const paths = group.items.map((item) => item.path);
  const isBusy = isScheduling || activeAction !== null;
  const kindSummary = Array.from(new Set(group.items.map((item) => item.kind.toUpperCase()))).join(
    " · ",
  );

  return (
    <article className="glass-card overflow-hidden">
      <div className="grid gap-0 xl:grid-cols-[minmax(320px,1.1fr)_minmax(0,1fr)]">
        <div className="relative border-b border-border/60 bg-secondary/20 xl:border-b-0 xl:border-r">
          <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-2">
            <BadgeStatus variant={group.is_group ? "primary" : "default"}>
              <span className="flex items-center gap-1.5">
                <Layers3 className="h-3.5 w-3.5" />
                {t("totalItems", { count: group.count })}
              </span>
            </BadgeStatus>
            {source ? <BadgeStatus variant="default">{source}</BadgeStatus> : null}
          </div>

          <div
            className={cn(
              "grid min-h-[280px] gap-2 p-3",
              group.items.length > 1 ? "grid-cols-2" : "grid-cols-1",
            )}
          >
            {group.items.map((item) => (
              <div
                key={item.path}
                className="overflow-hidden rounded-xl border border-border/60 bg-card/50 shadow-sm"
              >
                <div className={cn("bg-card/40", group.items.length > 1 ? "aspect-square" : "aspect-[4/3]")}>
                  {item.kind === "image" ? (
                    <ClickableImage
                      src={item.url}
                      alt={item.caption ?? item.name}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <video
                      className="h-full w-full object-cover"
                      controls
                      preload="metadata"
                      src={item.url}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-4 p-5">
          <div className="space-y-2">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-medium uppercase tracking-[0.24em] text-muted-foreground">
                  {primaryItem?.caption || group.caption ? t("caption") : t("file")}
                </p>
                <h3 className="text-base font-semibold leading-snug text-foreground">{title}</h3>
              </div>
              <BadgeStatus variant="warning">{kindSummary || primaryItem?.kind.toUpperCase()}</BadgeStatus>
            </div>

            {source ? (
              <p className="text-sm text-muted-foreground">{t("submittedVia", { source })}</p>
            ) : null}

            {group.submitter ? (
              <p className="text-sm text-muted-foreground">
                {t("suggestedBy")}:{" "}
                {group.submitter.is_admin && group.submitter.source
                  ? `${group.submitter.source} (${t("admin")})`
                  : group.submitter.user_id
                    ? t("userId", { id: group.submitter.user_id })
                    : t("unknown")}
              </p>
            ) : null}
          </div>

          <div className="grid gap-3 xl:grid-cols-2">
            <div className="rounded-xl border border-border/70 bg-secondary/20 p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <FileText className="h-3.5 w-3.5" />
                {t("file")}
              </div>
              <div className="space-y-1.5">
                {paths.slice(0, 3).map((path) => (
                  <p key={path} className="font-mono text-xs leading-5 text-muted-foreground break-all">
                    {path}
                  </p>
                ))}
                {paths.length > 3 ? (
                  <p className="text-xs text-muted-foreground">{t("totalItems", { count: paths.length })}</p>
                ) : null}
              </div>
            </div>

            <div className="rounded-xl border border-border/70 bg-secondary/20 p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {t("mediaType")}
              </p>
              <p className="mt-2 text-sm font-medium text-foreground">{kindSummary || primaryItem?.kind}</p>
              {group.expires_at ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("expiresAt", { time: formatDisplayDate(group.expires_at) })}
                </p>
              ) : null}
              {group.trashed_at ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("trashedAt", { time: formatDisplayDate(group.trashed_at) })}
                </p>
              ) : null}
            </div>
          </div>

          <div className="space-y-3 rounded-2xl border border-border/70 bg-background/40 p-4">
            <div className="space-y-1">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {t("manualSchedule")}
              </p>
              <p className="text-sm text-muted-foreground">{t("scheduledAt")}</p>
            </div>

            <div className="flex flex-col gap-2 xl:flex-row">
              <ScheduleDateTimePicker value={scheduleValue} onChange={onScheduleChange} />
              <Button
                className="xl:min-w-40"
                onClick={onManualSchedule}
                disabled={!scheduleValue || isBusy}
              >
                <Clock3 className="h-4 w-4" />
                {isScheduling ? t("loading") : t("manualSchedule")}
              </Button>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button onClick={() => onAction("push")} disabled={isBusy}>
                <Send className="h-4 w-4" />
                {activeAction === "push" ? t("loading") : t("pushNow")}
              </Button>
              <Button variant="secondary" onClick={() => onAction("schedule")} disabled={isBusy}>
                <Clock3 className="h-4 w-4" />
                {activeAction === "schedule" ? t("loading") : t("schedule")}
              </Button>
              <Button
                variant="destructive"
                onClick={() => onAction("remove_batch")}
                disabled={isBusy}
              >
                <Trash2 className="h-4 w-4" />
                {activeAction === "remove_batch" ? t("loading") : t("remove")}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
};

export default BatchGroupCard;
