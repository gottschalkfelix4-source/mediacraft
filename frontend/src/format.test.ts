import { describe, expect, it } from "vitest";
import { epCode, fmtAge, fmtDuration, fmtSize, parseDate, reasonKey, relTime } from "./format";

describe("parseDate", () => {
  it("treats timestamps without zone as UTC and trims microseconds", () => {
    expect(parseDate("2026-01-02T03:04:05.123456")?.toISOString()).toBe("2026-01-02T03:04:05.123Z");
    expect(parseDate("2026-01-02T03:04:05Z")?.toISOString()).toBe("2026-01-02T03:04:05.000Z");
  });
  it("reads plain dates as local calendar days", () => {
    const d = parseDate("2026-05-17")!;
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 4, 17]);
  });
  it("returns null for empty or broken input", () => {
    expect(parseDate("")).toBeNull();
    expect(parseDate("kein datum")).toBeNull();
  });
});

describe("durations and sizes", () => {
  it("formats durations compactly", () => {
    expect(fmtDuration(12)).toBe("12 s");
    expect(fmtDuration(3 * 3600 + 12 * 60)).toBe("3 h 12 min");
    expect(fmtDuration(2 * 86400)).toBe("2 d");
    expect(fmtDuration(null)).toBe("–");
  });
  it("formats sizes with German separators", () => {
    expect(fmtSize(0)).toBe("0 B");
    expect(fmtSize(1536)).toBe("2 KB");
    expect(fmtSize(1.5 * 1024 ** 3)).toBe("1,5 GB");
  });
  it("formats release age", () => {
    expect(fmtAge(0.2)).toBe("12 min");
    expect(fmtAge(30)).toBe("30 h");
    expect(fmtAge(72)).toBe("3 d");
  });
  it("relTime says past/future", () => {
    const now = new Date("2026-01-01T12:00:00Z");
    expect(relTime(new Date("2026-01-01T13:00:00Z"), now)).toBe("in 1 h");
    expect(relTime(new Date("2026-01-01T11:55:00Z"), now)).toBe("vor 5 min");
  });
  it("builds episode codes", () => {
    expect(epCode(1, 5)).toBe("S01E05");
  });
});

describe("reasonKey groups rejection reasons", () => {
  it("drops release specific details", () => {
    expect(reasonKey("Zu klein: 1.2 MB/min < 4 MB/min")).toBe("Zu klein");
    expect(reasonKey("Qualität HDTV-720p ist im Profil 'HD-1080p' nicht erlaubt")).toBe("Qualität … ist im Profil … nicht erlaubt");
    expect(reasonKey("S01E02: Vorhandene Datei (WEBDL-1080p, Score 100) ist gleichwertig oder besser")).toBe(
      "Vorhandene Datei … ist gleichwertig oder besser",
    );
    expect(reasonKey("Custom-Format-Score -10000 < Minimum -1000")).toBe(reasonKey("Custom-Format-Score 5 < Minimum 10"));
  });
});
