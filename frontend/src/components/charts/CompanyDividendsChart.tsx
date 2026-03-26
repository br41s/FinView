"use client";

import { useState, useMemo, useCallback } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { CompanyDividendsYearly } from "@/lib/types";
import { formatEur } from "@/lib/format";

const PALETTE = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316", "#84cc16", "#14b8a6",
  "#a855f7", "#f43f5e", "#0ea5e9", "#eab308", "#22c55e",
  "#d946ef", "#fb923c", "#2dd4bf", "#818cf8", "#fbbf24",
];

interface CompanyLine {
  key: string;
  ticker: string;
  name: string;
  color: string;
}

type ViewMode = "year" | "cumulative";

export function CompanyDividendsChart({
  data,
}: Readonly<{ data: CompanyDividendsYearly[] }>) {
  const [mode, setMode] = useState<ViewMode>("year");
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const years = useMemo(() => {
    const s = new Set<string>();
    for (const d of data) for (const y of Object.keys(d.years)) s.add(y);
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [data]);

  const lines = useMemo<CompanyLine[]>(() => {
    const used = new Map<string, number>();
    return data.map((d, i) => {
      const n = used.get(d.ticker) ?? 0;
      used.set(d.ticker, n + 1);
      return {
        key: n > 0 ? `${d.ticker}_${n}` : d.ticker,
        ticker: d.ticker,
        name: d.name,
        color: PALETTE[i % PALETTE.length],
      };
    });
  }, [data]);

  const chartData = useMemo(
    () =>
      years.map((y) => {
        const row: Record<string, number | string> = { year: y };
        data.forEach((d, i) => {
          if (mode === "year") {
            row[lines[i].key] = Number.parseFloat(d.years[y] || "0");
          } else {
            let acc = 0;
            for (const prev of years) {
              acc += Number.parseFloat(d.years[prev] || "0");
              if (prev === y) break;
            }
            row[lines[i].key] = Math.round(acc * 100) / 100;
          }
        });
        return row;
      }),
    [data, years, lines, mode],
  );

  const focus = hoveredKey ?? activeKey;

  const renderTooltip = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ({ active, payload, label }: any) => {
      if (!active || !payload?.length) return null;
      const items = payload as Array<{ dataKey?: string; value?: number }>;
      const visible = focus
        ? items.filter((p) => p.dataKey === focus)
        : [...items]
            .filter((p) => (p.value ?? 0) > 0)
            .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
            .slice(0, 8);
      const total = focus
        ? 0
        : items.filter((p) => (p.value ?? 0) > 0).length;
      const rest = total - visible.length;
      return (
        <div className="bg-[#1a1a1a] border border-neutral-700 rounded-lg p-3 shadow-xl max-w-xs">
          <p className="text-neutral-500 text-[11px] mb-1.5">{label}</p>
          {visible.map((it) => {
            const match = lines.find((c) => c.key === it.dataKey);
            return (
              <div
                key={String(it.dataKey)}
                className="flex justify-between gap-4 text-xs py-0.5"
              >
                <span className="truncate" style={{ color: match?.color }}>
                  {match?.ticker ?? String(it.dataKey)}
                </span>
                <span className="text-neutral-200 font-mono tabular-nums shrink-0">
                  {formatEur(it.value ?? 0)}
                </span>
              </div>
            );
          })}
          {rest > 0 && (
            <p className="text-neutral-600 text-[10px] mt-1">
              … y {rest} más
            </p>
          )}
        </div>
      );
    },
    [focus, lines],
  );

  const toggle = useCallback(
    (key: string) => setActiveKey((p) => (p === key ? null : key)),
    [],
  );

  if (data.length === 0 || years.length < 2) return null;

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-neutral-400">
          Dividendos por empresa
        </h3>
        <div className="flex bg-neutral-800 rounded-lg p-0.5">
          <button
            onClick={() => setMode("year")}
            className={`px-3 py-1 text-xs rounded-md transition-colors ${
              mode === "year"
                ? "bg-blue-600 text-white"
                : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            Por año
          </button>
          <button
            onClick={() => setMode("cumulative")}
            className={`px-3 py-1 text-xs rounded-md transition-colors ${
              mode === "cumulative"
                ? "bg-blue-600 text-white"
                : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            Acumulado
          </button>
        </div>
      </div>

      <div className="flex gap-4">
        {/* Left: company tickers */}
        <nav className="flex flex-col gap-0.5 min-w-22.5 justify-center overflow-y-auto pr-3 border-r border-neutral-800">
          {lines.map((l) => {
            const on = !focus || focus === l.key;
            return (
              <button
                key={l.key}
                onClick={() => toggle(l.key)}
                onMouseEnter={() => setHoveredKey(l.key)}
                onMouseLeave={() => setHoveredKey(null)}
                className="flex items-center gap-2 px-1.5 py-1 rounded text-left transition-all hover:bg-neutral-800/50"
                title={l.name}
              >
                <span
                  className="w-3 h-0.75 rounded-full shrink-0 transition-colors"
                  style={{ backgroundColor: on ? l.color : "#555" }}
                />
                <span
                  className="text-[11px] font-mono truncate transition-colors"
                  style={{ color: on ? "#e5e5e5" : "#555" }}
                >
                  {l.ticker}
                </span>
              </button>
            );
          })}
        </nav>

        {/* Chart */}
        <div className="flex-1 min-w-0">
          <ResponsiveContainer width="100%" height={Math.max(400, lines.length * 24)}>
            <LineChart
              data={chartData}
              margin={{ top: 10, right: 20, bottom: 5, left: 20 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis
                dataKey="year"
                tick={{ fill: "#ccc", fontSize: 12 }}
                axisLine={{ stroke: "#555" }}
                interval={0}
              />
              <YAxis
                orientation="right"
                tick={{ fill: "#999", fontSize: 11 }}
                axisLine={{ stroke: "#555" }}
                tickFormatter={(v: number) =>
                  v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)
                }
              />
              <Tooltip content={renderTooltip} />
              {lines.map((l) => {
                const isFocused = focus === l.key;
                const isDimmed = focus !== null && !isFocused;
                return (
                  <Line
                    key={l.key}
                    type="monotone"
                    dataKey={l.key}
                    name={l.name}
                    stroke={l.color}
                    strokeOpacity={isDimmed ? 0.12 : 1}
                    strokeWidth={isFocused ? 3 : 1.5}
                    dot={
                      isFocused
                        ? { r: 4, fill: l.color, strokeWidth: 0 }
                        : false
                    }
                    activeDot={
                      isDimmed
                        ? false
                        : {
                            r: 5,
                            fill: l.color,
                            stroke: "#1a1a1a",
                            strokeWidth: 2,
                            cursor: "pointer",
                            onClick: () => toggle(l.key),
                          }
                    }
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
