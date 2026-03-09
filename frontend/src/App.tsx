import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { LoginGuard, ProtectedLayout } from "@/components/RouteGuards";
import { SessionProvider } from "@/components/SessionProvider";

const LoginPage = lazy(() => import("@/pages/LoginPage"));
const DashboardPage = lazy(() => import("@/pages/Index"));
const QueuePage = lazy(() => import("@/pages/QueuePage"));
const BatchPage = lazy(() => import("@/pages/BatchPage"));
const SuggestionsPage = lazy(() => import("@/pages/SuggestionsPage"));
const PostsPage = lazy(() => import("@/pages/PostsPage"));
const SwipeReviewPage = lazy(() => import("@/pages/SwipeReviewPage"));
const StatsPage = lazy(() => import("@/pages/StatsPage"));
const JobsPage = lazy(() => import("@/pages/JobsPage"));
const LeaderboardPage = lazy(() => import("@/pages/LeaderboardPage"));
const EventsPage = lazy(() => import("@/pages/EventsPage"));
const TrashPage = lazy(() => import("@/pages/TrashPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const NotFound = lazy(() => import("@/pages/NotFound"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

function RouteFallback() {
  return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <SessionProvider>
        <Toaster />
        <Sonner />
        <Suspense fallback={<RouteFallback />}>
          <BrowserRouter>
            <Routes>
              <Route
                path="/login"
                element={
                  <LoginGuard>
                    <LoginPage />
                  </LoginGuard>
                }
              />
              <Route element={<ProtectedLayout />}>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/queue" element={<QueuePage />} />
                <Route path="/batch" element={<BatchPage />} />
                <Route path="/suggestions" element={<SuggestionsPage />} />
                <Route path="/posts" element={<PostsPage />} />
                <Route path="/swipe-review" element={<SwipeReviewPage />} />
                <Route path="/stats" element={<StatsPage />} />
                <Route path="/jobs" element={<JobsPage />} />
                <Route path="/leaderboard" element={<LeaderboardPage />} />
                <Route path="/events" element={<EventsPage />} />
                <Route path="/trash" element={<TrashPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </Suspense>
      </SessionProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
