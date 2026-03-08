import type { EventEntry } from "@/lib/api";
import type { BadgeStatusVariant } from "@/components/BadgeStatus";

function titleCase(value: string): string {
  return value
    .split(/[\s_]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function humanizeEventAction(action?: string | null): string {
  if (!action) {
    return "Unknown";
  }
  return titleCase(action);
}

export function humanizeEventKey(key: string): string {
  return titleCase(key);
}

export function getEventPrimarySource(event: EventEntry): string | null {
  return (
    event.items.find((item) => item.submitter?.source)?.submitter?.source ?? null
  );
}

export function getEventIntent(action?: string | null): BadgeStatusVariant {
  const normalized = (action ?? "").toLowerCase();
  if (
    normalized.includes("notok") ||
    normalized.includes("fail") ||
    normalized.includes("reject") ||
    normalized.includes("remove") ||
    normalized.includes("delete") ||
    normalized.includes("reset")
  ) {
    return "destructive";
  }
  if (
    normalized.includes("schedule") ||
    normalized.includes("queue") ||
    normalized.includes("job")
  ) {
    return "warning";
  }
  if (
    normalized.includes("ok") ||
    normalized.includes("push") ||
    normalized.includes("approve") ||
    normalized.includes("publish") ||
    normalized.includes("send")
  ) {
    return "success";
  }
  return "primary";
}

export function buildEventSearchText(event: EventEntry): string {
  const itemText = event.items.flatMap((item) => [
    item.name,
    item.path,
    item.media_type,
    item.submitter?.source,
    item.submitter?.user_id ? String(item.submitter.user_id) : null,
  ]);
  const extraText = Object.entries(event.extra ?? {}).flatMap(([key, value]) => [
    key,
    typeof value === "string" || typeof value === "number" || typeof value === "boolean"
      ? String(value)
      : JSON.stringify(value),
  ]);

  return [
    event.action,
    event.origin,
    event.actor != null ? String(event.actor) : null,
    ...itemText,
    ...extraText,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}
