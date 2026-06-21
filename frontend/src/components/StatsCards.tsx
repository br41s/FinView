"use client";

import { useState, useRef, useEffect } from "react";
import type { DashboardStats, WithholdingsByCountry } from "@/lib/types";
import { formatEur, plColor } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";

const FISCAL_NOTES: Record<string, string> = {
  "Estados Unidos de América": "CDI 15%. Deducible al 100% en casilla 588.",
  Alemania:
    "Ret. ~26%. Deducible hasta 15% (CDI). Exceso reclamable en origen.",
  Francia: "Ret. 25%. Deducible hasta 15% (CDI). Exceso reclamable en origen.",
  Suiza: "Ret. 35%. Deducible hasta 15% (CDI). Exceso reclamable (form. 6300).",
  "Reino Unido": "Sin retención en origen.",
  Brasil: "Sin retención en origen.",
  Portugal: "Ret. 28%. Deducible hasta 15% (CDI). Exceso reclamable.",
  "Países Bajos": "Ret. 15%. Deducible al 100% en casilla 588.",
  Italia: "Ret. 26%. Deducible hasta 15% (CDI). Exceso reclamable.",
  Irlanda: "Sin retención sobre dividendos para no residentes.",
};

function StatCard({
  label,
  value,
  className,
  sensitive = true,
}: {
  readonly label: string;
  readonly value: string;
  readonly className?: string;
  readonly sensitive?: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
          {label}
        </p>
        <p
          className={`text-xl font-semibold ${sensitive ? "fv-sensitive" : ""} ${className ?? ""}`}
        >
          {value}
        </p>
      </CardContent>
    </Card>
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
  const total = foreign.reduce(
    (sum, w) => sum + Number.parseFloat(w.withholding),
    0,
  );

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <Card ref={ref} className="relative">
      <CardContent className="p-5">
        <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
          Retenciones en origen
        </p>
        <p className="text-xl font-semibold text-amber-400 fv-sensitive">
          {formatEur(total)}
        </p>
        {foreign.length > 0 && (
          <>
            <button
              onClick={() => setOpen(!open)}
              className="text-xs text-primary mt-1.5 hover:text-primary/80 flex items-center gap-1"
            >
              {open ? "Ocultar" : "Ver detalle"}
              <span
                className={`transition-transform ${open ? "rotate-180" : ""}`}
              >
                ▾
              </span>
            </button>
            {open && (
              <div className="absolute top-full left-0 mt-1 w-80 bg-popover border border-border rounded-lg p-3 z-50 shadow-xl max-h-64 overflow-y-auto">
                {foreign.map((w) => {
                  const note =
                    FISCAL_NOTES[w.country] ??
                    `Retención ${w.effective_rate}%. Consultar CDI.`;
                  return (
                    <div
                      key={w.country}
                      className="py-2 border-b border-border last:border-0"
                    >
                      <div className="flex justify-between text-sm">
                        <span className="font-medium">{w.country}</span>
                        <span className="text-amber-400">
                          {formatEur(w.withholding)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Tasa efectiva: {w.effective_rate}%
                      </p>
                      <p className="text-xs text-muted-foreground/80 mt-0.5">
                        {note}
                      </p>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
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
  const spanishTotal = spanishWhg
    ? Number.parseFloat(spanishWhg.withholding)
    : 0;

  if (!showFiscal) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <StatCard
          label="Transacciones"
          value={stats.total_transactions.toString()}
          sensitive={false}
        />
        <StatCard
          label="Dividendos brutos"
          value={formatEur(stats.total_dividends_eur)}
        />
        <StatCard
          label="P&L neto"
          value={formatEur(stats.net_pl_eur)}
          className={plColor(stats.net_pl_eur)}
        />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
      <StatCard
        label="Transacciones"
        value={stats.total_transactions.toString()}
      />
      <StatCard
        label="Dividendos brutos"
        value={formatEur(stats.total_dividends_eur)}
      />
      <StatCard
        label="Retención ES (19%)"
        value={formatEur(spanishTotal)}
        className="text-orange-400"
      />
      <ForeignWithholdingsCard withholdings={withholdings} />
      <StatCard
        label="Ganancias"
        value={formatEur(stats.total_gains_eur)}
        className="text-green-400"
      />
      <StatCard
        label="Pérdidas"
        value={formatEur(stats.total_losses_eur)}
        className="text-red-400"
      />
      <StatCard
        label="P&L neto"
        value={formatEur(stats.net_pl_eur)}
        className={plColor(stats.net_pl_eur)}
      />
    </div>
  );
}
