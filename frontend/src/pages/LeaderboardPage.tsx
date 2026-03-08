import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import DataTable from "@/components/DataTable";
import { ErrorState, LoadingState } from "@/components/PageState";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";
import { api, type LeaderboardEntry } from "@/lib/api";

const LeaderboardPage = () => {
  const queryClient = useQueryClient();
  const { t } = useSession();

  const query = useQuery({
    queryKey: ["leaderboard"],
    queryFn: api.getLeaderboard,
  });

  const resetMutation = useMutation({
    mutationFn: api.resetLeaderboard,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      toast.success(t("resetDone"));
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

  const renderTable = (rows: LeaderboardEntry[]) => (
    <DataTable
      headers={[t("rank"), t("source"), t("submissions"), t("approved"), t("rejected")]}
      rows={rows.map((row, index) => [
        index + 1,
        row.source,
        row.submissions,
        `${row.approved} (${row.approved_pct.toFixed(1)}%)`,
        `${row.rejected} (${row.rejected_pct.toFixed(1)}%)`,
      ])}
    />
  );

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{t("leaderboard")}</p>
        <Button variant="outline" onClick={() => resetMutation.mutate()}>
          {t("resetLeaderboard")}
        </Button>
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">{t("submissions")}</h3>
        {renderTable(query.data.submissions)}
      </div>
      <div className="space-y-3">
        <h3 className="text-sm font-semibold">{t("approved")}</h3>
        {renderTable(query.data.approved)}
      </div>
      <div className="space-y-3">
        <h3 className="text-sm font-semibold">{t("rejected")}</h3>
        {renderTable(query.data.rejected)}
      </div>
    </div>
  );
};

export default LeaderboardPage;
