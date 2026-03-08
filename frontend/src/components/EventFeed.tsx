import { Activity, Clock3, Files, User2 } from "lucide-react";
import BadgeStatus from "@/components/BadgeStatus";
import { useSession } from "@/components/SessionProvider";
import type { EventEntry } from "@/lib/api";
import { formatDisplayDate } from "@/lib/datetime";
import {
  getEventIntent,
  getEventPrimarySource,
  humanizeEventAction,
  humanizeEventKey,
} from "@/lib/event-log";
import { cn } from "@/lib/utils";

type EventFeedVariant = "compact" | "full";

interface EventFeedProps {
  events: EventEntry[];
  emptyMessage: string;
  className?: string;
  variant?: EventFeedVariant;
}

function formatActorLabel(
  actor: EventEntry["actor"],
  fallbackLabel: string,
): string {
  if (actor == null || actor === "") {
    return fallbackLabel;
  }
  return String(actor);
}

function formatExtraValue(value: unknown): string {
  if (value == null) {
    return "—";
  }

  if (typeof value === "string") {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return formatDisplayDate(value);
    }
    return value;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return JSON.stringify(value);
}

function submitterLabel(item: EventEntry["items"][number], unknownLabel: string): string {
  const submitter = item.submitter;
  if (!submitter) {
    return unknownLabel;
  }

  if (submitter.is_admin && submitter.source) {
    return `@${submitter.source}`;
  }

  if (submitter.source) {
    return submitter.source;
  }

  if (submitter.user_id) {
    return `#${submitter.user_id}`;
  }

  return unknownLabel;
}

function CompactEventRow({ event }: { event: EventEntry }) {
  const { t } = useSession();
  const source = getEventPrimarySource(event);
  const actor = formatActorLabel(event.actor, t("system"));
  const eventTone = getEventIntent(event.action);

  return (
    <article className="flex gap-3 rounded-xl border border-border/40 bg-secondary/25 p-3 transition-colors hover:bg-secondary/40">
      <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/12 text-primary">
        <Activity className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <BadgeStatus variant={eventTone}>{humanizeEventAction(event.action)}</BadgeStatus>
          {event.origin ? <BadgeStatus variant="default">{event.origin}</BadgeStatus> : null}
          {event.items.length > 0 ? (
            <span className="text-xs text-muted-foreground">
              {t("count")}: {event.items.length}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Clock3 className="h-3.5 w-3.5" />
            {formatDisplayDate(event.timestamp)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <User2 className="h-3.5 w-3.5" />
            {actor}
          </span>
          {source ? (
            <span className="inline-flex items-center gap-1.5">
              <Files className="h-3.5 w-3.5" />
              {source}
            </span>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function FullEventCard({ event }: { event: EventEntry }) {
  const { t } = useSession();
  const actor = formatActorLabel(event.actor, t("system"));
  const source = getEventPrimarySource(event);
  const eventTone = getEventIntent(event.action);
  const extraEntries = Object.entries(event.extra ?? {});

  return (
    <article className="glass-card overflow-hidden p-4 md:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <BadgeStatus variant={eventTone}>{humanizeEventAction(event.action)}</BadgeStatus>
            {event.origin ? <BadgeStatus variant="default">{event.origin}</BadgeStatus> : null}
            <BadgeStatus variant="primary">
              {t("count")}: {event.items.length}
            </BadgeStatus>
          </div>

          <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-2">
              <Clock3 className="h-4 w-4" />
              {formatDisplayDate(event.timestamp)}
            </span>
            <span className="inline-flex items-center gap-2">
              <User2 className="h-4 w-4" />
              {actor}
            </span>
            {source ? (
              <span className="inline-flex items-center gap-2">
                <Files className="h-4 w-4" />
                {source}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      {event.items.length > 0 ? (
        <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {event.items.map((item) => (
            <div
              key={item.path}
              className="rounded-xl border border-border/50 bg-secondary/35 px-3 py-2.5"
            >
              <div className="flex items-center justify-between gap-3">
                <code className="truncate text-xs text-foreground">{item.name}</code>
                {item.media_type ? (
                  <span className="shrink-0 rounded-full bg-background px-2 py-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                    {item.media_type}
                  </span>
                ) : null}
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>{submitterLabel(item, t("unknown"))}</span>
                {item.submitter?.source && item.submitter?.source !== getEventPrimarySource(event) ? (
                  <span>{item.submitter.source}</span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">{t("noItemsRecorded")}</p>
      )}

      {extraEntries.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {extraEntries.map(([key, value]) => (
            <div
              key={key}
              className="rounded-xl border border-border/40 bg-background/70 px-3 py-2"
            >
              <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                {humanizeEventKey(key)}
              </div>
              <div className="mt-1 text-sm">{formatExtraValue(value)}</div>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

const EventFeed = ({
  events,
  emptyMessage,
  className,
  variant = "full",
}: EventFeedProps) => {
  if (events.length === 0) {
    return (
      <div className="glass-card p-12 text-center">
        <p className="text-muted-foreground">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      {events.map((event, index) =>
        variant === "compact" ? (
          <CompactEventRow
            key={`${event.timestamp ?? "event"}-${event.action ?? "action"}-${index}`}
            event={event}
          />
        ) : (
          <FullEventCard
            key={`${event.timestamp ?? "event"}-${event.action ?? "action"}-${index}`}
            event={event}
          />
        ),
      )}
    </div>
  );
};

export default EventFeed;
