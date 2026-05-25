import { describe, it, expect } from "vitest";

describe("Utility functions", () => {
  describe("formatUKDateTime", () => {
    it("returns N/A for null input", async () => {
      const { formatUKDateTime } = await import("../lib/utils");
      expect(formatUKDateTime(null)).toBe("N/A");
      expect(formatUKDateTime(undefined)).toBe("N/A");
    });

    it("formats a valid date string", async () => {
      const { formatUKDateTime } = await import("../lib/utils");
      const result = formatUKDateTime("2026-03-05 09:15:00");
      expect(result).not.toBe("N/A");
      expect(result).toContain("2026");
      expect(result).toContain("05/03");
    });

    it("handles range strings with - separator", async () => {
      const { formatUKDateTime } = await import("../lib/utils");
      const result = formatUKDateTime("2026-03-05 09:00:00 - 2026-03-05 10:00:00");
      expect(result).toContain("-");
      expect(result).toContain("05/03");
    });

    it("returns original string for invalid date", async () => {
      const { formatUKDateTime } = await import("../lib/utils");
      expect(formatUKDateTime("not-a-date")).toBe("not-a-date");
    });
  });

  describe("formatUKDate", () => {
    it("returns N/A for null input", async () => {
      const { formatUKDate } = await import("../lib/utils");
      expect(formatUKDate(null)).toBe("N/A");
      expect(formatUKDate(undefined)).toBe("N/A");
    });

    it("formats a valid date", async () => {
      const { formatUKDate } = await import("../lib/utils");
      const result = formatUKDate("2026-03-05");
      expect(result).toContain("05/03/2026");
    });

    it("returns N/A for invalid date", async () => {
      const { formatUKDate } = await import("../lib/utils");
      expect(formatUKDate("invalid")).toBe("N/A");
    });
  });

  describe("formatUKTime", () => {
    it("returns N/A for null input", async () => {
      const { formatUKTime } = await import("../lib/utils");
      expect(formatUKTime(null)).toBe("N/A");
      expect(formatUKTime(undefined)).toBe("N/A");
    });

    it("formats a valid time", async () => {
      const { formatUKTime } = await import("../lib/utils");
      const result = formatUKTime("2026-03-05 09:15:00");
      expect(result).not.toBe("N/A");
      expect(result).toContain("09");
    });

    it("returns N/A for invalid time", async () => {
      const { formatUKTime } = await import("../lib/utils");
      expect(formatUKTime("invalid")).toBe("N/A");
    });
  });

  describe("cn", () => {
    it("merges class names", async () => {
      const { cn } = await import("../lib/utils");
      const result = cn("foo", "bar");
      expect(result).toBe("foo bar");
    });

    it("handles conditional classes", async () => {
      const { cn } = await import("../lib/utils");
      const result = cn("base", false && "hidden", "visible");
      expect(result).toBe("base visible");
    });
  });
});
