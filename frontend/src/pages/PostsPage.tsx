import { useDeferredValue, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, SlidersHorizontal } from "lucide-react";
import { toast } from "sonner";
import MediaGroupCard from "@/components/MediaGroupCard";
import PagePagination from "@/components/PagePagination";
import { ErrorState, LoadingState } from "@/components/PageState";
import SectionHeader from "@/components/SectionHeader";
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
import { api, type PostsFilters } from "@/lib/api";

const PostsPage = () => {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<PostsFilters>({
    q: "",
    kind: "all",
    layout: "all",
    source: "all",
  });
  const queryClient = useQueryClient();
  const { t } = useSession();
  const deferredQuery = useDeferredValue(filters.q.trim());
  const activeFilters =
    deferredQuery.length > 0 ||
    filters.kind !== "all" ||
    filters.layout !== "all" ||
    filters.source !== "all";

  useEffect(() => {
    setPage(1);
  }, [deferredQuery, filters.kind, filters.layout, filters.source]);

  const query = useQuery({
    queryKey: ["posts", page, deferredQuery, filters.kind, filters.layout, filters.source],
    queryFn: () =>
      api.getPosts(page, {
        q: deferredQuery,
        kind: filters.kind,
        layout: filters.layout,
        source: filters.source,
      }),
    placeholderData: (previousData) => previousData,
  });

  const mutation = useMutation({
    mutationFn: (payload: { action: string; paths: string[] }) =>
      api.postAction({
        action: payload.action,
        origin: "posts",
        paths: payload.paths,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
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

  return (
    <div className="space-y-6">
      <SectionHeader
        badge={t("posts")}
        title={t("pendingPosts")}
        description={
          activeFilters
            ? t("filteredItems", { count: query.data.total_items })
            : t("totalItems", { count: query.data.total_items })
        }
        icon={FileText}
        actions={
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setFilters({
                  q: "",
                  kind: "all",
                  layout: "all",
                  source: "all",
                })
              }
              disabled={!activeFilters}
            >
              {t("clearFilters")}
            </Button>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
              {t("refresh")}
            </Button>
          </>
        }
      />

      <div className="glass-card p-4">
        <SectionHeader
          as="div"
          badge={t("posts")}
          title={t("search")}
          description={t("searchPostsPlaceholder")}
          icon={SlidersHorizontal}
          tone="neutral"
          compact
          className="mb-4"
        />

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
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
              placeholder={t("searchPostsPlaceholder")}
            />
          </label>

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("source")}
            </span>
            <Select
              value={filters.source}
              onValueChange={(value) =>
                setFilters((current) => ({
                  ...current,
                  source: value,
                }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder={t("allSources")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("allSources")}</SelectItem>
                {query.data.filters.sources.map((source) => (
                  <SelectItem key={source} value={source}>
                    {source}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("mediaType")}
            </span>
            <Select
              value={filters.kind}
              onValueChange={(value: PostsFilters["kind"]) =>
                setFilters((current) => ({
                  ...current,
                  kind: value,
                }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder={t("allMedia")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("allMedia")}</SelectItem>
                <SelectItem value="image">{t("imageOnly")}</SelectItem>
                <SelectItem value="video">{t("videoOnly")}</SelectItem>
              </SelectContent>
            </Select>
          </label>

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("layout")}
            </span>
            <Select
              value={filters.layout}
              onValueChange={(value: PostsFilters["layout"]) =>
                setFilters((current) => ({
                  ...current,
                  layout: value,
                }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder={t("allLayouts")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("allLayouts")}</SelectItem>
                <SelectItem value="single">{t("singlePosts")}</SelectItem>
                <SelectItem value="group">{t("groupedPosts")}</SelectItem>
              </SelectContent>
            </Select>
          </label>
        </div>
      </div>

      <div className="space-y-3">
        {query.isFetching ? (
          <p className="text-xs text-muted-foreground">{t("loading")}</p>
        ) : null}

        {query.data.items.length === 0 ? (
          <LoadingState label={activeFilters ? t("noPostsMatchFilters") : t("noPosts")} />
        ) : (
          <div className="relative">
            <div
              className={`grid grid-cols-1 gap-4 transition-opacity xl:grid-cols-2 ${
                query.isFetching ? "opacity-60" : "opacity-100"
              }`}
            >
              {query.data.items.map((group) => (
                <MediaGroupCard
                  key={group.items.map((item) => item.path).join("|")}
                  group={group}
                  actions={
                    <>
                      <Button
                        size="sm"
                        onClick={() =>
                          mutation.mutate({
                            action: "ok",
                            paths: group.items.map((item) => item.path),
                          })
                        }
                      >
                        {t("sendToBatch")}
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          mutation.mutate({
                            action: "schedule",
                            paths: group.items.map((item) => item.path),
                          })
                        }
                      >
                        {t("schedule")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          mutation.mutate({
                            action: "push",
                            paths: group.items.map((item) => item.path),
                          })
                        }
                      >
                        {t("pushNow")}
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() =>
                          mutation.mutate({
                            action: "notok",
                            paths: group.items.map((item) => item.path),
                          })
                        }
                      >
                        {t("reject")}
                      </Button>
                    </>
                  }
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <PagePagination
        page={query.data.page}
        totalPages={query.data.total_pages}
        onPageChange={setPage}
      />
    </div>
  );
};

export default PostsPage;
