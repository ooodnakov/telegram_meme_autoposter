import { Clock3, FileText, Save, Trash2 } from "lucide-react";
import BadgeStatus from "@/components/BadgeStatus";
import ClickableImage from "@/components/ClickableImage";
import ScheduleDateTimePicker from "@/components/ScheduleDateTimePicker";
import { useSession } from "@/components/SessionProvider";
import { Button } from "@/components/ui/button";
import { formatDisplayDate } from "@/lib/datetime";
import type { QueueItem } from "@/lib/api";

interface QueueItemCardProps {
  item: QueueItem;
  draftValue: string;
  onDraftChange: (value: string) => void;
  onSave: () => void;
  onUnschedule: () => void;
  isSaving?: boolean;
  isUnscheduling?: boolean;
}

const QueueItemCard = ({
  item,
  draftValue,
  onDraftChange,
  onSave,
  onUnschedule,
  isSaving = false,
  isUnscheduling = false,
}: QueueItemCardProps) => {
  const { t } = useSession();
  const hasCaption = Boolean(item.caption?.trim());

  return (
    <article className="glass-card overflow-hidden">
      <div className="grid gap-0 lg:grid-cols-[minmax(260px,320px)_1fr]">
        <div className="relative border-b border-border/60 bg-secondary/20 lg:border-b-0 lg:border-r">
          <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-2">
            <BadgeStatus variant="warning">
              <span className="flex items-center gap-1.5">
                <Clock3 className="h-3.5 w-3.5" />
                {formatDisplayDate(item.scheduled_at)}
              </span>
            </BadgeStatus>
            {item.source ? <BadgeStatus variant="default">{item.source}</BadgeStatus> : null}
          </div>

          <div className="aspect-[4/3] bg-card/50">
            {item.kind === "image" ? (
              <ClickableImage
                src={item.url}
                alt={item.caption ?? item.name}
                className="h-full w-full object-cover"
              />
            ) : (
              <video className="h-full w-full object-cover" controls preload="metadata" src={item.url} />
            )}
          </div>
        </div>

        <div className="space-y-4 p-5">
          <div className="space-y-2">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-medium uppercase tracking-[0.24em] text-muted-foreground">
                  {hasCaption ? t("caption") : t("file")}
                </p>
                <h3 className="text-base font-semibold leading-snug text-foreground">
                  {item.caption || item.name}
                </h3>
              </div>
              <BadgeStatus variant="primary">{item.kind.toUpperCase()}</BadgeStatus>
            </div>

            {hasCaption ? (
              <p className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{t("file")}:</span> {item.name}
              </p>
            ) : null}
          </div>

          <div className="grid gap-3 xl:grid-cols-2">
            <div className="rounded-xl border border-border/70 bg-secondary/20 p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <FileText className="h-3.5 w-3.5" />
                {t("file")}
              </div>
              <p className="font-mono text-xs leading-5 text-muted-foreground break-all">{item.path}</p>
            </div>

            <div className="rounded-xl border border-border/70 bg-secondary/20 p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {t("scheduledAt")}
              </p>
              <p className="mt-2 text-sm font-medium text-foreground">
                {formatDisplayDate(item.scheduled_at)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">{item.mime_type ?? item.kind}</p>
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
              <ScheduleDateTimePicker value={draftValue} onChange={onDraftChange} />
              <Button
                className="xl:min-w-28"
                onClick={onSave}
                disabled={isSaving || isUnscheduling}
              >
                <Save className="h-4 w-4" />
                {isSaving ? t("loading") : t("save")}
              </Button>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="destructive"
                onClick={onUnschedule}
                disabled={isSaving || isUnscheduling}
              >
                <Trash2 className="h-4 w-4" />
                {isUnscheduling ? t("loading") : t("unschedule")}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
};

export default QueueItemCard;
