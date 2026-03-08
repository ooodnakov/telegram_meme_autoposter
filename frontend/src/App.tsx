import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { LoginGuard, ProtectedLayout } from "@/components/RouteGuards";
import { SessionProvider } from "@/components/SessionProvider";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/Index";
import QueuePage from "@/pages/QueuePage";
import BatchPage from "@/pages/BatchPage";
import SuggestionsPage from "@/pages/SuggestionsPage";
import PostsPage from "@/pages/PostsPage";
import StatsPage from "@/pages/StatsPage";
import JobsPage from "@/pages/JobsPage";
import LeaderboardPage from "@/pages/LeaderboardPage";
import EventsPage from "@/pages/EventsPage";
import TrashPage from "@/pages/TrashPage";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <SessionProvider>
        <Toaster />
        <Sonner />
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
              <Route path="/stats" element={<StatsPage />} />
              <Route path="/jobs" element={<JobsPage />} />
              <Route path="/leaderboard" element={<LeaderboardPage />} />
              <Route path="/events" element={<EventsPage />} />
              <Route path="/trash" element={<TrashPage />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </SessionProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
