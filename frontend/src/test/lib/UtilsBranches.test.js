import { describe, it, expect } from "vitest";

describe("lib/utils edge branches", () => {
  it("returns start-only format when range end is invalid", async () => {
    const { formatUKDateTime } = await import("../../lib/utils");
    const result = formatUKDateTime("2026-03-05 09:00:00 - not-a-date");
    expect(result).toContain("05/03/2026");
    expect(result).not.toContain(" - ");
  });

  it("returns original string when range start is invalid", async () => {
    const { formatUKDateTime } = await import("../../lib/utils");
    expect(formatUKDateTime("junk - 2026-03-05 10:00:00")).toBe("junk - 2026-03-05 10:00:00");
  });

  it("hits catch branches via throwing input", async () => {
    const { formatUKDateTime, formatUKDate, formatUKTime } = await import("../../lib/utils");
    const bad = { valueOf() { throw new Error("bad"); } };
    expect(formatUKDateTime(bad)).toBe(bad);
    expect(formatUKDate(bad)).toBe("N/A");
    expect(formatUKTime(bad)).toBe("N/A");
  });

  it("formats truthy non-string input with includes support", async () => {
    const { formatUKDateTime } = await import("../../lib/utils");
    expect(formatUKDateTime(["2026-03-05 09:15:00"])).toContain("2026");
  });
  it("cn handles objects, arrays and conflicting tailwind classes", async () => {
    const { cn } = await import("../../lib/utils");
    expect(cn({ active: true, hidden: false })).toBe("active");
    expect(cn(["a", "b"])).toBe("a b");
    expect(cn("px-2 px-4")).toBe("px-4");
  });
});
