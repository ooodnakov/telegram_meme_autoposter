import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import MediaGroupCard from "@/components/MediaGroupCard";
import PagePagination from "@/components/PagePagination";
import { ErrorState, LoadingState } from "@/components/PageState";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";

const SuggestionsPage = () => {
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();
  const { t } = useSession();

  const query = useQuery({
    queryKey: ["suggestions", page],
    queryFn: () => api.getSuggestions(page),
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
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {t("totalItems", { count: query.data.total_items })}
        </p>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
          {t("refresh")}
        </Button>
      </div>

      {query.data.items.length === 0 ? (
        <LoadingState label={t("noSuggestions")} />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
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
