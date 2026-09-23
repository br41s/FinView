import { fmt } from "@/lib/format";
import { getAccountValueDisplay } from "@/lib/portfolioValues";
import type { OhlcBar } from "@/lib/api";
import {
  executionMarkers,
  alignMarkersToBars,
  CHART_SCOPES,
  type ChartScope,
} from "@/lib/chartMarkers";
import { PriceChart } from "@/components/charts/PriceChart";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LoadingDots } from "@/components/loading-dots";

import { TX_COLORS, TX_LABELS, type Position, type PositionDetail } from "./types";

interface PositionDetailPanelProps {
  p: Position;
  detail: PositionDetail | undefined;
  isLoadingThis: boolean;
  plClass: string;
  /** OHLC cache keyed by `${isin}:${scope}`; a missing or empty entry hides the chart. */
  ohlcByIsin: Map<string, OhlcBar[]>;
  chartScope: ChartScope;
  setChartScope: (scope: ChartScope) => void;
}

// Shared between the desktop table's expanded row and the mobile card's
// expanded section — same detail content, different container.
export function PositionDetailPanel({
  p,
  detail,
  isLoadingThis,
  plClass,
  ohlcByIsin,
  chartScope,
  setChartScope,
}: PositionDetailPanelProps) {
  if (isLoadingThis && !detail) {
    return <LoadingDots text="Cargando detalle" />;
  }
  if (!detail) {
    return (
      <p className="text-sm text-muted-foreground">Error al cargar detalle</p>
    );
  }
  return (
    <div className="space-y-4">
      {/* Summary grid */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <div>
          <p className="text-xs text-muted-foreground">ISIN</p>
          <p className="font-mono text-sm">{p.isin}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Valor actual</p>
          <p className="font-medium fv-sensitive">
            {p.market_value_eur != null ? `${fmt(p.market_value_eur)} €` : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Rentabilidad</p>
          <p className={`font-medium ${plClass}`}>
            {p.unrealized_pl_pct != null
              ? `${p.unrealized_pl_pct >= 0 ? "+" : ""}${fmt(p.unrealized_pl_pct)}%`
              : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Peso cartera</p>
          <p className="font-medium">
            {p.weight_pct != null ? `${fmt(p.weight_pct, 1)}%` : "—"}
          </p>
        </div>
        {p.country && (
          <div>
            <p className="text-xs text-muted-foreground">País</p>
            <p className="font-medium">{p.country}</p>
          </div>
        )}
      </div>

      {/* Account breakdown */}
      {detail.accounts.length > 1 && (
        <div>
          <h4 className="mb-2 text-sm font-semibold">Distribución por cuenta</h4>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {detail.accounts.map((a) => {
              const display = getAccountValueDisplay(a.value_eur, a.cost_eur);
              return (
                <div key={a.account_id} className="rounded-md border p-2">
                  <Badge variant="outline" className="text-[10px]">
                    {a.broker}
                  </Badge>
                  <p className="mt-1 text-sm">{fmt(a.quantity)} uds</p>
                  <p className="text-xs text-muted-foreground fv-sensitive">
                    {display
                      ? `${fmt(display.amount)} €${display.kind === "cost" ? " (coste)" : ""}`
                      : "—"}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {detail.dividends_by_year.length > 0 && (
        <div>
          <h4 className="mb-2 text-sm font-semibold">Dividendos cobrados</h4>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Año</TableHead>
                <TableHead className="text-right">Bruto (EUR)</TableHead>
                <TableHead className="text-right">Neto (EUR)</TableHead>
                <TableHead className="text-right">Pagos</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.dividends_by_year.map((d) => (
                <TableRow key={d.year}>
                  <TableCell className="font-medium">{d.year}</TableCell>
                  <TableCell className="text-right tabular-nums fv-sensitive">
                    {fmt(d.gross_eur)} €
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium text-blue-700 fv-sensitive">
                    {fmt(d.net_eur)} €
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {d.count}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {(() => {
        const bars = ohlcByIsin.get(`${detail.isin}:${chartScope}`) ?? [];
        if (!detail.ticker || bars.length === 0) return null;
        return (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h4 className="text-sm font-semibold">
                Precio y operaciones{" "}
                <span className="font-normal text-muted-foreground">
                  ▲ compra · ▼ venta · ● dividendo
                </span>
              </h4>
              <div className="flex items-center gap-0.5">
                {CHART_SCOPES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setChartScope(s)}
                    className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                      chartScope === s
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <PriceChart
              data={bars}
              markers={alignMarkersToBars(
                executionMarkers([
                  ...detail.transactions,
                  ...(detail.dividend_events ?? []).map((d) => ({
                    type: "DIVIDEND",
                    date: d.date,
                  })),
                ]),
                bars,
              )}
              height={360}
            />
          </div>
        );
      })()}

      <div>
        <h4 className="mb-2 text-sm font-semibold">
          Historial ({detail.transactions.length} operaciones)
        </h4>
        {detail.transactions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No hay operaciones registradas
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tipo</TableHead>
                <TableHead>Fecha</TableHead>
                <TableHead className="text-right">Cantidad</TableHead>
                <TableHead className="text-right">Precio</TableHead>
                <TableHead className="text-right">Neto (EUR)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.transactions.map((tx) => (
                <TableRow key={tx.id}>
                  <TableCell>
                    <Badge
                      className={TX_COLORS[tx.type] || "bg-gray-100 text-gray-700"}
                    >
                      {TX_LABELS[tx.type] || tx.type}
                    </Badge>
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {new Date(tx.date).toLocaleDateString("es-ES")}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmt(tx.quantity)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmt(tx.price)} {tx.currency}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium fv-sensitive">
                    {fmt(tx.net_eur)} €
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
