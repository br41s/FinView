"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { usePositionDetail } from "./usePositionDetail";

function eur(v: number | null | undefined): string {
  return v == null
    ? "—"
    : v.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
}

export function DividendosTab({ isin, symbol }: { isin: string | null; symbol: string }) {
  const { status, detail } = usePositionDetail(isin);

  if (status === "loading" && isin) return <Skeleton className="h-[220px] w-full" />;

  if (!detail || detail.dividends_by_year.length === 0) {
    return (
      <div className="flex h-[220px] flex-col items-center justify-center gap-1 text-center">
        <p className="text-sm text-muted-foreground">Sin dividendos registrados para {symbol}.</p>
        {!detail && (
          <p className="text-xs text-muted-foreground/70">
            Solo disponible para posiciones abiertas en cartera.
          </p>
        )}
      </div>
    );
  }

  const totalGross = detail.dividends_by_year.reduce((s, d) => s + d.gross_eur, 0);
  const totalNet = detail.dividends_by_year.reduce((s, d) => s + d.net_eur, 0);
  const totalCount = detail.dividends_by_year.reduce((s, d) => s + d.count, 0);

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-lg border">
        <table className="w-full text-xs tabular-nums">
          <thead className="bg-muted/80 text-[10px] uppercase text-muted-foreground">
            <tr>
              <th className="px-2 py-1 text-left">Año</th>
              <th className="px-2 py-1 text-right">Bruto</th>
              <th className="px-2 py-1 text-right">Neto</th>
              <th className="px-2 py-1 text-right">Pagos</th>
            </tr>
          </thead>
          <tbody>
            {detail.dividends_by_year.map((d) => (
              <tr key={d.year} className="border-t">
                <td className="px-2 py-1 font-medium">{d.year}</td>
                <td className="px-2 py-1 text-right">{eur(d.gross_eur)}</td>
                <td className="px-2 py-1 text-right text-emerald-600">{eur(d.net_eur)}</td>
                <td className="px-2 py-1 text-right text-muted-foreground">{d.count}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t bg-muted/40 font-medium">
            <tr>
              <td className="px-2 py-1">Total</td>
              <td className="px-2 py-1 text-right">{eur(totalGross)}</td>
              <td className="px-2 py-1 text-right text-emerald-600">{eur(totalNet)}</td>
              <td className="px-2 py-1 text-right text-muted-foreground">{totalCount}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-[11px] text-muted-foreground/70">
        Importes netos en EUR. Las retenciones por país se detallan en la vista fiscal.
      </p>
    </div>
  );
}
