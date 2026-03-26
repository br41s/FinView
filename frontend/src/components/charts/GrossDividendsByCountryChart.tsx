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
import type { DividendsByCountry } from "@/lib/types";
import { formatEur } from "@/lib/format";

export function GrossDividendsByCountryChart({ data }: Readonly<{ data: DividendsByCountry[] }>) {
  const chartData = data.map((d) => ({
    country: d.country,
    Bruto: Number.parseFloat(d.gross),
  }));

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
      <h3 className="text-sm font-medium text-neutral-400 mb-4">Dividendos brutos por país</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="country" tick={{ fill: "#999", fontSize: 11 }} />
          <YAxis tick={{ fill: "#999", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1a1a", border: "1px solid #333", borderRadius: 8 }}
            formatter={(value: number) => formatEur(value)}
            labelStyle={{ color: "#999" }}
          />
          <Bar dataKey="Bruto" fill="#3b82f6" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
