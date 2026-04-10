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
    <div className="bg-card border border-border rounded-xl p-6">
      <h3 className="text-sm font-medium text-muted-foreground mb-4">Dividendos brutos por país</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="country" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
          <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ backgroundColor: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8 }}
            formatter={(value) => formatEur(Number(value))}
            labelStyle={{ color: "var(--muted-foreground)" }}
          />
          <Bar dataKey="Bruto" fill="#3b82f6" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
