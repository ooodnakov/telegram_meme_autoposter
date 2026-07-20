import { useEffect, useState } from "react";
import ContentLayoutSelect, {
  type ContentLayoutMode,
} from "@/components/ContentLayoutSelect";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lightbulb } from "lucide-react";
import { toast } from "sonner";
import DestructiveActionDialog from "@/components/DestructiveActionDialog";
import MediaGroupCard from "@/components/MediaGroupCard";
import PagePagination from "@/components/PagePagination";
import { ErrorState, LoadingState } from "@/components/PageState";
import SectionHeader from "@/components/SectionHeader";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";

const SuggestionsPage = () => {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  const [layoutMode, setLayoutMode] = useState<ContentLayoutMode>("comfortable");
  const queryClient = useQueryClient();
  const { t } = useSession();

  useEffect(() => {
    setPage(1);
  }, [sort]);

  const query = useQuery({
    queryKey: ["suggestions", page, sort],
    queryFn: () => api.getSuggestions(page, sort),
  });

  const mutation = useMutation({
    mutationFn: (payload: { action: string; paths: string[] }) =>
      api.postAction({
        action: payload.action,
        origin: "suggestions",
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
        badge={t("suggestions")}
        title={t("pendingSuggestions")}
        description={t("totalItems", { count: query.data.total_items })}
        icon={Lightbulb}
        actions={
          <div className="flex items-center gap-2">
            <ContentLayoutSelect value={layoutMode} onChange={setLayoutMode} />
            <Select value={sort} onValueChange={(value: "newest" | "oldest") => setSort(value)}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="newest">{t("newestFirst")}</SelectItem>
                <SelectItem value="oldest">{t("oldestFirst")}</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
              {t("refresh")}
            </Button>
          </div>
        }
      />

      {query.data.items.length === 0 ? (
        <LoadingState label={t("noSuggestions")} />
      ) : (
        <div
          className={`grid grid-cols-1 ${
            layoutMode === "list"
              ? "gap-4"
              : layoutMode === "compact"
                ? "gap-3 md:grid-cols-2 2xl:grid-cols-3"
                : "gap-4 xl:grid-cols-2"
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
                  <DestructiveActionDialog
                    title={t("rejectConfirmTitle")}
                    description={t("rejectConfirmDescription")}
                    confirmLabel={t("reject")}
                    onConfirm={() =>
                      mutation.mutate({
                        action: "notok",
                        paths: group.items.map((item) => item.path),
                      })
                    }
                    trigger={
                      <Button size="sm" variant="destructive">
                        {t("reject")}
                      </Button>
                    }
                  />
                </>
              }
            />
          ))}
        </div>
      )}

      <PagePagination
        page={query.data.page}
        totalPages={query.data.total_pages}
        onPageChange={setPage}
      />
    </div>
  );
};

export default SuggestionsPage;
