import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SwipeReviewPage from "@/pages/SwipeReviewPage";

const apiMock = vi.hoisted(() => ({
  getSuggestions: vi.fn(),
  getPosts: vi.fn(),
  postAction: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
  },
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
}));

vi.mock("@/components/SessionProvider", () => ({
  useSession: () => ({
    t: (key: string, params?: Record<string, string | number>) => {
      if (params?.count !== undefined) {
        return `${key}:${params.count}`;
      }
      if (params?.source) {
        return `Source: ${params.source}`;
      }
      if (params?.id) {
        return `User #${params.id}`;
      }
      return key;
    },
  }),
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <SwipeReviewPage />
    </QueryClientProvider>,
  );
}

describe("SwipeReviewPage", () => {
  beforeEach(() => {
    apiMock.getSuggestions.mockReset();
    apiMock.getPosts.mockReset();
    apiMock.postAction.mockReset();
    apiMock.getSuggestions.mockResolvedValue({
      items: [
        {
          items: [
            {
              path: "photos/processed_suggestion.jpg",
              name: "processed_suggestion.jpg",
              url: "https://example.com/suggestion.jpg",
              kind: "image",
              caption: "Suggestion card",
            },
          ],
          count: 1,
          is_group: false,
          caption: "Suggestion card",
        },
      ],
      page: 1,
      per_page: 20,
      total_pages: 1,
      total_items: 1,
    });
    apiMock.getPosts.mockResolvedValue({
      items: [
        {
          items: [
            {
              path: "photos/processed_post.jpg",
              name: "processed_post.jpg",
              url: "https://example.com/post.jpg",
              kind: "image",
              caption: "Post card",
            },
          ],
          count: 1,
          is_group: false,
          caption: "Post card",
        },
      ],
      page: 1,
      per_page: 20,
      total_pages: 1,
      total_items: 1,
      filters: {
        q: "",
        kind: "all",
        layout: "all",
        source: "all",
        sources: [],
      },
    });
    apiMock.postAction.mockResolvedValue({ status: "ok" });
  });

  it("sends the reject action for suggestions", async () => {
    renderPage();

    expect(await screen.findByText("Suggestion card")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "reject" })[0]);

    await waitFor(() => {
      expect(apiMock.postAction).toHaveBeenCalledWith({
        action: "notok",
        origin: "suggestions",
        paths: ["photos/processed_suggestion.jpg"],
      });
    });
  });

  it("sends the schedule action for posts", async () => {
    renderPage();

    expect(await screen.findByText("Suggestion card")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "posts" }));
    expect(await screen.findByText("Post card")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "schedule" })[0]);

    await waitFor(() => {
      expect(apiMock.postAction).toHaveBeenCalledWith({
        action: "schedule",
        origin: "posts",
        paths: ["photos/processed_post.jpg"],
      });
    });
  });
});
