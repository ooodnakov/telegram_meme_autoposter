import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Layers,
  Play,
  RefreshCw,
  Send,
  Trash2,
  UserRound,
} from "lucide-react";
import { useSession } from "@/components/SessionProvider";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { useIsMobile } from "@/hooks/use-mobile";
import { cn } from "@/lib/utils";
import type { MediaAsset, MediaGroup } from "@/lib/api";

type SwipeAction = "notok" | "schedule" | "push" | "ok";
type SwipeDirection = "left" | "right" | "up" | "down";

const PREVIEW_THRESHOLD = 36;
const COMMIT_THRESHOLD = 120;
const TAP_THRESHOLD = 8;

const swipeDirections: Array<{
  action: SwipeAction;
  direction: SwipeDirection;
  icon: typeof ArrowLeft;
  tone: string;
}> = [
  {
    action: "notok",
    direction: "left",
    icon: ArrowLeft,
    tone: "border-destructive/50 bg-destructive/12 text-destructive",
  },
  {
    action: "schedule",
    direction: "right",
    icon: ArrowRight,
    tone: "border-warning/50 bg-warning/12 text-warning",
  },
  {
    action: "push",
    direction: "up",
    icon: ArrowUp,
    tone: "border-primary/50 bg-primary/12 text-primary",
  },
  {
    action: "ok",
    direction: "down",
    icon: ArrowDown,
    tone: "border-success/50 bg-success/12 text-success",
  },
];

function getActionLabel(
  action: SwipeAction,
  t: (key: string, params?: Record<string, string | number>) => string,
) {
  if (action === "notok") {
    return t("reject");
  }
  if (action === "schedule") {
    return t("schedule");
  }
  if (action === "push") {
    return t("pushNow");
  }
  return t("sendToBatch");
}

function getDirectionLabel(
  direction: SwipeDirection,
  t: (key: string, params?: Record<string, string | number>) => string,
) {
  if (direction === "left") {
    return t("swipeLeft");
  }
  if (direction === "right") {
    return t("swipeRight");
  }
  if (direction === "up") {
    return t("swipeUp");
  }
  return t("swipeDown");
}

function resolveSwipeAction(x: number, y: number): SwipeAction | null {
  if (Math.abs(x) >= Math.abs(y) && Math.abs(x) >= PREVIEW_THRESHOLD) {
    return x < 0 ? "notok" : "schedule";
  }
  if (Math.abs(y) >= PREVIEW_THRESHOLD) {
    return y < 0 ? "push" : "ok";
  }
  return null;
}

function getDismissOffset(action: SwipeAction) {
  if (action === "notok") {
    return { x: -560, y: 0 };
  }
  if (action === "schedule") {
    return { x: 560, y: 0 };
  }
  if (action === "push") {
    return { x: 0, y: -520 };
  }
  return { x: 0, y: 520 };
}

function buildIdentity(group: MediaGroup, t: (key: string, params?: Record<string, string | number>) => string) {
  if (group.submitter?.is_admin && group.submitter.source) {
    return `${group.submitter.source} (${t("admin")})`;
  }
  if (group.submitter?.user_id) {
    return t("userId", { id: group.submitter.user_id });
  }
  if (group.source) {
    return group.source;
  }
  return t("unknown");
}

function getAvatarText(group: MediaGroup, t: (key: string, params?: Record<string, string | number>) => string) {
  const source = group.source?.trim();
  if (source) {
    return source.replace(/^@/, "").slice(0, 2).toUpperCase();
  }
  if (group.submitter?.user_id) {
    return String(group.submitter.user_id).slice(-2);
  }
  return t("unknown").slice(0, 2).toUpperCase();
}

function getPreviewItem(group: MediaGroup | undefined) {
  return group?.items.find((item) => item.kind === "image") ?? group?.items[0] ?? null;
}

function preloadImages(groups: MediaGroup[]) {
  const warmers: HTMLImageElement[] = [];
  groups.slice(0, 3).forEach((group, groupIndex) => {
    const items = groupIndex === 0 ? group.items : group.items.slice(0, 2);
    items.forEach((item) => {
      if (item.kind !== "image") {
        return;
      }
      const image = new Image();
      image.src = item.url;
      warmers.push(image);
    });
  });
  return () => {
    warmers.forEach((image) => {
      image.src = "";
    });
  };
}

interface SwipeModerationDeckProps {
  emptyLabel: string;
  groups: MediaGroup[];
  isFetching: boolean;
  isMutating: boolean;
  onAction: (action: SwipeAction, paths: string[]) => void;
  onRefresh: () => void;
}

const SwipeModerationDeck = ({
  emptyLabel,
  groups,
  isFetching,
  isMutating,
  onAction,
  onRefresh,
}: SwipeModerationDeckProps) => {
  const { t } = useSession();
  const isMobile = useIsMobile();
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [dismissedAction, setDismissedAction] = useState<SwipeAction | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [previewAsset, setPreviewAsset] = useState<MediaAsset | null>(null);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const pointerIdRef = useRef<number | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const movedRef = useRef(false);
  const activeGroup = groups[0];
  const nextGroups = groups.slice(1, 3);
  const activeItem = activeGroup?.items[Math.min(selectedIndex, (activeGroup?.items.length ?? 1) - 1)];
  const previewAction = dismissedAction ?? resolveSwipeAction(dragOffset.x, dragOffset.y);
  const isBusy = isMutating || dismissedAction !== null;

  useEffect(() => {
    if (!activeGroup) {
      return;
    }
    return preloadImages(groups);
  }, [groups, activeGroup?.group_id, activeGroup?.items[0]?.path]);

  useEffect(() => {
    setDragOffset({ x: 0, y: 0 });
    setDismissedAction(null);
    setSelectedIndex(0);
    movedRef.current = false;
    startRef.current = null;
    pointerIdRef.current = null;
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, [activeGroup?.group_id, activeGroup?.items[0]?.path]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const profileBadges = useMemo(() => {
    if (!activeGroup) {
      return [];
    }
    const badges: string[] = [];
    if (activeGroup.source) {
      badges.push(t("submittedVia", { source: activeGroup.source }));
    }
    if (activeGroup.is_group) {
      badges.push(t("totalItems", { count: activeGroup.count }));
    }
    if (activeGroup.items.length > 1) {
      badges.push(`${selectedIndex + 1}/${activeGroup.items.length}`);
    }
    return badges;
  }, [activeGroup, selectedIndex, t]);

  function resetDrag() {
    setDragOffset({ x: 0, y: 0 });
    startRef.current = null;
    pointerIdRef.current = null;
    movedRef.current = false;
  }

  function commitAction(action: SwipeAction) {
    if (!activeGroup || isBusy) {
      return;
    }
    setDismissedAction(action);
    setDragOffset(getDismissOffset(action));
    timeoutRef.current = window.setTimeout(() => {
      onAction(
        action,
        activeGroup.items.map((item) => item.path),
      );
    }, 140);
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLElement>) {
    if (!activeGroup || isBusy) {
      return;
    }
    if (event.button !== 0) {
      return;
    }

    const target = event.target;
    if (target instanceof HTMLElement && target.closest("button, a, video")) {
      return;
    }

    pointerIdRef.current = event.pointerId;
    startRef.current = { x: event.clientX, y: event.clientY };
    movedRef.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLElement>) {
    if (pointerIdRef.current !== event.pointerId || !startRef.current || isBusy) {
      return;
    }
    const nextOffset = {
      x: event.clientX - startRef.current.x,
      y: event.clientY - startRef.current.y,
    };
    if (Math.abs(nextOffset.x) > TAP_THRESHOLD || Math.abs(nextOffset.y) > TAP_THRESHOLD) {
      movedRef.current = true;
    }
    setDragOffset(nextOffset);
  }

  function handlePointerEnd(event: ReactPointerEvent<HTMLElement>) {
    if (pointerIdRef.current !== event.pointerId) {
      return;
    }

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    const action = resolveSwipeAction(dragOffset.x, dragOffset.y);
    const horizontalCommit =
      Math.abs(dragOffset.x) >= Math.abs(dragOffset.y) &&
      Math.abs(dragOffset.x) >= COMMIT_THRESHOLD;
    const verticalCommit =
      Math.abs(dragOffset.y) > Math.abs(dragOffset.x) &&
      Math.abs(dragOffset.y) >= COMMIT_THRESHOLD;

    if (action && (horizontalCommit || verticalCommit)) {
      commitAction(action);
      return;
    }

    resetDrag();
  }

  function handleKeyboard(event: KeyboardEvent<HTMLElement>) {
    if (isBusy) {
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      commitAction("notok");
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      commitAction("schedule");
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      commitAction("push");
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      commitAction("ok");
    }
  }

  function openPreview(item: MediaAsset) {
    if (movedRef.current || item.kind !== "image") {
      return;
    }
    setPreviewAsset(item);
  }

  if (!activeGroup || !activeItem) {
    return (
      <div className="glass-card p-10 text-center">
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
        <Button
          variant="outline"
          className="mt-4 gap-2"
          onClick={onRefresh}
          disabled={isFetching}
        >
          <RefreshCw className={cn("h-4 w-4", isFetching ? "animate-spin" : "")} />
          {t("refresh")}
        </Button>
      </div>
    );
  }

  const cardRotation = dragOffset.x / 26;
  const identity = buildIdentity(activeGroup, t);
  const avatarText = getAvatarText(activeGroup, t);

  return (
    <>
      <Dialog open={previewAsset !== null} onOpenChange={(open) => !open && setPreviewAsset(null)}>
        <DialogContent className="z-[140] w-[98vw] max-w-[98vw] border-none bg-black/95 p-0 shadow-none sm:rounded-2xl">
          <DialogTitle className="sr-only">{previewAsset?.caption ?? previewAsset?.name ?? "Preview"}</DialogTitle>
          <DialogDescription className="sr-only">
            Preview the selected media in full screen.
          </DialogDescription>
          {previewAsset ? (
            <img
              src={previewAsset.url}
              alt={previewAsset.caption ?? previewAsset.name}
              className="max-h-[94vh] w-full rounded-2xl object-contain"
            />
          ) : null}
        </DialogContent>
      </Dialog>

      <div className={cn("grid gap-6", isMobile ? "grid-cols-1" : "xl:grid-cols-[minmax(0,1fr)_21rem]")}>
        <div className="space-y-4">
          {!isMobile ? (
            <div className="grid gap-3 xl:grid-cols-4">
              {swipeDirections.map(({ action, direction, icon: Icon, tone }) => (
                <div key={action} className={cn("rounded-2xl border px-4 py-3", tone)}>
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Icon className="h-4 w-4" />
                    {getDirectionLabel(direction, t)}
                  </div>
                  <p className="mt-1 text-xs opacity-80">{getActionLabel(action, t)}</p>
                </div>
              ))}
            </div>
          ) : null}

          <div
            className={cn(
              "relative mx-auto w-full",
              isMobile ? "min-h-[calc(100vh-11.5rem)] max-w-none" : "min-h-[72vh] max-w-[78rem]",
            )}
          >
            {nextGroups
              .slice()
              .reverse()
              .map((group, index) => {
                const previewItem = getPreviewItem(group);
                if (!previewItem) {
                  return null;
                }
                return (
                  <div
                    key={group.items.map((item) => item.path).join("|")}
                    className={cn(
                      "pointer-events-none absolute inset-0 mx-auto overflow-hidden rounded-[2rem] border border-border/50 bg-card/50 shadow-[0_35px_120px_-70px_hsl(var(--primary)/0.8)] backdrop-blur-md",
                      isMobile ? "top-3 w-[92%]" : "top-5 w-[92%]",
                    )}
                    style={{
                      transform: `translateY(${(index + 1) * (isMobile ? 12 : 22)}px) scale(${0.95 - index * 0.04})`,
                      opacity: 0.38 - index * 0.12,
                      zIndex: 10 - index,
                    }}
                  >
                    <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/10 to-black/60" />
                    {previewItem.kind === "image" ? (
                      <img
                        src={previewItem.url}
                        alt={previewItem.caption ?? previewItem.name}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <video className="h-full w-full object-cover" preload="metadata" src={previewItem.url} />
                    )}
                  </div>
                );
              })}

            <article
              className={cn(
                "absolute inset-0 z-[30] overflow-hidden border border-border/70 bg-[linear-gradient(180deg,hsl(var(--card))_0%,hsl(var(--card)/0.96)_100%)] transition-transform duration-200 ease-out",
                isMobile
                  ? "rounded-[2rem] shadow-[0_18px_80px_-45px_hsl(var(--primary)/0.95)]"
                  : "rounded-[2.4rem] shadow-[0_42px_140px_-72px_hsl(var(--primary)/0.9)]",
                isBusy ? "pointer-events-none opacity-80" : "cursor-grab active:cursor-grabbing",
                previewAction === "notok" && "ring-2 ring-destructive/60",
                previewAction === "schedule" && "ring-2 ring-warning/60",
                previewAction === "push" && "ring-2 ring-primary/60",
                previewAction === "ok" && "ring-2 ring-success/60",
                "touch-none select-none",
              )}
              style={{
                transform: `translate(${dragOffset.x}px, ${dragOffset.y}px) rotate(${cardRotation}deg)`,
              }}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerEnd}
              onPointerCancel={handlePointerEnd}
              onKeyDown={handleKeyboard}
              tabIndex={0}
            >
              <div className="relative flex h-full flex-col">
                <div className="absolute left-4 top-4 z-20 flex flex-wrap gap-2">
                  <div className="rounded-full bg-black/45 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-white backdrop-blur">
                    {tabDirectionLabel(previewAction, t)}
                  </div>
                  <div className="rounded-full bg-black/45 px-3 py-1 text-[11px] font-semibold text-white/90 backdrop-blur">
                    {groups.length}
                  </div>
                </div>

                <div className="relative flex-1 overflow-hidden">
                  {activeItem.kind === "image" ? (
                    <>
                      <img
                        src={activeItem.url}
                        alt={activeItem.caption ?? activeItem.name}
                        className="absolute inset-0 h-full w-full scale-110 object-cover opacity-25 blur-3xl"
                        aria-hidden="true"
                      />
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_transparent_0%,rgba(0,0,0,0.14)_38%,rgba(0,0,0,0.9)_100%)]" />
                      <div className="relative flex h-full items-center justify-center px-3 pb-28 pt-16 md:px-8 md:pb-36 md:pt-20">
                        <img
                          src={activeItem.url}
                          alt={activeItem.caption ?? activeItem.name}
                          className={cn(
                            "max-h-full max-w-full rounded-[1.8rem] object-contain shadow-[0_20px_70px_-40px_rgba(0,0,0,0.95)]",
                            isMobile ? "cursor-zoom-in" : "cursor-zoom-in",
                          )}
                          draggable={false}
                          onClick={() => openPreview(activeItem)}
                        />
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(0,122,255,0.18)_0%,rgba(0,0,0,0.88)_72%)]" />
                      <div className="relative flex h-full items-center justify-center px-3 pb-28 pt-16 md:px-8 md:pb-36 md:pt-20">
                        <video
                          className="max-h-full max-w-full rounded-[1.8rem] object-contain shadow-[0_20px_70px_-40px_rgba(0,0,0,0.95)]"
                          controls
                          preload="metadata"
                          src={activeItem.url}
                        />
                      </div>
                    </>
                  )}

                  {activeGroup.items.length > 1 ? (
                    <div className="absolute right-3 top-16 z-20 flex max-w-[34%] flex-col gap-2 md:right-4 md:top-20">
                      {activeGroup.items.slice(0, 4).map((item, index) => (
                        <button
                          key={item.path}
                          type="button"
                          className={cn(
                            "overflow-hidden rounded-2xl border border-white/15 bg-black/35 backdrop-blur transition",
                            index === selectedIndex ? "scale-[1.02] border-primary/70 shadow-[0_0_0_1px_rgba(255,255,255,0.16)]" : "opacity-75 hover:opacity-100",
                          )}
                          onClick={() => setSelectedIndex(index)}
                        >
                          <div className="relative aspect-[4/5] w-16 md:w-20">
                            {item.kind === "image" ? (
                              <img
                                src={item.url}
                                alt={item.caption ?? item.name}
                                className="h-full w-full object-cover"
                              />
                            ) : (
                              <>
                                <video className="h-full w-full object-cover" preload="metadata" src={item.url} />
                                <div className="absolute inset-0 flex items-center justify-center bg-black/45 text-white">
                                  <Play className="h-4 w-4" />
                                </div>
                              </>
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : null}

                  <div className="absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-black via-black/72 to-transparent px-4 pb-4 pt-20 md:px-6 md:pb-6">
                    <div className="flex items-end gap-3">
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/10 text-sm font-semibold text-white backdrop-blur">
                        {avatarText || <UserRound className="h-5 w-5" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-2xl font-semibold tracking-tight text-white md:text-3xl">
                            {activeGroup.source || identity}
                          </h3>
                          <span className="rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[11px] font-medium text-white/80">
                            {identity}
                          </span>
                        </div>
                        <p className="mt-2 max-w-3xl text-sm leading-6 text-white/75 md:text-base">
                          {activeGroup.caption || activeItem.caption || activeItem.name}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {profileBadges.map((badge) => (
                            <span
                              key={badge}
                              className="rounded-full border border-white/12 bg-white/10 px-2.5 py-1 text-[11px] font-medium text-white/80 backdrop-blur"
                            >
                              {badge}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {isMobile ? (
                  <div className="absolute inset-x-3 bottom-3 z-30">
                    <div className="grid grid-cols-4 gap-2 rounded-[1.5rem] border border-white/10 bg-black/55 p-2 backdrop-blur-xl">
                      {swipeDirections.map(({ action, icon: Icon, tone }) => (
                        <button
                          key={action}
                          type="button"
                          className={cn(
                            "flex h-14 items-center justify-center rounded-2xl border transition",
                            tone,
                          )}
                          disabled={isBusy}
                          onClick={() => commitAction(action)}
                          aria-label={getActionLabel(action, t)}
                        >
                          <Icon className="h-5 w-5" />
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </article>
          </div>
        </div>

        {!isMobile ? (
          <aside className="glass-card h-fit space-y-4 p-5">
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
                {t("reviewDeck")}
              </p>
              <p className="text-4xl font-semibold tracking-tight">{groups.length}</p>
              <p className="text-sm text-muted-foreground">{t("swipeHelp")}</p>
            </div>

            <div className="grid gap-2">
              <Button
                variant="destructive"
                className="justify-start gap-2"
                disabled={isBusy}
                onClick={() => commitAction("notok")}
              >
                <Trash2 className="h-4 w-4" />
                {getActionLabel("notok", t)}
              </Button>
              <Button
                variant="secondary"
                className="justify-start gap-2"
                disabled={isBusy}
                onClick={() => commitAction("schedule")}
              >
                <ArrowRight className="h-4 w-4" />
                {getActionLabel("schedule", t)}
              </Button>
              <Button
                variant="outline"
                className="justify-start gap-2"
                disabled={isBusy}
                onClick={() => commitAction("push")}
              >
                <Send className="h-4 w-4" />
                {getActionLabel("push", t)}
              </Button>
              <Button
                className="justify-start gap-2"
                disabled={isBusy}
                onClick={() => commitAction("ok")}
              >
                <Layers className="h-4 w-4" />
                {getActionLabel("ok", t)}
              </Button>
            </div>

            <Button
              variant="ghost"
              className="w-full justify-start gap-2"
              disabled={isFetching || isBusy}
              onClick={onRefresh}
            >
              <RefreshCw className={cn("h-4 w-4", isFetching ? "animate-spin" : "")} />
              {t("refresh")}
            </Button>
          </aside>
        ) : null}
      </div>
    </>
  );
};

function tabDirectionLabel(
  action: SwipeAction | null,
  t: (key: string, params?: Record<string, string | number>) => string,
) {
  if (!action) {
    return t("swipeReview");
  }
  if (action === "notok") {
    return getDirectionLabel("left", t);
  }
  if (action === "schedule") {
    return getDirectionLabel("right", t);
  }
  if (action === "push") {
    return getDirectionLabel("up", t);
  }
  return getDirectionLabel("down", t);
}

export default SwipeModerationDeck;
