import { type ReactNode } from "react";
import BadgeStatus from "@/components/BadgeStatus";
import ClickableImage from "@/components/ClickableImage";
import { useSession } from "@/components/SessionProvider";
import { formatDisplayDate } from "@/lib/datetime";
import type { MediaGroup } from "@/lib/api";

interface MediaGroupCardProps {
  group: MediaGroup;
  actions?: ReactNode;
  scheduleInput?: ReactNode;
}

const MediaGroupCard = ({
  group,
  actions,
  scheduleInput,
}: MediaGroupCardProps) => {
  const { t } = useSession();
  const submitter = group.submitter;

  return (
    <div className="glass-card overflow-hidden">
      <div
        className={`grid gap-2 p-3 ${
          group.items.length > 1 ? "grid-cols-2" : "grid-cols-1"
        }`}
      >
        {group.items.map((item) => (
          <div
            key={item.path}
            className="overflow-hidden rounded-lg bg-secondary/50 aspect-square"
          >
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
        ))}
      </div>
      <div className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <p className="text-sm font-medium">
              {group.caption || group.items[0]?.caption || group.items[0]?.name}
            </p>
            {group.source ? (
              <p className="text-xs text-muted-foreground">
                {t("submittedVia", { source: group.source })}
              </p>
            ) : null}
          </div>
          {group.is_group ? (
            <BadgeStatus variant="default">{t("totalItems", { count: group.count })}</BadgeStatus>
          ) : null}
        </div>

        {submitter ? (
          <p className="text-xs text-muted-foreground">
            {t("suggestedBy")}:{" "}
            {submitter.is_admin && submitter.source
              ? `${submitter.source} (${t("admin")})`
              : submitter.user_id
                ? t("userId", { id: submitter.user_id })
                : t("unknown")}
          </p>
        ) : null}

        {group.trashed_at ? (
          <p className="text-xs text-muted-foreground">
            {t("trashedAt", { time: formatDisplayDate(group.trashed_at) })}
          </p>
        ) : null}
        {group.expires_at ? (
          <p className="text-xs text-muted-foreground">
            {t("expiresAt", { time: formatDisplayDate(group.expires_at) })}
          </p>
        ) : null}

        {scheduleInput}
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
    </div>
  );
};

export default MediaGroupCard;
