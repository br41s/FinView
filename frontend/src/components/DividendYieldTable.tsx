"use client";

import type { DividendYield } from "@/lib/types";
import { formatEur } from "@/lib/format";

export function DividendYieldTable({ data }: Readonly<{ data: DividendYield[] }>) {
  if (data.length === 0) return <p className="text-muted-foreground text-sm">Sin datos</p>;

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <h3 className="text-sm font-medium text-muted-foreground mb-4">Rendimiento de dividendos</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
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
                <tr key={d.isin} className="border-b border-border/50 hover:bg-muted/30">
                  <td className="py-2 text-foreground max-w-48 truncate" title={d.name}>
                    {d.name}
                  </td>
                  <td className="py-2 text-muted-foreground">{d.country ?? "—"}</td>
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
                  <td className="py-2 text-right text-muted-foreground">{d.payment_count}</td>
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
  if (value <= 0) return <span className="text-muted-foreground/70">—</span>;

  let color = "text-muted-foreground";
  if (value >= 10) color = "text-green-400 font-semibold";
  else if (value >= 5) color = "text-green-400";
  else if (value >= 3) color = "text-blue-400";

  return <span className={color}>{value.toFixed(2)}%</span>;
}
