import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Files, SlidersHorizontal, Users } from "lucide-react";
import { toast } from "sonner";
import EventFeed from "@/components/EventFeed";
import PagePagination from "@/components/PagePagination";
import { ErrorState, LoadingState } from "@/components/PageState";
import SectionHeader from "@/components/SectionHeader";
import StatCard from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";
import { buildEventSearchText } from "@/lib/event-log";

const EventsPage = () => {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    q: "",
    origin: "all",
  });
  const queryClient = useQueryClient();
  const { t } = useSession();
  const deferredQuery = useDeferredValue(filters.q.trim().toLowerCase());

  useEffect(() => {
    setPage(1);
  }, [deferredQuery, filters.origin]);

  const query = useQuery({
    queryKey: ["events", page],
    queryFn: () => api.getEvents(page),
    placeholderData: (previousData) => previousData,
  });
  const events = query.data?.items;

  const resetMutation = useMutation({
    mutationFn: api.resetEvents,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      toast.success(t("resetDone"));
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const origins = useMemo(
    () => {
      const items = events ?? [];
      return Array.from(
        new Set(items.map((event) => event.origin).filter(Boolean) as string[]),
      ).sort((left, right) => left.localeCompare(right));
    },
    [events],
  );

  const filteredEvents = useMemo(
    () => {
      const items = events ?? [];
      return items.filter((event) => {
        if (filters.origin !== "all" && event.origin !== filters.origin) {
          return false;
        }

        if (deferredQuery.length > 0 && !buildEventSearchText(event).includes(deferredQuery)) {
          return false;
        }

        return true;
      });
    },
    [deferredQuery, events, filters.origin],
  );

  const activeFilters = deferredQuery.length > 0 || filters.origin !== "all";
  const affectedItems = filteredEvents.reduce((total, event) => total + event.items.length, 0);
  const uniqueActors = new Set(
    filteredEvents
      .map((event) => event.actor)
      .filter((actor): actor is string | number => actor != null && actor !== ""),
  ).size;

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

  return (
    <div className="space-y-6">
      <SectionHeader
        badge={t("events")}
        title={t("recentEvents")}
        description={
          activeFilters
            ? t("matchingEvents", { count: filteredEvents.length })
            : `${t("totalItems", { count: query.data.total_items })} · ${t("pageOf", {
                page: query.data.page,
                total: query.data.total_pages,
              })}`
        }
        icon={Activity}
        actions={
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setFilters({
                  q: "",
                  origin: "all",
                })
              }
              disabled={!activeFilters}
            >
              {t("clearFilters")}
            </Button>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
              {t("refresh")}
            </Button>
            <Button variant="outline" size="sm" onClick={() => resetMutation.mutate()}>
              {t("clearHistory")}
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title={t("loggedActions")}
          value={filteredEvents.length}
          icon={Activity}
          description={
            activeFilters
              ? t("matchingEvents", { count: filteredEvents.length })
              : t("totalItems", { count: query.data.total_items })
          }
        />
        <StatCard
          title={t("affectedItems")}
          value={affectedItems}
          icon={Files}
          description={t("pageOf", { page: query.data.page, total: query.data.total_pages })}
        />
        <StatCard
          title={t("uniqueActors")}
          value={uniqueActors}
          icon={Users}
          description={t("count") + `: ${events?.length ?? 0}`}
        />
      </div>

      <div className="glass-card p-4">
        <SectionHeader
          as="div"
          badge={t("events")}
          title={t("search")}
          description={t("searchLogsPlaceholder")}
          icon={SlidersHorizontal}
          tone="neutral"
          compact
          className="mb-4"
        />

        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("search")}
            </span>
            <Input
              value={filters.q}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  q: event.target.value,
                }))
              }
              placeholder={t("searchLogsPlaceholder")}
            />
          </label>

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("origin")}
            </span>
            <Select
              value={filters.origin}
              onValueChange={(value) =>
                setFilters((current) => ({
                  ...current,
                  origin: value,
                }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder={t("allOrigins")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("allOrigins")}</SelectItem>
                {origins.map((origin) => (
                  <SelectItem key={origin} value={origin}>
                    {origin}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        </div>
      </div>

      <EventFeed
        events={filteredEvents}
        emptyMessage={t("noEventsYet")}
        denseDesktop
      />

      <PagePagination
        page={query.data.page}
        totalPages={query.data.total_pages}
        onPageChange={setPage}
      />
    </div>
  );
};

export default EventsPage;
