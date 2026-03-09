import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Settings2 } from "lucide-react";
import { toast } from "sonner";
import { ErrorState, LoadingState } from "@/components/PageState";
import { useSession } from "@/components/SessionProvider";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

function stringifyChannels(channels: string[]): string {
  return channels.join("\n");
}

function parseChannels(value: string): string[] {
  const seen = new Set<string>();
  const channels: string[] = [];

  for (const entry of value.split(/[\n,]/)) {
    const normalized = entry.trim();
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    channels.push(normalized);
  }

  return channels;
}

function ChannelPill({ value }: { value: string }) {
  return (
    <span className="rounded-full border border-border/70 bg-secondary/40 px-3 py-1 text-xs font-medium text-foreground">
      {value}
    </span>
  );
}

const SettingsPage = () => {
  const queryClient = useQueryClient();
  const { t } = useSession();
  const [draft, setDraft] = useState("");

  const query = useQuery({
    queryKey: ["channel-settings"],
    queryFn: api.getChannelSettings,
  });

  useEffect(() => {
    if (query.data) {
      setDraft(stringifyChannels(query.data.selected_chats));
    }
  }, [query.data]);

  const mutation = useMutation({
    mutationFn: (selectedChats: string[]) => api.updateChannelSettings(selectedChats),
    onSuccess: async (payload) => {
      setDraft(stringifyChannels(payload.selected_chats));
      toast.success(t("settingsSaveSuccess"), {
        description: t("settingsSavedCount", {
          count: payload.selected_chats.length,
        }),
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["channel-settings"] }),
        queryClient.invalidateQueries({ queryKey: ["events"] }),
      ]);
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

  const parsedDraft = parseChannels(draft);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.24em] text-primary">
            <Settings2 className="h-3.5 w-3.5" />
            {t("settings")}
          </div>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t("settings")}</h1>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              {t("settingsSubtitle")}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => void query.refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t("refresh")}
          </Button>
          <Button
            variant="outline"
            onClick={() =>
              setDraft(stringifyChannels(query.data.default_selected_chats))
            }
          >
            {t("settingsResetDefaults")}
          </Button>
          <Button
            disabled={mutation.isPending}
            onClick={() => mutation.mutate(parsedDraft)}
          >
            {t("save")}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="border-border/60 bg-card/70">
          <CardHeader className="pb-3">
            <CardDescription>{t("settingsCurrentList")}</CardDescription>
            <CardTitle className="text-3xl">{query.data.selected_chats.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-border/60 bg-card/70">
          <CardHeader className="pb-3">
            <CardDescription>{t("settingsDefaultList")}</CardDescription>
            <CardTitle className="text-3xl">
              {query.data.default_selected_chats.length}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-border/60 bg-card/70">
          <CardHeader className="pb-3">
            <CardDescription>{t("settingsValkeyKey")}</CardDescription>
            <CardTitle className="break-all font-mono text-sm">
              {query.data.valkey_key}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card className="border-border/60 bg-card/80">
        <CardHeader>
          <CardTitle>{t("settingsCurrentList")}</CardTitle>
          <CardDescription>{t("sourceChannelsHint")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={t("sourceChannelsPlaceholder")}
            className="min-h-[240px] font-mono text-sm"
          />
          <div className="flex flex-wrap gap-2">
            {parsedDraft.length > 0 ? (
              parsedDraft.map((channel) => (
                <ChannelPill key={channel} value={channel} />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">{t("settingsEmpty")}</p>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>{t("settingsCurrentList")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {query.data.selected_chats.length > 0 ? (
              query.data.selected_chats.map((channel) => (
                <ChannelPill key={channel} value={channel} />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">{t("settingsEmpty")}</p>
            )}
          </CardContent>
        </Card>

        <Card className="border-border/60 bg-card/70">
          <CardHeader>
            <CardTitle>{t("settingsDefaultList")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {query.data.default_selected_chats.length > 0 ? (
              query.data.default_selected_chats.map((channel) => (
                <ChannelPill key={channel} value={channel} />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">{t("settingsEmpty")}</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default SettingsPage;
