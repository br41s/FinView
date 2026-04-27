"use client";

import type { DividendSummary, DividendYield } from "@/lib/types";
import { formatEur } from "@/lib/format";

function pctCobrado(netEur: string, investedEur: string): string {
  const net = Number.parseFloat(netEur);
  const invested = Number.parseFloat(investedEur);
  if (!invested || invested <= 0) return "—";
  return `${((net / invested) * 100).toFixed(2)}%`;
}

export function DividendsTable({
  dividends,
  dividendYield = [],
}: Readonly<{ dividends: DividendSummary[]; dividendYield?: DividendYield[] }>) {
  if (dividends.length === 0)
    return <p className="text-muted-foreground text-sm">Sin datos</p>;

  const investedByIsin = new Map(dividendYield.map((d) => [d.isin, d.total_invested]));

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="text-left py-2">Empresa</th>
            <th className="text-left py-2 hidden sm:table-cell">País</th>
            <th className="text-right py-2 hidden sm:table-cell">Invertido</th>
            <th className="text-right py-2">Bruto</th>
            <th className="text-right py-2 hidden sm:table-cell">Retención</th>
            <th className="text-right py-2">Neto</th>
            <th className="text-right py-2 hidden md:table-cell">% cobrado</th>
            <th className="text-right py-2">Pagos</th>
          </tr>
        </thead>
        <tbody>
          {dividends.map((d, i) => {
            const invested = investedByIsin.get(d.isin) ?? "0";
            return (
              <tr
                key={`${d.isin}-${d.name}-${i}`}
                className="border-b border-border/50 hover:bg-muted/30"
              >
                <td className="py-2 text-foreground max-w-48 truncate" title={d.name}>
                  {d.name}
                </td>
                <td className="py-2 text-muted-foreground hidden sm:table-cell">
                  {d.country ?? "—"}
                </td>
                <td className="py-2 text-right text-muted-foreground hidden sm:table-cell">
                  {Number.parseFloat(invested) > 0 ? formatEur(invested) : "—"}
                </td>
                <td className="py-2 text-right">
                  {formatEur(d.total_gross_eur)}
                </td>
                <td className="py-2 text-right text-red-400 hidden sm:table-cell">
                  {formatEur(d.total_withholding_eur)}
                </td>
                <td className="py-2 text-right text-green-400">
                  {formatEur(d.total_net_eur)}
                </td>
                <td className="py-2 text-right text-blue-400 hidden md:table-cell">
                  {pctCobrado(d.total_net_eur, invested)}
                </td>
                <td className="py-2 text-right text-muted-foreground">
                  {d.payment_count}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
