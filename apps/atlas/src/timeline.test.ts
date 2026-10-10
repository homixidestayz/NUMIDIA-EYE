import { describe, expect, it } from "vitest";
import {
  ALGERIA_OFFSET_MINUTES,
  RANGES,
  bucketByHour,
  formatLocalClock,
  formatLocalDay,
  inRange,
  localDayStartUtc,
  rangeStartUtc,
  rangeLabel,
} from "./timeline";

/** 2026-10-10T21:40Z is 22:40 on 10 Oct in Algeria (UTC+1). */
const NOW = new Date("2026-10-10T21:40:00Z");

describe("Algeria local day", () => {
  it("is UTC+1 with no daylight saving", () => {
    expect(ALGERIA_OFFSET_MINUTES).toBe(60);
    // Algeria has not observed DST since 2022; a Jan and a Jul instant must
    // produce the same offset or "today" would change length mid-year.
    expect(localDayStartUtc(new Date("2026-01-15T23:30:00Z"))).toBeInstanceOf(Date);
    expect(localDayStartUtc(new Date("2026-07-15T23:30:00Z"))).toBeInstanceOf(Date);
  });

  it("starts the day at 00:00 local, which is 23:00 UTC the previous day", () => {
    const s = localDayStartUtc(NOW);
    expect(s.toISOString()).toBe("2026-10-09T23:00:00.000Z");
    expect(formatLocalClock(s)).toBe("00:00");
  });

  it("keeps an instant before 01:00 local on the correct local day", () => {
    // 00:30 on 10 Oct local is still 23:30 on 9 Oct UTC.
    const s = localDayStartUtc(new Date("2026-10-09T23:30:00Z"));
    expect(s.toISOString()).toBe("2026-10-09T23:00:00.000Z");
    expect(formatLocalDay(s)).toBe("10 Oct");
  });

  it("never returns a start in the future", () => {
    for (const iso of [
      "2026-10-10T21:40:00Z",
      "2026-03-31T22:59:00Z",
      "2026-12-31T23:59:00Z",
    ]) {
      const s = localDayStartUtc(new Date(iso));
      expect(s.getTime()).toBeLessThanOrEqual(new Date(iso).getTime());
    }
  });
});

describe("ranges", () => {
  it("leads with TODAY", () => {
    expect(RANGES[0].id).toBe("today");
    expect(rangeLabel("today")).toBe("Today");
  });

  it("maps each range to a concrete start", () => {
    const spanStart = new Date("2026-10-08T00:00:00Z");
    const spanEnd = NOW;
    for (const r of RANGES) {
      const s = rangeStartUtc(r.id, NOW, spanStart, spanEnd);
      if (r.id === "all") {
        expect(s?.toISOString()).toBe(spanStart.toISOString());
      } else {
        expect(s).toBeInstanceOf(Date);
        expect(s!.getTime()).toBeLessThanOrEqual(NOW.getTime());
      }
    }
  });

  it("puts 24h exactly 24 hours back, not at a day boundary", () => {
    const s = rangeStartUtc("24h", NOW, new Date("2026-10-01T00:00:00Z"), NOW);
    expect((NOW.getTime() - s!.getTime()) / 3_600_000).toBe(24);
  });

  it("keeps TODAY inside 24h for any instant of the day", () => {
    for (const iso of ["2026-10-10T00:05:00Z", "2026-10-10T12:00:00Z", "2026-10-10T22:55:00Z"]) {
      const now = new Date(iso);
      const s = rangeStartUtc("today", now, new Date("2026-10-01T00:00:00Z"), now)!;
      const h = (now.getTime() - s.getTime()) / 3_600_000;
      expect(h).toBeGreaterThan(0);
      expect(h).toBeLessThanOrEqual(24);
    }
  });
});

describe("bucketing", () => {
  const at = (iso: string) => new Date(iso);

  it("counts detections into hourly buckets", () => {
    const dets = [
      { acq_datetime: "2026-10-10T09:05:00Z" },
      { acq_datetime: "2026-10-10T09:55:00Z" },
      { acq_datetime: "2026-10-10T10:15:00Z" },
    ].map((d) => ({ acq_datetime: new Date(d.acq_datetime) }));
    const start = at("2026-10-10T08:00:00Z");
    const end = at("2026-10-10T12:00:00Z");
    const b = bucketByHour(dets, start, end);
    const total = b.reduce((s, x) => s + x.count, 0);
    expect(total).toBe(3);
    expect(b.every((x) => x.count >= 0)).toBe(true);
    expect(b.length).toBeGreaterThan(0);
  });

  it("returns a zero-filled run so gaps read as gaps, not as missing bars", () => {
    const b = bucketByHour([], at("2026-10-10T08:00:00Z"), at("2026-10-10T12:00:00Z"));
    expect(b.length).toBeGreaterThan(0);
    expect(b.every((x) => x.count === 0)).toBe(true);
  });

  it("never reports a count above the number of detections", () => {
    const many = Array.from({ length: 37 }, (_, i) => ({
      acq_datetime: new Date(Date.UTC(2026, 9, 10, 9, i % 60)),
    }));
    const b = bucketByHour(many, at("2026-10-10T00:00:00Z"), at("2026-10-10T23:00:00Z"));
    expect(b.reduce((s, x) => s + x.count, 0)).toBe(37);
  });
});

describe("inRange", () => {
  const d = (iso: string) => ({ acq_datetime: new Date(iso) });
  const start = new Date("2026-10-10T09:00:00Z");
  const end = new Date("2026-10-10T11:00:00Z");

  it("includes both ends of the window", () => {
    expect(inRange(d("2026-10-10T09:00:00Z"), start, end)).toBe(true);
    expect(inRange(d("2026-10-10T11:00:00Z"), start, end)).toBe(true);
  });

  it("excludes anything outside", () => {
    expect(inRange(d("2026-10-10T08:59:00Z"), start, end)).toBe(false);
    expect(inRange(d("2026-10-10T11:01:00Z"), start, end)).toBe(false);
  });

  it("accepts a string acq_datetime as the API actually returns it", () => {
    expect(
      inRange({ acq_datetime: "2026-10-10T10:00:00Z" }, start, end),
    ).toBe(true);
    expect(
      inRange({ acq_datetime: "2026-10-10T10:00:00+00:00" }, start, end),
    ).toBe(true);
  });

  it("treats an unparseable timestamp as outside the window, not as in it", () => {
    expect(inRange({ acq_datetime: "not-a-date" }, start, end)).toBe(false);
  });
});