"use client";

import type { DashboardStats } from "@/lib/types";
import { formatEur, plColor } from "@/lib/format";

function Card({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
      <p className="text-xs text-neutral-500 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-xl font-semibold ${className ?? "text-neutral-100"}`}>{value}</p>
    </div>
  );
}

export function StatsCards({ stats }: { stats: DashboardStats }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      <Card label="Transacciones" value={stats.total_transactions.toString()} />
      <Card label="Dividendos brutos" value={formatEur(stats.total_dividends_eur)} />
      <Card
        label="Ganancias"
        value={formatEur(stats.total_gains_eur)}
        className="text-green-400"
      />
      <Card
        label="Pérdidas"
        value={formatEur(stats.total_losses_eur)}
        className="text-red-400"
      />
      <Card
        label="P&L neto"
        value={formatEur(stats.net_pl_eur)}
        className={plColor(stats.net_pl_eur)}
      />
    </div>
  );
}
