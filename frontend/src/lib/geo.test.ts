import { describe, expect, it } from "vitest";
import {
  formatAccuracyLine,
  scopeLabel,
  thesisSegments,
  tradabilityHint,
  type GeoAccuracy,
  type GeoCheckpointHorizon,
  type GeoHorizonAccuracy,
  macroRegimeBadge,
} from "./geo";

const NOW = new Date("2026-09-20T12:00:00Z").getTime();

function bucket(over: Partial<GeoHorizonAccuracy> = {}): GeoHorizonAccuracy {
  return { correct: 0, incorrect: 0, neutral: 0, pending: 0, accuracy: null, ...over };
}

function data(
  horizons: Partial<Record<GeoCheckpointHorizon, GeoHorizonAccuracy>>,
  since = "2026-08-21T12:00:00Z",
): GeoAccuracy {
  return { since, horizons, rules: [] };
}

describe("formatAccuracyLine", () => {
  it("says nothing before the first fetch lands", () => {
    expect(formatAccuracyLine(null, NOW)).toBeNull();
  });

  it("renders every horizon, the window and the sample size", () => {
    const line = formatAccuracyLine(
      data({
        "1h": bucket({ correct: 12, incorrect: 88, accuracy: 0.12 }),
        "6h": bucket({ correct: 18, incorrect: 82, accuracy: 0.18 }),
        "1d": bucket({ correct: 30, incorrect: 70, accuracy: 0.3 }),
        "3d": bucket({ correct: 41, incorrect: 59, accuracy: 0.41 }),
        "7d": bucket({ correct: 45, incorrect: 55, accuracy: 0.45 }),
      }),
      NOW,
    );
    expect(line).toBe(
      "Aciertos (30 d): 1h 12 % · 6h 18 % · 1d 30 % · 3d 41 % · 7d 45 % · n=500",
    );
  });

  it("shows a dash, never 0 %, for a horizon with nothing measurable", () => {
    // The distinction the dots lost: unmeasured is not a zero hit rate.
    const line = formatAccuracyLine(
      data({ "1h": bucket({ neutral: 9, pending: 3 }) }),
      NOW,
    );
    expect(line).toContain("1h —");
    expect(line).not.toContain("0 %");
  });

  it("keeps a real 0 % distinct from no measurement", () => {
    const line = formatAccuracyLine(
      data({ "1h": bucket({ correct: 0, incorrect: 7, accuracy: 0 }) }),
      NOW,
    );
    expect(line).toContain("1h 0 %");
    expect(line).toContain("6h —");
  });

  it("leaves NEUTRAL and PENDING out of the sample size", () => {
    const line = formatAccuracyLine(
      data({
        "1d": bucket({ correct: 2, incorrect: 3, neutral: 40, pending: 20, accuracy: 0.4 }),
      }),
      NOW,
    );
    expect(line).toContain("n=5");
  });

  it("dashes every horizon when the backend returns an empty matrix", () => {
    expect(formatAccuracyLine(data({}), NOW)).toBe(
      "Aciertos (30 d): 1h — · 6h — · 1d — · 3d — · 7d — · n=0",
    );
  });

  it("derives the window from `since` rather than assuming 30 days", () => {
    const line = formatAccuracyLine(data({}, "2026-09-13T12:00:00Z"), NOW);
    expect(line).toContain("Aciertos (7 d)");
  });

  it("never reports a zero-day window", () => {
    const line = formatAccuracyLine(data({}, "2026-09-20T11:00:00Z"), NOW);
    expect(line).toContain("Aciertos (1 d)");
  });

  it("rounds the percentage to whole points", () => {
    const line = formatAccuracyLine(
      data({ "1h": bucket({ correct: 1, incorrect: 2, accuracy: 1 / 3 }) }),
      NOW,
    );
    expect(line).toContain("1h 33 %");
  });
});

describe("tradabilityHint", () => {
  it("says nothing about an instrument buyable as cash", () => {
    expect(tradabilityHint({ tradability: "cash_eu", alternate: null })).toEqual({
      badge: null,
      tooltip: null,
      muted: false,
    });
  });

  it("treats an older row with no tradability as cash, not as dead", () => {
    // Signals persisted before the scoping work carry no field; greying them
    // out would paint most of the feed as unreachable.
    expect(tradabilityHint({}).muted).toBe(false);
    expect(tradabilityHint({}).badge).toBeNull();
  });

  it("marks a US ETF as options-only without dimming it — it is still a route", () => {
    const hint = tradabilityHint({
      tradability: "options_only",
      alternate: "SGLN / 4GLD (physical gold ETC)",
    });
    expect(hint.badge).toBe("opc.");
    expect(hint.muted).toBe(false);
    expect(hint.tooltip).toBe(
      "ETF USA sin KID: solo opciones en IBKR — alternativa: SGLN / 4GLD (physical gold ETC)",
    );
  });

  it("dims an instrument with no retail route and names the alternative", () => {
    const hint = tradabilityHint({
      tradability: "not_tradable",
      alternate: "WisdomTree Cocoa ETC",
    });
    expect(hint.muted).toBe(true);
    expect(hint.badge).toBe("s/ruta");
    expect(hint.tooltip).toBe("Sin ruta minorista en la UE — alternativa: WisdomTree Cocoa ETC");
  });

  it("says 'sin alternativa' rather than trailing an empty one", () => {
    // The backend sends "" → null for LBR=F; a blank tail would read as a bug.
    expect(tradabilityHint({ tradability: "not_tradable", alternate: null }).tooltip).toBe(
      "Sin ruta minorista en la UE — sin alternativa",
    );
    expect(tradabilityHint({ tradability: "options_only", alternate: "  " }).tooltip).toBe(
      "ETF USA sin KID: solo opciones en IBKR — sin alternativa",
    );
  });
});

describe("scopeLabel", () => {
  it("translates every scope the backend can send", () => {
    expect(scopeLabel("site")).toBe("sitio");
    expect(scopeLabel("local")).toBe("local");
    expect(scopeLabel("regional")).toBe("regional");
    expect(scopeLabel("global")).toBe("global");
  });

  it("returns null for a row written before scoping, so no tag is drawn", () => {
    expect(scopeLabel(undefined)).toBeNull();
    expect(scopeLabel("")).toBeNull();
    expect(scopeLabel("planetary")).toBeNull();
  });
});

describe("thesisSegments", () => {
  it("splits a written chain into its three links", () => {
    expect(
      thesisSegments("Corta el suministro de cobre → sube el precio spot → mineras arriba"),
    ).toEqual([
      "Corta el suministro de cobre",
      "sube el precio spot",
      "mineras arriba",
    ]);
  });

  it("leaves an unchained thesis as one segment", () => {
    expect(thesisSegments("Riesgo de oferta en el Golfo")).toEqual([
      "Riesgo de oferta en el Golfo",
    ]);
  });

  it("drops empty links instead of rendering a dangling arrow", () => {
    expect(thesisSegments("A →  → B")).toEqual(["A", "B"]);
    expect(thesisSegments("   ")).toEqual([]);
  });
});


describe("macroRegimeBadge", () => {
  it("is silent without a snapshot", () => {
    expect(macroRegimeBadge(null)).toBeNull();
    expect(macroRegimeBadge(undefined)).toBeNull();
  });

  it("warns on risk-off and says what it does to the score", () => {
    const badge = macroRegimeBadge({ regime: "risk_off", vix: 31.24, as_of: "2026-09-17" });
    expect(badge?.tone).toBe("warn");
    expect(badge?.label).toBe("Régimen: risk-off");
    expect(badge?.title).toContain("VIX 31.2");
    expect(badge?.title).toContain("+1 de riesgo");
  });

  it("is muted on neutral and tolerates a missing VIX", () => {
    const badge = macroRegimeBadge({ regime: "neutral", vix: null, as_of: null });
    expect(badge).toEqual({ label: "Régimen: neutral", tone: "muted", title: "VIX n/d." });
  });
});
