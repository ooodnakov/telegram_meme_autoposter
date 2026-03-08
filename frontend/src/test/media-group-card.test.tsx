import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MediaGroupCard from "@/components/MediaGroupCard";

vi.mock("@/components/SessionProvider", () => ({
  useSession: () => ({
    t: (key: string, params?: Record<string, string | number>) => {
      if (key === "suggestedBy") {
        return "Suggested by";
      }
      if (key === "userId") {
        return `User #${params?.id}`;
      }
      if (key === "totalItems") {
        return `${params?.count} items`;
      }
      if (key === "submittedVia") {
        return `Source: ${params?.source}`;
      }
      if (key === "trashedAt") {
        return `Trashed at ${params?.time}`;
      }
      if (key === "expiresAt") {
        return `Expires at ${params?.time}`;
      }
      if (key === "unknown") {
        return "Unknown";
      }
      if (key === "admin") {
        return "Admin";
      }
      return key;
    },
  }),
}));

describe("MediaGroupCard", () => {
  it("renders grouped media details", () => {
    render(
      <MediaGroupCard
        group={{
          items: [
            {
              path: "photos/a.jpg",
              name: "a.jpg",
              url: "https://example.com/a.jpg",
              kind: "image",
              caption: "Caption A",
            },
            {
              path: "videos/b.mp4",
              name: "b.mp4",
              url: "https://example.com/b.mp4",
              kind: "video",
            },
          ],
          count: 2,
          is_group: true,
          caption: "Album caption",
          source: "@source",
          submitter: {
            is_admin: false,
            is_suggestion: true,
            user_id: 42,
          },
        }}
      />,
    );

    expect(screen.getByText("Album caption")).toBeInTheDocument();
    expect(screen.getByText("2 items")).toBeInTheDocument();
    expect(screen.getByText("Source: @source")).toBeInTheDocument();
    expect(screen.getByText(/User #42/)).toBeInTheDocument();
  });
});
