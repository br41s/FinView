"use client";

import { useState } from "react";
import type { DividendSummary, DividendYield } from "@/lib/types";
import { SortHeader, type SortDir } from "@/components/SortHeader";
import { formatEur } from "@/lib/format";

type SortKey =
  | "name"
  | "country"
  | "invested"
  | "total_gross_eur"
  | "total_withholding_eur"
  | "total_net_eur"
  | "pct_cobrado"
  | "payment_count";

function pctCobradoValue(netEur: string, investedEur: string): number {
  const net = Number.parseFloat(netEur);
  const invested = Number.parseFloat(investedEur);
  if (!invested || invested <= 0) return 0;
  return (net / invested) * 100;
}

function pctCobrado(netEur: string, investedEur: string): string {
  const invested = Number.parseFloat(investedEur);
  if (!invested || invested <= 0) return "—";
  return `${pctCobradoValue(netEur, investedEur).toFixed(2)}%`;
}

export function DividendsTable({
  dividends,
  dividendYield = [],
}: Readonly<{ dividends: DividendSummary[]; dividendYield?: DividendYield[] }>) {
  const [sortKey, setSortKey] = useState<SortKey>("total_net_eur");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  if (dividends.length === 0)
    return <p className="text-muted-foreground text-sm">Sin datos</p>;

  const investedByIsin = new Map(dividendYield.map((d) => [d.isin, d.total_invested]));

  const enriched = dividends.map((d, i) => ({
    ...d,
    _key: `${d.isin}-${d.name}-${i}`,
    invested: investedByIsin.get(d.isin) ?? "0",
  }));

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = [...enriched].sort((a, b) => {
    let va: number | string;
    let vb: number | string;
    switch (sortKey) {
      case "name":
        va = a.name.toLowerCase();
        vb = b.name.toLowerCase();
        break;
      case "country":
        va = (a.country ?? "").toLowerCase();
        vb = (b.country ?? "").toLowerCase();
        break;
      case "invested":
        va = Number.parseFloat(a.invested) || 0;
        vb = Number.parseFloat(b.invested) || 0;
        break;
      case "pct_cobrado":
        va = pctCobradoValue(a.total_net_eur, a.invested);
        vb = pctCobradoValue(b.total_net_eur, b.invested);
        break;
      case "payment_count":
        va = a.payment_count;
        vb = b.payment_count;
        break;
      default:
        va = Number.parseFloat(a[sortKey]) || 0;
        vb = Number.parseFloat(b[sortKey]) || 0;
    }
    if (va < vb) return sortDir === "asc" ? -1 : 1;
    if (va > vb) return sortDir === "asc" ? 1 : -1;
    return 0;
  });

  const headerProps = { sortKey, sortDir, onSort: handleSort };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <SortHeader {...headerProps} k="name" align="left">Empresa</SortHeader>
            <SortHeader {...headerProps} k="country" align="left" className="hidden sm:table-cell">País</SortHeader>
            <SortHeader {...headerProps} k="invested" className="hidden sm:table-cell">Invertido</SortHeader>
            <SortHeader {...headerProps} k="total_gross_eur">Bruto</SortHeader>
            <SortHeader {...headerProps} k="total_withholding_eur" className="hidden sm:table-cell">Retención</SortHeader>
            <SortHeader {...headerProps} k="total_net_eur">Neto</SortHeader>
            <SortHeader {...headerProps} k="pct_cobrado" className="hidden md:table-cell">% cobrado</SortHeader>
            <SortHeader {...headerProps} k="payment_count">Pagos</SortHeader>
          </tr>
        </thead>
        <tbody>
          {sorted.map((d) => (
            <tr
              key={d._key}
              className="border-b border-border/50 hover:bg-muted/30"
            >
              <td className="py-2 text-foreground max-w-48 truncate" title={d.name}>
                {d.name}
              </td>
              <td className="py-2 text-muted-foreground hidden sm:table-cell">
                {d.country ?? "—"}
              </td>
              <td className="py-2 text-right text-muted-foreground hidden sm:table-cell">
                {Number.parseFloat(d.invested) > 0 ? formatEur(d.invested) : "—"}
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
                {pctCobrado(d.total_net_eur, d.invested)}
              </td>
              <td className="py-2 text-right text-muted-foreground">
                {d.payment_count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
