"use client";

import type { DividendSummary } from "@/lib/types";
import { formatEur } from "@/lib/format";

export function DividendsTable({ dividends }: Readonly<{ dividends: DividendSummary[] }>) {
  if (dividends.length === 0) return <p className="text-muted-foreground text-sm">Sin datos</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="text-left py-2">Empresa</th>
            <th className="text-left py-2">ISIN</th>
            <th className="text-left py-2">País</th>
            <th className="text-right py-2">Bruto</th>
            <th className="text-right py-2">Retención</th>
            <th className="text-right py-2">Neto</th>
            <th className="text-right py-2">Pagos</th>
          </tr>
        </thead>
        <tbody>
          {dividends.map((d, i) => (
            <tr key={`${d.isin}-${d.name}-${i}`} className="border-b border-border/50 hover:bg-muted/30">
              <td className="py-2 text-foreground max-w-48 truncate">{d.name}</td>
              <td className="py-2 font-mono text-xs text-muted-foreground">{d.isin}</td>
              <td className="py-2 text-muted-foreground">{d.country ?? "—"}</td>
              <td className="py-2 text-right">{formatEur(d.total_gross_eur)}</td>
              <td className="py-2 text-right text-red-400">{formatEur(d.total_withholding_eur)}</td>
              <td className="py-2 text-right text-green-400">{formatEur(d.total_net_eur)}</td>
              <td className="py-2 text-right text-muted-foreground">{d.payment_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
