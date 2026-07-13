"use client";

import { useState, useMemo } from "react";
import type { DividendYield } from "@/lib/types";
import { formatEur, formatCurrency, plColor } from "@/lib/format";

type SortKey =
  | "name"
  | "country"
  | "currency"
  | "total_invested"
  | "current_value"
  | "pl"
  | "pl_pct";

type SortDir = "asc" | "desc";

function num(v: string | number): number {
  return typeof v === "string" ? Number.parseFloat(v) || 0 : v;
}

export function DividendYieldTable({
  data,
}: Readonly<{ data: DividendYield[] }>) {
  const [sortKey, setSortKey] = useState<SortKey>("pl");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const enriched = useMemo(
    () =>
      data.map((d) => {
        const invested = num(d.total_invested);
        const value = num(d.current_value);
        const pl = invested > 0 && value > 0 ? value - invested : 0;
        const plPct = invested > 0 && value > 0 ? (pl / invested) * 100 : 0;
        return { ...d, pl, plPct };
      }),
    [data],
  );

  const sorted = useMemo(() => {
    const arr = [...enriched];
    arr.sort((a, b) => {
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
        case "currency":
          va = (a.currency ?? "EUR").toLowerCase();
          vb = (b.currency ?? "EUR").toLowerCase();
          break;
        case "pl":
          va = a.pl;
          vb = b.pl;
          break;
        case "pl_pct":
          va = a.plPct;
          vb = b.plPct;
          break;
        default:
          va = num((a as Record<string, unknown>)[sortKey] as string);
          vb = num((b as Record<string, unknown>)[sortKey] as string);
      }
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return arr;
  }, [enriched, sortKey, sortDir]);

  const totals = useMemo(() => {
    let invested = 0;
    let value = 0;
    let pl = 0;
    for (const d of enriched) {
      invested += num(d.total_invested);
      value += num(d.current_value);
      pl += d.pl;
    }
    const plPct = invested > 0 ? (pl / invested) * 100 : 0;
    return { invested, value, pl, plPct };
  }, [enriched]);

  if (data.length === 0)
    return <p className="text-muted-foreground text-sm">Sin datos</p>;

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function SortHeader({
    k,
    children,
    align = "right",
    className,
  }: {
    k: SortKey;
    children: React.ReactNode;
    align?: "left" | "right";
    className?: string;
  }) {
    const active = sortKey === k;
    return (
      <th
        className={`py-2 cursor-pointer select-none hover:text-foreground transition-colors ${className ?? ""} ${align === "left" ? "text-left" : "text-right"}`}
        onClick={() => handleSort(k)}
      >
        <span className={active ? "text-foreground" : ""}>
          {children} {active ? (sortDir === "asc" ? "↑" : "↓") : ""}
        </span>
      </th>
    );
  }

  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <h3 className="text-sm font-medium text-muted-foreground mb-4">
        Rendimiento
        <span className="ml-2 text-xs text-muted-foreground/60">
          ({data.length} posiciones)
        </span>
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-muted-foreground text-xs">
              <SortHeader k="name" align="left">
                Empresa
              </SortHeader>
              <SortHeader
                k="country"
                align="left"
                className="hidden md:table-cell"
              >
                País
              </SortHeader>
              <SortHeader k="currency" align="left" className="hidden sm:table-cell">
                Divisa
              </SortHeader>
              <SortHeader k="total_invested">
                Invertido
              </SortHeader>
              <SortHeader k="current_value">Valor actual</SortHeader>
              <SortHeader k="pl">+/-</SortHeader>
              <SortHeader k="pl_pct" className="hidden sm:table-cell">
                % +/-
              </SortHeader>
            </tr>
          </thead>
          <tbody>
            {sorted.map((d) => {
              const isNonEur = d.currency !== "EUR";
              const currencyTooltip = (() => {
                if (!d.original_price || !isNonEur) return undefined;
                const priceStr = formatCurrency(d.original_price, d.currency);
                const fxStr = d.fx_rate
                  ? ` (1 EUR = ${Number.parseFloat(d.fx_rate).toFixed(4)} ${d.currency})`
                  : "";
                return `${priceStr}${fxStr}`;
              })();
              return (
                <tr
                  key={d.isin}
                  className="border-b border-border/50 hover:bg-muted/30"
                >
                  <td
                    className="py-2 text-foreground max-w-48 truncate"
                    title={d.name}
                  >
                    <span className="sm:hidden font-medium">
                      {(d.ticker ?? d.name).slice(0, 5)}
                    </span>
                    <span className="hidden sm:inline">{d.name}</span>
                  </td>
                  <td className="py-2 text-muted-foreground text-sm hidden md:table-cell">
                    {d.country ?? "—"}
                  </td>
                  <td className="py-2 text-muted-foreground text-sm hidden sm:table-cell">
                    <span
                      className={isNonEur ? "text-blue-400 font-medium" : ""}
                      title={currencyTooltip}
                    >
                      {d.currency ?? "EUR"}
                    </span>
                  </td>
                  <td className="py-2 text-right">
                    {num(d.total_invested) > 0
                      ? formatEur(d.total_invested)
                      : "—"}
                  </td>
                  <td className="py-2 text-right">
                    {num(d.current_value) > 0
                      ? formatEur(d.current_value)
                      : "—"}
                    {d.original_price &&
                      isNonEur &&
                      num(d.current_value) > 0 && (
                        <span className="block text-xs text-muted-foreground">
                          {formatCurrency(
                            num(d.original_price) * num(d.qty_remaining),
                            d.currency,
                          )}
                        </span>
                      )}
                  </td>
                  <td className={`py-2 text-right ${plColor(d.pl)}`}>
                    {d.pl !== 0 ? formatEur(d.pl) : "—"}
                  </td>
                  <td
                    className={`py-2 text-right hidden sm:table-cell ${plColor(d.plPct)}`}
                  >
                    {d.plPct !== 0
                      ? `${d.plPct > 0 ? "+" : ""}${d.plPct.toFixed(1)}%`
                      : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-border font-semibold text-foreground">
              <td className="py-3" colSpan={2}>
                Total
              </td>
              <td className="py-3 hidden sm:table-cell" />
              <td className="py-3 text-right">{formatEur(totals.invested)}</td>
              <td className="py-3 text-right">{formatEur(totals.value)}</td>
              <td className={`py-3 text-right ${plColor(totals.pl)}`}>
                {formatEur(totals.pl)}
              </td>
              <td
                className={`py-3 text-right hidden sm:table-cell ${plColor(totals.plPct)}`}
              >
                {totals.plPct > 0 ? "+" : ""}
                {totals.plPct.toFixed(1)}%
              </td>
            </tr>
          </tfoot>
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
