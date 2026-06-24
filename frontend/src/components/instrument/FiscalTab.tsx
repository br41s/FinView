"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { usePositionDetail } from "./usePositionDetail";

function eur(v: number | null | undefined, d = 2): string {
  return v == null
    ? "—"
    : v.toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d }) + " €";
}

export function FiscalTab({ isin, symbol }: { isin: string | null; symbol: string }) {
  const { status, detail } = usePositionDetail(isin);

  if (status === "loading" && isin) return <Skeleton className="h-[260px] w-full" />;

  if (!detail) {
    return (
      <div className="flex h-[240px] flex-col items-center justify-center gap-1 text-center">
        <p className="text-sm text-muted-foreground">Sin datos fiscales para {symbol}.</p>
        <p className="text-xs text-muted-foreground/70">
          Solo disponible para posiciones abiertas en cartera.
        </p>
      </div>
    );
  }

  const plPositive = (detail.unrealized_pl_eur ?? 0) >= 0;

  return (
    <div className="space-y-3">
      {/* Cost basis / value summary */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <Stat label="Cantidad" value={detail.total_quantity.toLocaleString("es-ES")} />
        <Stat label="País" value={detail.country ?? "—"} />
        <Stat label="Coste medio" value={eur(detail.avg_cost_eur, 4)} />
        <Stat label="Coste total" value={eur(detail.total_cost_eur)} />
        <Stat label="Valor mercado" value={eur(detail.market_value_eur)} />
        <Stat
          label="P&L no realizada"
          value={
            <span className={plPositive ? "text-emerald-600" : "text-red-600"}>
              {eur(detail.unrealized_pl_eur)}
              {detail.unrealized_pl_pct != null && ` (${detail.unrealized_pl_pct.toFixed(1)}%)`}
            </span>
          }
        />
      </div>

      {/* Per-broker breakdown (the cross-broker FIFO inputs) */}
      {detail.accounts.length > 0 && (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-xs tabular-nums">
            <thead className="bg-muted/80 text-[10px] uppercase text-muted-foreground">
              <tr>
                <th className="px-2 py-1 text-left">Bróker</th>
                <th className="px-2 py-1 text-right">Cantidad</th>
                <th className="px-2 py-1 text-right">Coste</th>
                <th className="px-2 py-1 text-right">Valor</th>
              </tr>
            </thead>
            <tbody>
              {detail.accounts.map((a, i) => (
                <tr key={`${a.broker}-${a.account_id}-${i}`} className="border-t">
                  <td className="px-2 py-1">{a.broker}</td>
                  <td className="px-2 py-1 text-right">{a.quantity.toLocaleString("es-ES")}</td>
                  <td className="px-2 py-1 text-right text-muted-foreground">{eur(a.cost_eur)}</td>
                  <td className="px-2 py-1 text-right">{eur(a.value_eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-muted-foreground/70">
        Casillas IRPF y FIFO cross-bróker en la vista fiscal del dashboard.
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border p-2">
      <p className="text-[10px] uppercase text-muted-foreground">{label}</p>
      <p className="font-medium">{value}</p>
    </div>
  );
}
