import { describe, expect, it } from "vitest";
import { gapLines, nextStepDelayMs, progressLabel, type SyncProgress } from "./brokerSync";

function progress(overrides: Partial<SyncProgress> = {}): SyncProgress {
  return {
    state: "running",
    done: 2,
    total: 8,
    year: 2021,
    message: null,
    gaps: {},
    retry_after: 5,
    ...overrides,
  };
}

describe("nextStepDelayMs", () => {
  it("continues at once after a step that imported a year", () => {
    expect(nextStepDelayMs(progress())).toBe(500);
  });

  it("waits IBKR's retry time while a statement is generating", () => {
    expect(nextStepDelayMs(progress({ message: "IBKR está generando el informe de 2021." }))).toBe(
      5000,
    );
  });
});

describe("progressLabel", () => {
  it("counts the year being imported, not the ones already done", () => {
    expect(progressLabel(progress())).toBe("Importando 3 de 8 (2021)");
  });

  it("never counts past the total", () => {
    expect(progressLabel(progress({ done: 8, year: null }))).toBe("Importando 8 de 8");
  });

  it("reports a finished run", () => {
    expect(progressLabel(progress({ state: "done", done: 8 }))).toBe(
      "Sincronización completa: 8 años",
    );
    expect(progressLabel(progress({ state: "done", done: 1, total: 1 }))).toBe(
      "Sincronización completa",
    );
  });

  it("shows the backend's reason when the run stops", () => {
    expect(progressLabel(progress({ state: "error", message: "El token ha caducado." }))).toBe(
      "El token ha caducado.",
    );
  });
});

describe("gapLines", () => {
  it("lists missing years oldest first and the history note last", () => {
    expect(
      gapLines({ historial: "Añade Date Opened.", "2022": "código 1003", "2019": "código 1003" }),
    ).toEqual(["2019: código 1003", "2022: código 1003", "Añade Date Opened."]);
  });

  it("is empty when nothing is missing", () => {
    expect(gapLines(undefined)).toEqual([]);
  });
});
