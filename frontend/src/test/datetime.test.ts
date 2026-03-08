import { describe, expect, it } from "vitest";
import {
  fromDateTimeLocalValue,
  toDateTimeLocalValue,
} from "@/lib/datetime";

describe("datetime helpers", () => {
  it("converts datetime-local values into API format", () => {
    expect(fromDateTimeLocalValue("2026-03-08T12:34")).toBe("2026-03-08 12:34");
  });

  it("converts ISO values into datetime-local values", () => {
    expect(toDateTimeLocalValue("2026-03-08T12:34:00+00:00")).toHaveLength(16);
  });
});
