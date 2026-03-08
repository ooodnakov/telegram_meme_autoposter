import { useEffect, useRef } from "react";
import { Send } from "lucide-react";
import { useSession } from "@/components/SessionProvider";
import { getPublicConfig } from "@/lib/config";

const LoginPage = () => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { t } = useSession();
  const { botUsername } = getPublicConfig();

  useEffect(() => {
    if (!botUsername || !containerRef.current) {
      return;
    }

    containerRef.current.innerHTML = "";
    const script = document.createElement("script");
    script.async = true;
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-auth-url", `${window.location.origin}/auth`);
    script.setAttribute("data-request-access", "write");
    containerRef.current.appendChild(script);
  }, [botUsername]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen max-w-5xl items-center px-6 py-12">
        <div className="grid w-full gap-10 rounded-[32px] border border-border/60 bg-card/80 p-8 shadow-2xl backdrop-blur-xl lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-6">
            <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/15">
              <Send className="h-6 w-6 text-primary" />
            </div>
            <div className="space-y-3">
              <h1 className="text-4xl font-semibold tracking-tight">
                {t("loginTitle")}
              </h1>
              <p className="max-w-lg text-sm text-muted-foreground">
                {t("loginSubtitle")}
              </p>
            </div>
          </div>

          <div className="glass-card flex min-h-[320px] flex-col items-center justify-center gap-5 p-8">
            <div ref={containerRef} />
            {!botUsername ? (
              <p className="text-center text-sm text-destructive">
                Telegram bot username is not configured.
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
