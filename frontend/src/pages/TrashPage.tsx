import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import MediaGroupCard from "@/components/MediaGroupCard";
import PagePagination from "@/components/PagePagination";
import { ErrorState, LoadingState } from "@/components/PageState";
import SectionHeader from "@/components/SectionHeader";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api } from "@/lib/api";

const TrashPage = () => {
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();
  const { t } = useSession();

  const query = useQuery({
    queryKey: ["trash", page],
    queryFn: () => api.getTrash(page),
  });

  const restoreMutation = useMutation({
    mutationFn: (paths: string[]) => api.restoreTrash(paths),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (paths: string[]) => api.deleteTrash(paths),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
    onError: (error: Error) => toast.error(error.message),
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
        badge={t("trash")}
        title={t("trashItems")}
        description={t("totalItems", { count: query.data.total_items })}
        icon={Trash2}
        tone="destructive"
        actions={
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            {t("refresh")}
          </Button>
        }
      />

      {query.data.items.length === 0 ? (
        <LoadingState label={t("noTrash")} />
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
                      restoreMutation.mutate(group.items.map((item) => item.path))
                    }
                  >
                    {t("restore")}
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() =>
                      deleteMutation.mutate(group.items.map((item) => item.path))
                    }
                  >
                    {t("deleteForever")}
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

export default TrashPage;
