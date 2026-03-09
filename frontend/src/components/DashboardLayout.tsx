import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Clock,
  FileText,
  Languages,
  LayoutDashboard,
  Layers,
  Lightbulb,
  LogOut,
  Menu,
  Send,
  Settings2,
  Trash2,
  Trophy,
  Workflow,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSession } from "@/components/SessionProvider";

const navItems = [
  { path: "/", key: "dashboard", icon: LayoutDashboard },
  { path: "/queue", key: "queue", icon: Clock },
  { path: "/batch", key: "batch", icon: Layers },
  { path: "/suggestions", key: "suggestions", icon: Lightbulb },
  { path: "/posts", key: "posts", icon: FileText },
  { path: "/stats", key: "analytics", icon: BarChart3 },
  { path: "/jobs", key: "jobs", icon: Workflow },
  { path: "/leaderboard", key: "leaderboard", icon: Trophy },
  { path: "/events", key: "events", icon: Activity },
  { path: "/trash", key: "trash", icon: Trash2 },
  { path: "/settings", key: "settings", icon: Settings2 },
] as const;

const DashboardLayout = ({ children }: { children: React.ReactNode }) => {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { session, language, setLanguage, logout, t } = useSession();

  const nextLanguage = language === "ru" ? "en" : "ru";

  return (
    <div className="flex min-h-screen bg-background">
      {sidebarOpen ? (
        <button
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="Close sidebar"
        />
      ) : null}

      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 border-r border-sidebar-border bg-sidebar transition-transform duration-300 lg:static lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-sidebar-border px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15">
              <Send className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-sidebar-accent-foreground">
                Meme Autoposter
              </h1>
              <p className="text-xs text-sidebar-foreground">{t("adminPanel")}</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <nav className="space-y-1 px-3 py-4">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {t(item.key)}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-background/85 px-6 py-4 backdrop-blur-xl">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
                onClick={() => setSidebarOpen(true)}
              >
                <Menu className="h-5 w-5" />
              </Button>
              <div>
                <h2 className="text-lg font-semibold text-foreground">
                  {t(
                    navItems.find((item) => item.path === location.pathname)?.key ??
                      "dashboard",
                  )}
                </h2>
                <p className="text-xs text-muted-foreground">
                  {session?.username || `#${session?.user_id ?? ""}`}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => void setLanguage(nextLanguage)}
              >
                <Languages className="h-4 w-4" />
                {nextLanguage.toUpperCase()}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => void logout()}
              >
                <LogOut className="h-4 w-4" />
                {t("logout")}
              </Button>
            </div>
          </div>
        </header>

        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
};

export default DashboardLayout;
