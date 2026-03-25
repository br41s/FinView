"use client";

import { useState, useRef, useEffect } from "react";
import type { DashboardStats, WithholdingsByCountry } from "@/lib/types";
import { formatEur, plColor } from "@/lib/format";

const FISCAL_NOTES: Record<string, string> = {
  "Estados Unidos de América": "CDI 15%. Deducible al 100% en casilla 588.",
  "Alemania": "Ret. ~26%. Deducible hasta 15% (CDI). Exceso reclamable en origen.",
  "Francia": "Ret. 25%. Deducible hasta 15% (CDI). Exceso reclamable en origen.",
  "Suiza": "Ret. 35%. Deducible hasta 15% (CDI). Exceso reclamable (form. 6300).",
  "Reino Unido": "Sin retención en origen.",
  "Brasil": "Sin retención en origen.",
  "Portugal": "Ret. 28%. Deducible hasta 15% (CDI). Exceso reclamable.",
  "Países Bajos": "Ret. 15%. Deducible al 100% en casilla 588.",
  "Italia": "Ret. 26%. Deducible hasta 15% (CDI). Exceso reclamable.",
  "Irlanda": "Sin retención sobre dividendos para no residentes.",
};

function Card({
  label,
  value,
  className,
}: {
  readonly label: string;
  readonly value: string;
  readonly className?: string;
}) {
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
      <p className="text-xs text-neutral-500 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-xl font-semibold ${className ?? "text-neutral-100"}`}>{value}</p>
    </div>
  );
}

function ForeignWithholdingsCard({
  withholdings,
}: {
  readonly withholdings: readonly WithholdingsByCountry[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const foreign = withholdings.filter((w) => w.country !== "España");
  const total = foreign.reduce((sum, w) => sum + Number.parseFloat(w.withholding), 0);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div ref={ref} className="bg-neutral-900 border border-neutral-800 rounded-xl p-5 relative">
      <p className="text-xs text-neutral-500 uppercase tracking-wide mb-1">
        Retenciones en origen
      </p>
      <p className="text-xl font-semibold text-amber-400">{formatEur(total)}</p>
      {foreign.length > 0 && (
        <>
          <button
            onClick={() => setOpen(!open)}
            className="text-xs text-blue-400 mt-1.5 hover:text-blue-300 flex items-center gap-1"
          >
            {open ? "Ocultar" : "Ver detalle"}
            <span className={`transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
          </button>
          {open && (
            <div className="absolute top-full left-0 mt-1 w-80 bg-neutral-800 border border-neutral-700 rounded-lg p-3 z-50 shadow-xl max-h-64 overflow-y-auto">
              {foreign.map((w) => {
                const note =
                  FISCAL_NOTES[w.country] ?? `Retención ${w.effective_rate}%. Consultar CDI.`;
                return (
                  <div key={w.country} className="py-2 border-b border-neutral-700 last:border-0">
                    <div className="flex justify-between text-sm">
                      <span className="text-neutral-200 font-medium">{w.country}</span>
                      <span className="text-amber-400">{formatEur(w.withholding)}</span>
                    </div>
                    <p className="text-xs text-neutral-500 mt-0.5">
                      Tasa efectiva: {w.effective_rate}%
                    </p>
                    <p className="text-xs text-neutral-400 mt-0.5">{note}</p>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function StatsCards({
  stats,
  withholdings,
  showFiscal,
}: {
  readonly stats: DashboardStats;
  readonly withholdings: readonly WithholdingsByCountry[];
  readonly showFiscal: boolean;
}) {
  const spanishWhg = withholdings.find((w) => w.country === "España");
  const spanishTotal = spanishWhg ? Number.parseFloat(spanishWhg.withholding) : 0;

  if (!showFiscal) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <Card label="Transacciones" value={stats.total_transactions.toString()} />
        <Card label="Dividendos brutos" value={formatEur(stats.total_dividends_eur)} />
        <Card label="P&L neto" value={formatEur(stats.net_pl_eur)} className={plColor(stats.net_pl_eur)} />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
      <Card label="Transacciones" value={stats.total_transactions.toString()} />
      <Card label="Dividendos brutos" value={formatEur(stats.total_dividends_eur)} />
      <Card label="Retención ES (19%)" value={formatEur(spanishTotal)} className="text-orange-400" />
      <ForeignWithholdingsCard withholdings={withholdings} />
      <Card label="Ganancias" value={formatEur(stats.total_gains_eur)} className="text-green-400" />
      <Card label="Pérdidas" value={formatEur(stats.total_losses_eur)} className="text-red-400" />
      <Card label="P&L neto" value={formatEur(stats.net_pl_eur)} className={plColor(stats.net_pl_eur)} />
    </div>
  );
}
