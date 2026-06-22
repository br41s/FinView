"use client";

import { useEffect, useMemo, useRef } from "react";
import { useTheme } from "next-themes";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  LineSeries,
  ColorType,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
  type CandlestickData,
  type LineData,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";

// Minimal OHLC point. open/high/low optional → falls back to a line series.
export interface PricePoint {
  date: string;
  close: number;
  open?: number;
  high?: number;
  low?: number;
}

export interface PriceLine {
  price: number;
  color: string;
  /** 0..1 — drives line width and solid/dashed style. */
  strength?: number;
  title?: string;
}

export interface PriceMarker {
  date: string;
  position: "aboveBar" | "belowBar";
  color: string;
  shape: "arrowUp" | "arrowDown" | "circle";
  text?: string;
}

// Canvas-rendered, so colors must be concrete (CSS vars can't resolve on canvas).
function palette(dark: boolean) {
  return {
    text: dark ? "#94a3b8" : "#475569",
    grid: dark ? "rgba(148,163,184,0.10)" : "rgba(71,85,105,0.10)",
    line: dark ? "#60a5fa" : "#2563eb",
    up: "#22c55e",
    down: "#ef4444",
  };
}

function hasOHLC(p: PricePoint): p is Required<PricePoint> {
  return p.open != null && p.high != null && p.low != null;
}

export function PriceChart({
  data,
  priceLines = [],
  markers = [],
  height = 360,
}: Readonly<{
  data: PricePoint[];
  priceLines?: PriceLine[];
  markers?: PriceMarker[];
  height?: number;
}>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);
  const { resolvedTheme } = useTheme();

  // Manual candle-width control (on top of the auto-fit done on each rebuild).
  function adjustZoom(factor: number) {
    const chart = chartApiRef.current;
    if (!chart) return;
    const ts = chart.timeScale();
    const current = ts.options().barSpacing ?? 6;
    ts.applyOptions({ barSpacing: Math.max(1, current * factor) });
  }

  // Rebuild only when something visible actually changes — not on every parent
  // render (callers often re-slice data into a fresh array each render).
  const rebuildKey = useMemo(
    () =>
      [
        resolvedTheme,
        height,
        data.length,
        data[0]?.date,
        data[data.length - 1]?.date,
        priceLines.map((l) => `${l.price}:${l.strength ?? ""}:${l.color}`).join("|"),
        markers.map((m) => `${m.date}:${m.shape}`).join("|"),
      ].join("~"),
    [resolvedTheme, height, data, priceLines, markers],
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
      // maxBarSpacing caps candle width so short ranges (few bars) don't stretch
      // across the whole pane. Edges left unpinned so the cap can take effect.
      timeScale: { borderVisible: false, maxBarSpacing: 24 },
      crosshair: { horzLine: { labelVisible: true }, vertLine: { labelVisible: true } },
    });
    chartApiRef.current = chart;

    const useCandles = data.every(hasOHLC);
    let series: ISeriesApi<SeriesType>;
    if (useCandles) {
      series = chart.addSeries(CandlestickSeries, {
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
    } else {
      series = chart.addSeries(LineSeries, { color: c.line, lineWidth: 2 });
      series.setData(
        data.map((p): LineData => ({ time: p.date as Time, value: p.close })),
      );
    }

    // Horizontal price lines (e.g. support/resistance, option strikes). Width and
    // solid/dashed style encode optional strength (stronger = thicker + solid).
    for (const l of priceLines) {
      const s = l.strength ?? 1;
      series.createPriceLine({
        price: l.price,
        color: l.color,
        lineWidth: Math.min(4, Math.max(1, Math.round(s * 3))) as 1 | 2 | 3 | 4,
        lineStyle: s > 0.7 ? LineStyle.Solid : LineStyle.Dashed,
        axisLabelVisible: true,
        title: l.title ?? "",
      });
    }

    // Markers (e.g. buy/sell executions). createSeriesMarkers sorts internally,
    // but markers must reference a time within the data range to be visible.
    if (markers.length > 0) {
      createSeriesMarkers(
        series,
        markers.map(
          (m): SeriesMarker<Time> => ({
            time: m.date as Time,
            position: m.position,
            color: m.color,
            shape: m.shape,
            text: m.text,
          }),
        ),
      );
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartApiRef.current = null;
    };
    // rebuildKey captures every dependency that should trigger a rebuild.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rebuildKey]);

  return (
    <div className="relative w-full" style={{ height }}>
      <div ref={containerRef} className="h-full w-full" />
      <div className="absolute right-1 top-1 z-10 flex flex-col gap-0.5">
        <button
          onClick={() => adjustZoom(1.3)}
          title="Acercar"
          className="flex h-6 w-6 items-center justify-center rounded border bg-background/80 text-sm text-muted-foreground backdrop-blur transition-colors hover:bg-muted hover:text-foreground"
        >
          +
        </button>
        <button
          onClick={() => adjustZoom(1 / 1.3)}
          title="Alejar"
          className="flex h-6 w-6 items-center justify-center rounded border bg-background/80 text-sm text-muted-foreground backdrop-blur transition-colors hover:bg-muted hover:text-foreground"
        >
          −
        </button>
      </div>
    </div>
  );
}
