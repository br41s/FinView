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
import type { WithholdingsByCountry } from "@/lib/types";
import { formatEur } from "@/lib/format";

export function WithholdingsChart({ data }: Readonly<{ data: WithholdingsByCountry[] }>) {
  const chartData = data.map((d) => ({
    country: d.country,
    Retención: Number.parseFloat(d.withholding),
    "Tipo efectivo (%)": Number.parseFloat(d.effective_rate),
  }));

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <h3 className="text-sm font-medium text-muted-foreground mb-4">Retenciones por país</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="country" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
          <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ backgroundColor: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8 }}
            formatter={(value, name) =>
              name === "Tipo efectivo (%)" ? `${value}%` : formatEur(Number(value))
            }
            labelStyle={{ color: "var(--muted-foreground)" }}
          />
          <Bar dataKey="Retención" fill="#ef4444" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      {/* Rate table */}
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
        {data.map((d) => (
          <div key={d.country} className="text-xs">
            <span className="text-muted-foreground">{d.country}: </span>
            <span className="text-red-400 font-medium">{d.effective_rate}%</span>
            <span className="text-muted-foreground/70 ml-1">({formatEur(d.withholding)})</span>
          </div>
        ))}
      </div>
    </div>
  );
}
