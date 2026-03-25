"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { PatrimonioComposition } from "@/lib/types";
import { formatEur } from "@/lib/format";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#06b6d4"];

export function PatrimonioChart({ data }: Readonly<{ data: PatrimonioComposition[] }>) {
  const chartData = data.map((d) => ({
    name: `Cas. ${d.casilla}`,
    fullName: d.description,
    value: Number.parseFloat(d.amount),
  }));

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
      <h3 className="text-sm font-medium text-neutral-400 mb-4">Composición del patrimonio (Modelo 714)</h3>
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
            wrapperStyle={{ fontSize: 12 }}
            formatter={(value, entry) => {
              const fullName = (entry.payload as { fullName?: string })?.fullName ?? value;
              return fullName.length > 40 ? fullName.slice(0, 40) + "…" : fullName;
            }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
