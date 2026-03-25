"use client";

import type { DividendYield } from "@/lib/types";
import { formatEur } from "@/lib/format";

export function DividendYieldTable({ data }: Readonly<{ data: DividendYield[] }>) {
  if (data.length === 0) return <p className="text-neutral-500 text-sm">Sin datos</p>;

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
      <h3 className="text-sm font-medium text-neutral-400 mb-4">Rendimiento de dividendos</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-neutral-500">
              <th className="text-left py-2">Empresa</th>
              <th className="text-left py-2">País</th>
              <th className="text-right py-2">Dividendos</th>
              <th className="text-right py-2">Invertido</th>
              <th className="text-right py-2">% s/coste</th>
              <th className="text-right py-2">Valor actual</th>
              <th className="text-right py-2">% s/valor</th>
              <th className="text-right py-2">Pagos</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => {
              const yieldCost = Number.parseFloat(d.yield_on_cost);
              const yieldValue = Number.parseFloat(d.yield_on_value);
              return (
                <tr key={d.isin} className="border-b border-neutral-800/50 hover:bg-neutral-800/30">
                  <td className="py-2 text-neutral-200 max-w-48 truncate" title={d.name}>
                    {d.name}
                  </td>
                  <td className="py-2 text-neutral-400">{d.country ?? "—"}</td>
                  <td className="py-2 text-right text-green-400">{formatEur(d.total_dividends)}</td>
                  <td className="py-2 text-right">
                    {Number.parseFloat(d.total_invested) > 0 ? formatEur(d.total_invested) : "—"}
                  </td>
                  <td className="py-2 text-right">
                    <YieldBadge value={yieldCost} />
                  </td>
                  <td className="py-2 text-right">
                    {Number.parseFloat(d.current_value) > 0 ? formatEur(d.current_value) : "—"}
                  </td>
                  <td className="py-2 text-right">
                    <YieldBadge value={yieldValue} />
                  </td>
                  <td className="py-2 text-right text-neutral-400">{d.payment_count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function YieldBadge({ value }: Readonly<{ value: number }>) {
  if (value <= 0) return <span className="text-neutral-600">—</span>;

  let color = "text-neutral-400";
  if (value >= 10) color = "text-green-400 font-semibold";
  else if (value >= 5) color = "text-green-400";
  else if (value >= 3) color = "text-blue-400";

  return <span className={color}>{value.toFixed(2)}%</span>;
}
