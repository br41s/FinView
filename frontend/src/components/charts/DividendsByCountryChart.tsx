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

export function DividendsByCountryChart({ data }: Readonly<{ data: DividendsByCountry[] }>) {
  const chartData = data.map((d) => ({
    name: d.country,
    value: Number.parseFloat(d.gross),
    withholding: Number.parseFloat(d.withholding),
    count: d.count,
  }));

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
      <h3 className="text-sm font-medium text-neutral-400 mb-4">Dividendos por país</h3>
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
          >
            {chartData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1a1a", border: "1px solid #333", borderRadius: 8 }}
            formatter={(value) => formatEur(Number(value))}
            labelStyle={{ color: "#999" }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, color: "#999" }}
            formatter={(value) => value}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
