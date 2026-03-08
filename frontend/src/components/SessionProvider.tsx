import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type SessionPayload } from "@/lib/api";
import { getPublicConfig } from "@/lib/config";
import { translations, type SupportedLanguage, type TranslationKey } from "@/lib/i18n";

interface SessionContextValue {
  session: SessionPayload | null;
  isLoading: boolean;
  error: ApiError | null;
  isAuthenticated: boolean;
  language: SupportedLanguage;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
  setLanguage: (language: SupportedLanguage) => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

function formatMessage(
  language: SupportedLanguage,
  key: TranslationKey,
  params?: Record<string, string | number>,
): string {
  const template = translations[language][key] ?? translations.en[key];
  if (!params) {
    return template;
  }
  return Object.entries(params).reduce(
    (message, [name, value]) => message.replace(`{${name}}`, String(value)),
    template,
  );
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const publicConfig = getPublicConfig();
  const [languageOverride, setLanguageOverride] = useState<SupportedLanguage | null>(null);

  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: api.getSession,
    retry: false,
  });

  const setLanguageMutation = useMutation({
    mutationFn: async (language: SupportedLanguage) => {
      await api.setLanguage(language);
      return language;
    },
    onSuccess: async (language) => {
      setLanguageOverride(language);
      await queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });

  const logoutMutation = useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
      setLanguageOverride(null);
      await queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });

  const session = sessionQuery.data ?? null;
  const error =
    sessionQuery.error instanceof ApiError ? sessionQuery.error : null;
  const language = (
    languageOverride ??
    session?.language ??
    publicConfig.defaultLanguage ??
    "en"
  ) as SupportedLanguage;

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      isLoading: sessionQuery.isLoading,
      error,
      isAuthenticated: Boolean(session),
      language,
      t: (key, params) => formatMessage(language, key, params),
      setLanguage: async (nextLanguage) => {
        await setLanguageMutation.mutateAsync(nextLanguage);
      },
      logout: async () => {
        await logoutMutation.mutateAsync();
      },
    }),
    [
      error,
      language,
      logoutMutation,
      session,
      sessionQuery.isLoading,
      setLanguageMutation,
    ],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return context;
}
