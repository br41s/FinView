"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { DividendsByCountry } from "@/lib/types";
import { formatEur } from "@/lib/format";

const COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316", "#84cc16", "#6366f1",
];

interface Props {
  data: DividendsByCountry[];
  activeCountry?: string | null;
  onCountryClick?: (country: string | null) => void;
}

export function DividendsByCountryChart({ data, activeCountry, onCountryClick }: Readonly<Props>) {
  const chartData = data.map((d, i) => ({
    name: d.country,
    value: Number.parseFloat(d.gross),
    withholding: Number.parseFloat(d.withholding),
    count: d.count,
    fill: COLORS[i % COLORS.length],
  }));

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <h3 className="text-sm font-medium text-muted-foreground mb-4">
        Dividendos por país
        {onCountryClick && (
          <span className="ml-2 text-xs font-normal opacity-60">— pulsa un sector para filtrar</span>
        )}
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={110}
            paddingAngle={2}
            dataKey="value"
            cursor={onCountryClick ? "pointer" : undefined}
            onClick={(entry) => onCountryClick?.(activeCountry === entry.name ? null : entry.name as string)}
          >
            {chartData.map((entry) => (
              <Cell
                key={entry.name}
                fill={entry.fill}
                opacity={activeCountry == null || activeCountry === entry.name ? 1 : 0.3}
                stroke={activeCountry === entry.name ? "var(--foreground)" : "none"}
                strokeWidth={activeCountry === entry.name ? 2 : 0}
              />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ backgroundColor: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8 }}
            formatter={(value) => formatEur(Number(value))}
            labelStyle={{ color: "var(--muted-foreground)" }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, color: "var(--muted-foreground)" }}
            formatter={(value) => value}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
