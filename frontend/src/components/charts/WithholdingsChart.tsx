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
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
      <h3 className="text-sm font-medium text-neutral-400 mb-4">Retenciones por país</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="country" tick={{ fill: "#999", fontSize: 11 }} />
          <YAxis tick={{ fill: "#999", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1a1a", border: "1px solid #333", borderRadius: 8 }}
            formatter={(value, name) =>
              name === "Tipo efectivo (%)" ? `${value}%` : formatEur(Number(value))
            }
            labelStyle={{ color: "#999" }}
          />
          <Bar dataKey="Retención" fill="#ef4444" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      {/* Rate table */}
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
        {data.map((d) => (
          <div key={d.country} className="text-xs">
            <span className="text-neutral-400">{d.country}: </span>
            <span className="text-red-400 font-medium">{d.effective_rate}%</span>
            <span className="text-neutral-600 ml-1">({formatEur(d.withholding)})</span>
          </div>
        ))}
      </div>
    </div>
  );
}
