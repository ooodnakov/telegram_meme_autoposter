import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Hand, Lightbulb, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { ErrorState, LoadingState } from "@/components/PageState";
import SectionHeader from "@/components/SectionHeader";
import { useSession } from "@/components/SessionProvider";
import SwipeModerationDeck from "@/components/SwipeModerationDeck";
import { Button } from "@/components/ui/button";
import { useIsMobile } from "@/hooks/use-mobile";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { api } from "@/lib/api";

const SwipeReviewPage = () => {
  const [tab, setTab] = useState<"suggestions" | "posts">("suggestions");
  const { t } = useSession();
  const isMobile = useIsMobile();
  const queryClient = useQueryClient();

  const suggestionsQuery = useQuery({
    queryKey: ["swipe-review", "suggestions"],
    queryFn: () => api.getSuggestions(1),
  });
  const postsQuery = useQuery({
    queryKey: ["swipe-review", "posts"],
    queryFn: () => api.getPosts(1),
  });

  const mutation = useMutation({
    mutationFn: (payload: {
      action: "notok" | "schedule" | "push" | "ok";
      origin: "suggestions" | "posts";
      paths: string[];
    }) => api.postAction(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const activeQuery = tab === "suggestions" ? suggestionsQuery : postsQuery;
  const suggestionsGroups = suggestionsQuery.data?.items ?? [];
  const postsGroups = postsQuery.data?.items ?? [];

  if (activeQuery.isLoading && !activeQuery.data) {
    return <LoadingState label={t("loading")} />;
  }

  if (activeQuery.isError && !activeQuery.data) {
    return (
      <ErrorState
        message={t("errorPrefix", { message: activeQuery.error?.message ?? "Unknown error" })}
        retryLabel={t("retry")}
        onRetry={() => void activeQuery.refetch()}
      />
    );
  }

  return (
    <div className="space-y-6">
      {isMobile ? (
        <div className="flex items-center justify-between gap-3 rounded-[1.75rem] border border-border/60 bg-card/70 px-4 py-3 backdrop-blur-xl">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <div className="rounded-2xl bg-primary/12 p-2 text-primary">
                <Hand className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-base font-semibold">{t("swipeReview")}</p>
                <p className="text-xs text-muted-foreground">
                  {tab === "suggestions"
                    ? t("swipeSuggestionsHint", {
                        count: suggestionsQuery.data?.total_items ?? 0,
                      })
                    : t("swipePostsHint", {
                        count: postsQuery.data?.total_items ?? 0,
                      })}
                </p>
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant={tab === "suggestions" ? "default" : "outline"}
              size="sm"
              onClick={() => setTab("suggestions")}
            >
              {t("suggestions")}
            </Button>
            <Button
              variant={tab === "posts" ? "default" : "outline"}
              size="sm"
              onClick={() => setTab("posts")}
            >
              {t("posts")}
            </Button>
          </div>
        </div>
      ) : (
        <>
          <SectionHeader
            badge={t("swipeReview")}
            title={t("swipeReviewTitle")}
            description={t("swipeReviewDescription")}
            icon={Hand}
            actions={
              <>
                <Button
                  variant={tab === "suggestions" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setTab("suggestions")}
                >
                  {t("suggestions")}
                </Button>
                <Button
                  variant={tab === "posts" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setTab("posts")}
                >
                  {t("posts")}
                </Button>
              </>
            }
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="glass-card p-4">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl bg-warning/10 p-2 text-warning">
                  <Lightbulb className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-semibold">{t("suggestions")}</p>
                  <p className="text-sm text-muted-foreground">
                    {t("swipeSuggestionsHint", {
                      count: suggestionsQuery.data?.total_items ?? 0,
                    })}
                  </p>
                </div>
              </div>
            </div>

            <div className="glass-card p-4">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl bg-primary/10 p-2 text-primary">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-semibold">{t("posts")}</p>
                  <p className="text-sm text-muted-foreground">
                    {t("swipePostsHint", {
                      count: postsQuery.data?.total_items ?? 0,
                    })}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      <Tabs value={tab} onValueChange={(value) => setTab(value as "suggestions" | "posts")}>
        <TabsContent value="suggestions" className="mt-0">
          <SwipeModerationDeck
            emptyLabel={t("noSuggestions")}
            groups={suggestionsGroups}
            isFetching={suggestionsQuery.isFetching}
            isMutating={mutation.isPending}
            onRefresh={() => void suggestionsQuery.refetch()}
            onAction={(action, paths) =>
              mutation.mutate({
                action,
                origin: "suggestions",
                paths,
              })
            }
          />
        </TabsContent>
        <TabsContent value="posts" className="mt-0">
          <SwipeModerationDeck
            emptyLabel={t("noPosts")}
            groups={postsGroups}
            isFetching={postsQuery.isFetching}
            isMutating={mutation.isPending}
            onRefresh={() => void postsQuery.refetch()}
            onAction={(action, paths) =>
              mutation.mutate({
                action,
                origin: "posts",
                paths,
              })
            }
          />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default SwipeReviewPage;
