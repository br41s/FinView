"use client";

import type { CapitalGain } from "@/lib/types";
import { formatEur, plColor } from "@/lib/format";

export function CapitalGainsTable({ gains }: Readonly<{ gains: CapitalGain[] }>) {
  if (gains.length === 0) return <p className="text-neutral-500 text-sm">Sin datos</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-500">
            <th className="text-left py-2">Empresa</th>
            <th className="text-left py-2">ISIN</th>
            <th className="text-left py-2">Compra</th>
            <th className="text-left py-2">Venta</th>
            <th className="text-right py-2">Cantidad</th>
            <th className="text-right py-2">Coste</th>
            <th className="text-right py-2">Venta</th>
            <th className="text-right py-2">P&L</th>
            <th className="text-left py-2">Periodo</th>
          </tr>
        </thead>
        <tbody>
          {gains.map((g) => (
            <tr key={g.id} className="border-b border-neutral-800/50 hover:bg-neutral-800/30">
              <td className="py-2 text-neutral-300">{g.name}</td>
              <td className="py-2 font-mono text-xs text-neutral-400">{g.isin}</td>
              <td className="py-2 text-neutral-300">{g.buy_date}</td>
              <td className="py-2 text-neutral-300">{g.sell_date}</td>
              <td className="py-2 text-right text-neutral-300">{g.quantity}</td>
              <td className="py-2 text-right">{formatEur(g.cost_basis_eur)}</td>
              <td className="py-2 text-right">{formatEur(g.proceeds_eur)}</td>
              <td className={`py-2 text-right font-medium ${plColor(g.realized_pl_eur)}`}>
                {formatEur(g.realized_pl_eur)}
              </td>
              <td className="py-2 text-neutral-400 text-xs">{g.holding_period ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
