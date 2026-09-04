import { describe, expect, it } from "vitest";
import { formatAge, geoHealth, type GeoCycleRun } from "./geoHealth";

const NOW = new Date("2026-09-04T12:00:00Z").getTime();

function run(overrides: Partial<GeoCycleRun> = {}): GeoCycleRun {
  return {
    started_at: "2026-09-04T11:50:00Z",
    finished_at: "2026-09-04T11:51:00Z",
    ok: true,
    events: 34,
    new_signals: 2,
    notified: 0,
    checkpoints_evaluated: 5,
    persist_failures: 0,
    sources: { earthquakes: 9, events: 20, fires: 5 },
    error: null,
    ...overrides,
  };
}

describe("geoHealth", () => {
  it("says nothing before the status has loaded", () => {
    expect(geoHealth(null, NOW)).toBeNull();
  });

  it("reports a healthy recent cycle with what it ingested", () => {
    const health = geoHealth({ interval_minutes: 15, last_run: run() }, NOW);
    expect(health).toEqual({
      tone: "ok",
      message: "Última ejecución hace 10 min · 34 eventos · 2 señales nuevas",
    });
  });

  it("flags a pipeline that has never recorded a cycle", () => {
    const health = geoHealth({ interval_minutes: 15, last_run: null }, NOW);
    expect(health?.tone).toBe("warn");
    expect(health?.message).toContain("/api/geo/cron");
  });

  it("surfaces the error of a failed cycle", () => {
    const health = geoHealth(
      {
        interval_minutes: 15,
        last_run: run({ ok: false, error: "IntegrityError: UNIQUE constraint failed" }),
      },
      NOW,
    );
    expect(health?.tone).toBe("down");
    expect(health?.message).toContain("IntegrityError");
  });

  it("tolerates a couple of missed cycles before crying wolf", () => {
    // 15-minute interval, one hour of silence: the prod cron only runs every 30
    // minutes, so three raw intervals would be a false alarm.
    const health = geoHealth(
      { interval_minutes: 15, last_run: run({ started_at: "2026-09-04T11:00:00Z" }) },
      NOW,
    );
    expect(health?.tone).toBe("ok");
  });

  it("warns once the silence is longer than the schedule explains", () => {
    const health = geoHealth(
      { interval_minutes: 15, last_run: run({ started_at: "2026-09-04T09:00:00Z" }) },
      NOW,
    );
    expect(health?.tone).toBe("warn");
    expect(health?.message).toContain("hace 3 h");
  });

  it("calls a day of silence what it is, and names the job to check", () => {
    const health = geoHealth(
      { interval_minutes: 15, last_run: run({ started_at: "2026-07-23T11:01:00Z" }) },
      NOW,
    );
    expect(health?.tone).toBe("down");
    expect(health?.message).toContain("geo-intel-cycle");
  });

  it("treats every source at zero as an outage, not a quiet day", () => {
    const health = geoHealth(
      {
        interval_minutes: 15,
        last_run: run({ events: 0, new_signals: 0, sources: { earthquakes: 0, events: 0 } }),
      },
      NOW,
    );
    expect(health?.tone).toBe("warn");
    expect(health?.message).toContain("ninguna fuente");
  });

  it("does not read a genuinely quiet cycle as broken", () => {
    // Sources answered, nothing crossed a threshold. That is a real outcome.
    const health = geoHealth(
      {
        interval_minutes: 15,
        last_run: run({ events: 0, new_signals: 0, sources: { earthquakes: 12, events: 4 } }),
      },
      NOW,
    );
    expect(health?.tone).toBe("ok");
  });

  it("reports signals lost by the persist phase", () => {
    const health = geoHealth(
      { interval_minutes: 15, last_run: run({ persist_failures: 1 }) },
      NOW,
    );
    expect(health?.tone).toBe("warn");
    expect(health?.message).toContain("1 señal ");
  });

  it("handles a run recorded before source counts existed", () => {
    const health = geoHealth({ interval_minutes: 15, last_run: run({ sources: {} }) }, NOW);
    expect(health?.tone).toBe("ok");
  });
});

describe("formatAge", () => {
  it("rounds down to the unit that reads naturally", () => {
    expect(formatAge(30_000)).toBe("hace menos de un minuto");
    expect(formatAge(9 * 60_000)).toBe("hace 9 min");
    expect(formatAge(3 * 3_600_000)).toBe("hace 3 h");
    expect(formatAge(26 * 3_600_000)).toBe("hace 1 día");
    expect(formatAge(44 * 24 * 3_600_000)).toBe("hace 44 días");
  });
});
