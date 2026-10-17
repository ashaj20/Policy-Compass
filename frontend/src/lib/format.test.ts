import { describe, expect, it } from "vitest";
import { formatFileSize, formatLongDate, formatRelativeDay } from "./format";

describe("format", () => {
  it("formats effective dates like the design: 01 September 2026", () => {
    expect(formatLongDate("2026-09-01")).toBe("01 September 2026");
    expect(formatLongDate("2026-12-31")).toBe("31 December 2026");
  });

  it("describes last-updated days relative to now", () => {
    const now = new Date(2026, 9, 17, 15, 0);
    expect(formatRelativeDay(new Date(2026, 9, 17, 9, 0).toISOString(), now)).toBe("today");
    expect(formatRelativeDay(new Date(2026, 9, 16, 23, 0).toISOString(), now)).toBe("yesterday");
    expect(formatRelativeDay(new Date(2026, 9, 3, 12, 0).toISOString(), now)).toBe("3 Oct 2026");
  });

  it("formats file sizes", () => {
    expect(formatFileSize(500)).toBe("500 bytes");
    expect(formatFileSize(2048)).toBe("2 KB");
    expect(formatFileSize(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});