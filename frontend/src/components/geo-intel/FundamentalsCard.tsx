"use client";

import { useEffect, useState } from "react";
import { api, type Fundamentals } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";
import { fmtPct } from "@/lib/format";

/**
 * Fundamental context for a ticker on the Ideas desk.
 *
 * Colour for a thesis a human is reading — never an input to a signal, a score
 * or a gate. yfinance `.info` is scraped and has no stable contract, so every
 * field is optional and the whole card disappears when there's nothing to show,
 * rather than rendering a grid of dashes.
 */

function compactMoney(v: number, currency?: string): string {
  const abs = Math.abs(v);
  const unit = abs >= 1e12 ? ["T", 1e12] : abs >= 1e9 ? ["B", 1e9] : abs >= 1e6 ? ["M", 1e6] : ["", 1];
  const n = v / (unit[1] as number);
  const sym = currency === "EUR" ? "€" : currency === "USD" ? "$" : "";
  return `${sym}${n.toFixed(n >= 100 ? 0 : 1)}${unit[0]}`;
}

function num(v: number): string {
  return v.toFixed(1);
}

export function FundamentalsCard({ symbol }: { symbol: string }) {
  // The result is stored with the symbol it answers, so a symbol change reads
  // as "loading" by derivation rather than a synchronous reset in the effect.
  const [loaded, setLoaded] = useState<{ symbol: string; data: Fundamentals | null } | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    api.charts
      .fundamentals(symbol)
      .then((d) => {
        if (!cancelled) setLoaded({ symbol, data: d });
      })
      // Best-effort by design: a failure and "this ticker has no fundamentals"
      // are the same outcome here — show nothing.
      .catch((e) => {
        bestEffort("fundamentals for the signal panel")(e);
        if (!cancelled) setLoaded({ symbol, data: null });
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const current = loaded?.symbol === symbol ? loaded : null;
  if (!current) {
    return (
      <p className="text-[11px] text-[rgba(31,27,22,0.4)]">Cargando fundamentales…</p>
    );
  }
  const data = current.data;
  if (!data || Object.keys(data).length === 0) return null;

  const rows: [string, string][] = [];
  if (data.market_cap) rows.push(["Capitalización", compactMoney(data.market_cap, data.currency)]);
  if (data.trailing_pe) rows.push(["PER", num(data.trailing_pe)]);
  if (data.forward_pe) rows.push(["PER fwd", num(data.forward_pe)]);
  if (data.price_to_book) rows.push(["P/VC", num(data.price_to_book)]);
  if (data.dividend_yield) rows.push(["Dividendo", fmtPct(100 * data.dividend_yield)]);
  if (data.profit_margins) rows.push(["Margen neto", fmtPct(100 * data.profit_margins)]);
  if (data.return_on_equity) rows.push(["ROE", fmtPct(100 * data.return_on_equity)]);
  if (data.revenue_growth) rows.push(["Crec. ventas", fmtPct(100 * data.revenue_growth)]);
  if (data.debt_to_equity) rows.push(["Deuda/FP", num(data.debt_to_equity)]);
  if (data.beta) rows.push(["Beta", num(data.beta)]);

  if (rows.length === 0 && !data.sector) return null;

  return (
    <div className="mt-3 border-t border-[rgba(31,27,22,0.12)] pt-3">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.5)]">
        Fundamentales
      </p>
      {(data.sector || data.industry) && (
        <p className="mt-1.5 text-[11px] text-[rgba(31,27,22,0.6)]">
          {[data.sector, data.industry].filter(Boolean).join(" · ")}
        </p>
      )}
      {rows.length > 0 && (
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
          {rows.map(([label, value]) => (
            <div key={label} className="flex items-baseline justify-between gap-2">
              <span className="text-[10px] text-[rgba(31,27,22,0.5)]">{label}</span>
              <span
                className="text-[11px] tabular-nums text-[#1F1B16]"
                style={{ fontFamily: "var(--fv-font-jetbrains), monospace" }}
              >
                {value}
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="mt-2 text-[10px] italic text-[rgba(31,27,22,0.4)]">
        Contexto para la tesis. No alimenta ninguna señal ni puntuación.
      </p>
    </div>
  );
}
