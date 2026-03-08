import { describe, expect, it } from "vitest";
import {
  buildEventSearchText,
  getEventIntent,
  getEventPrimarySource,
  humanizeEventAction,
} from "@/lib/event-log";
import type { EventEntry } from "@/lib/api";

const sampleEvent: EventEntry = {
  timestamp: "2026-03-08T12:00:00+00:00",
  action: "manual_schedule",
  origin: "batch",
  actor: "admin",
  items: [
    {
      path: "photos/post_1.jpg",
      name: "post_1.jpg",
      media_type: "photo",
      submitter: {
        is_admin: true,
        is_suggestion: false,
        source: "source_channel",
      },
    },
  ],
  extra: {
    scheduled_at: "2026-03-08 13:00",
    job_name: "cleanup",
  },
};

describe("event log helpers", () => {
  it("humanizes event action names", () => {
    expect(humanizeEventAction("manual_schedule")).toBe("Manual Schedule");
  });

  it("classifies destructive moderation actions correctly", () => {
    expect(getEventIntent("notok")).toBe("destructive");
    expect(getEventIntent("push")).toBe("success");
  });

  it("extracts the primary source from event items", () => {
    expect(getEventPrimarySource(sampleEvent)).toBe("source_channel");
  });

  it("indexes event metadata for filtering", () => {
    const searchText = buildEventSearchText(sampleEvent);
    expect(searchText).toContain("manual_schedule");
    expect(searchText).toContain("source_channel");
    expect(searchText).toContain("cleanup");
  });
});
