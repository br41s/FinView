"use client";

import { useEffect, useMemo, useRef } from "react";
import { useTheme } from "next-themes";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  ColorType,
  LineStyle,
  type IChartApi,
  type CandlestickData,
  type LineData,
  type Time,
} from "lightweight-charts";

import type { ZcPricePoint, ZcZone } from "@/lib/api";

// Canvas-rendered, so colors must be concrete (CSS vars can't be resolved on canvas).
// Two palettes keyed on the resolved next-themes value.
function palette(dark: boolean) {
  return {
    text: dark ? "#94a3b8" : "#475569",
    grid: dark ? "rgba(148,163,184,0.10)" : "rgba(71,85,105,0.10)",
    line: dark ? "#60a5fa" : "#2563eb",
    up: "#22c55e",
    down: "#ef4444",
    support: "#22c55e",
    resistance: "#ef4444",
  };
}

function hasOHLC(p: ZcPricePoint): p is Required<ZcPricePoint> {
  return p.open != null && p.high != null && p.low != null;
}

export function ZonasClaveChart({
  data,
  zones,
}: Readonly<{ data: ZcPricePoint[]; zones: ZcZone[] }>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();

  // Rebuild only when something visible actually changes — not on every parent
  // render (data is re-sliced into a fresh array each render by filterByScope).
  const rebuildKey = useMemo(
    () =>
      [
        resolvedTheme,
        data.length,
        data[0]?.date,
        data[data.length - 1]?.date,
        zones.map((z) => `${z.zone_type}:${z.level}:${z.strength}`).join("|"),
      ].join("~"),
    [resolvedTheme, data, zones],
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el || data.length === 0) return;

    const dark = resolvedTheme !== "light";
    const c = palette(dark);

    const chart: IChartApi = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: c.text,
        attributionLogo: true, // Apache-2.0 attribution requirement — do not remove
        fontSize: 11,
      },
      grid: {
        vertLines: { color: c.grid },
        horzLines: { color: c.grid },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: { horzLine: { labelVisible: true }, vertLine: { labelVisible: true } },
    });

    const useCandles = data.every(hasOHLC);
    if (useCandles) {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: c.up,
        downColor: c.down,
        borderUpColor: c.up,
        borderDownColor: c.down,
        wickUpColor: c.up,
        wickDownColor: c.down,
      });
      series.setData(
        data.map(
          (p): CandlestickData => ({
            time: p.date as Time,
            open: p.open!,
            high: p.high!,
            low: p.low!,
            close: p.close,
          }),
        ),
      );
      drawZones(series);
    } else {
      const series = chart.addSeries(LineSeries, { color: c.line, lineWidth: 2 });
      series.setData(
        data.map((p): LineData => ({ time: p.date as Time, value: p.close })),
      );
      drawZones(series);
    }

    // Support/resistance as horizontal price lines on the price series. Width and
    // solid/dashed style encode zone strength (stronger = thicker + solid).
    function drawZones(series: ReturnType<IChartApi["addSeries"]>) {
      for (const z of zones) {
        series.createPriceLine({
          price: z.level,
          color: z.zone_type === "support" ? c.support : c.resistance,
          lineWidth: Math.min(4, Math.max(1, Math.round(z.strength * 3))) as 1 | 2 | 3 | 4,
          lineStyle: z.strength > 0.7 ? LineStyle.Solid : LineStyle.Dashed,
          axisLabelVisible: true,
          title: z.level.toFixed(2),
        });
      }
    }

    chart.timeScale().fitContent();

    return () => chart.remove();
    // rebuildKey captures every dependency that should trigger a rebuild.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rebuildKey]);

  return <div ref={containerRef} className="h-[360px] w-full" />;
}
