"use client";

import { useState, useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import type { CompanyDividendsYearly } from "@/lib/types";
import { formatEur } from "@/lib/format";

const YEAR_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316",
];

type ViewMode = "year" | "cumulative";

export function CompanyDividendsChart({
  data,
}: Readonly<{ data: CompanyDividendsYearly[] }>) {
  const [mode, setMode] = useState<ViewMode>("year");

  const years = useMemo(() => {
    const ySet = new Set<string>();
    for (const d of data) {
      for (const y of Object.keys(d.years)) ySet.add(y);
    }
    return Array.from(ySet).sort((a, b) => a.localeCompare(b));
  }, [data]);

  const chartData = useMemo(() => {
    return data.map((d) => {
      const entry: Record<string, string | number> = {
        ticker: d.ticker,
        name: d.name,
      };
      if (mode === "year") {
        for (const y of years) {
          entry[y] = Number.parseFloat(d.years[y] || "0");
        }
      } else {
        let running = 0;
        for (const y of years) {
          running += Number.parseFloat(d.years[y] || "0");
          entry[y] = Math.round(running * 100) / 100;
        }
      }
      return entry;
    });
  }, [data, years, mode]);

  if (data.length === 0) return null;

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
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
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{ bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis
            dataKey="ticker"
            tick={{ fill: "#ccc", fontSize: 11 }}
            angle={-45}
            textAnchor="end"
            height={60}
            interval={0}
          />
          <YAxis tick={{ fill: "#999", fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1a1a1a",
              border: "1px solid #333",
              borderRadius: 8,
            }}
            formatter={(value) => formatEur(Number(value))}
            labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ""}
            labelStyle={{ color: "#ddd" }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {years.map((y, i) => (
            <Bar
              key={y}
              dataKey={y}
              fill={YEAR_COLORS[i % YEAR_COLORS.length]}
              radius={[4, 4, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
