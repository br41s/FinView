import { describe, expect, it } from "vitest";
import { activeAllDay, activeKey, dayMoods, EVENT_TIMING, isAllDay, localDay, whenLabel } from "./eventTiming";
import type { EventType, WorldEvent } from "./types";

const ev = (id: string, eventType: EventType, occurredAt: string, assetId: string | null = "A"): WorldEvent =>
  ({ id, eventType, occurredAt, assetId }) as WorldEvent;

// 12 Nov 2026, 15:00 in the viewer's own time zone.
const NOW = new Date(2026, 10, 12, 15, 0).getTime();

describe("event timing", () => {
  it("price moves and signals are instants; dividends, results and trades fill a day", () => {
    expect(EVENT_TIMING.price_move_up).toBe("instant");
    expect(EVENT_TIMING.options_alert).toBe("instant");
    expect(isAllDay(ev("d", "dividend_paid", "2026-11-12T00:00:00.000Z"))).toBe(true);
    expect(isAllDay(ev("t", "position_added", "2026-11-12T00:00:00.000Z"))).toBe(true);
  });

  it("knows today in the viewer's calendar", () => {
    expect(localDay(NOW)).toBe("2026-11-12");
  });

  it("keeps performing only today's all-day events that have a building", () => {
    const events = [
      ev("today", "dividend_paid", "2026-11-12T00:00:00.000Z"),
      ev("yesterday", "dividend_paid", "2026-11-11T00:00:00.000Z"),
      ev("instant", "price_move_up", "2026-11-12T00:00:00.000Z"),
      ev("no-building", "position_closed", "2026-11-12T00:00:00.000Z", null),
    ];
    expect(activeAllDay(events, NOW).map((e) => e.id)).toEqual(["today"]);
  });

  it("has a key that ignores order", () => {
    const a = ev("a", "dividend_paid", "2026-11-12T00:00:00.000Z");
    const b = ev("b", "earnings_beat", "2026-11-12T00:00:00.000Z");
    expect(activeKey([a, b])).toBe(activeKey([b, a]));
  });
});

describe("whenLabel", () => {
  it("never gives an all-day event a time of day", () => {
    expect(whenLabel(ev("a", "dividend_paid", "2026-11-12T00:00:00.000Z"), NOW)).toBe("Todo el día · hoy");
    expect(whenLabel(ev("b", "position_added", "2026-11-11T00:00:00.000Z"), NOW)).toBe("Todo el día · ayer");
    expect(whenLabel(ev("c", "dividend_paid", "2026-11-09T00:00:00.000Z"), NOW)).toBe("Todo el día · 9 nov");
    expect(whenLabel(ev("d", "dividend_paid", "2025-12-30T00:00:00.000Z"), NOW)).toBe("Todo el día · 30 dic 2025");
  });

  it("dates an instant by how long ago it happened", () => {
    expect(whenLabel(ev("p", "price_move_up", new Date(NOW - 5 * 60000).toISOString()), NOW)).toBe("hace 5 min");
    expect(whenLabel(ev("q", "price_move_up", new Date(NOW - 3 * 3600000).toISOString()), NOW)).toBe("hace 3 h");
  });
});

describe("dayMoods", () => {
  it("gives each building the strongest mood of the day", () => {
    const moods = dayMoods([
      ev("1", "position_added", "2026-11-12T00:00:00.000Z", "A"),
      ev("2", "dividend_paid", "2026-11-12T00:00:00.000Z", "A"),
      ev("3", "position_reduced", "2026-11-12T00:00:00.000Z", "B"),
      ev("4", "earnings_miss", "2026-11-12T00:00:00.000Z", "B"),
      ev("5", "position_closed", "2026-11-12T00:00:00.000Z", "C"),
    ]);
    expect([...moods.entries()].sort()).toEqual([["A", "party"], ["B", "concerned"]]);
  });
});
