"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { TopDividendPayer } from "@/lib/types";
import { formatEur } from "@/lib/format";

export function TopPayersChart({ data }: Readonly<{ data: TopDividendPayer[] }>) {
  const chartData = data.map((d) => ({
    name: d.name.length > 18 ? d.name.slice(0, 18) + "…" : d.name,
    fullName: d.name,
    Bruto: Number.parseFloat(d.gross),
    Retención: Number.parseFloat(d.withholding),
  }));

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
      <h3 className="text-sm font-medium text-neutral-400 mb-4">Top pagadores de dividendos</h3>
      <ResponsiveContainer width="100%" height={350}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" horizontal={false} />
          <XAxis type="number" tick={{ fill: "#999", fontSize: 11 }} />
          <YAxis
            type="category"
            dataKey="name"
            width={150}
            tick={{ fill: "#ccc", fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1a1a", border: "1px solid #333", borderRadius: 8 }}
            formatter={(value: number) => formatEur(value)}
            labelFormatter={(_, payload) => payload?.[0]?.payload?.fullName ?? ""}
            labelStyle={{ color: "#ddd" }}
          />
          <Bar dataKey="Bruto" fill="#10b981" radius={[0, 4, 4, 0]} />
          <Bar dataKey="Retención" fill="#ef4444" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
