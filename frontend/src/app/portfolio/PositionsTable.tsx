"use client";

import { Fragment } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Target, Loader2, AlertTriangle } from "lucide-react";

import { fmt } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { PositionDetailPanel } from "./PositionDetailPanel";
import type { PositionsListProps } from "./types";

// Desktop rendering of the positions list (hidden below `sm`); the mobile
// stacked cards live in PositionsMobileList.tsx and take the same props.
export function PositionsTable({
  positions,
  pricesLoaded,
  expandedIsin,
  details,
  loadingDetail,
  onExpand,
  geoByTicker,
  zcWatchlist,
  zcAdding,
  onAddToZonas,
  ohlcByIsin,
  chartScope,
  setChartScope,
}: PositionsListProps) {
  const router = useRouter();

  return (
    <Table className="hidden sm:table">
      <TableHeader>
        <TableRow>
          <TableHead className="w-8" />
          <TableHead>Activo</TableHead>
          <TableHead className="text-right">Cantidad</TableHead>
          <TableHead className="text-right">Coste medio</TableHead>
          <TableHead className="text-right">Precio actual</TableHead>
          <TableHead className="text-right">Valor</TableHead>
          <TableHead className="text-right">P&L</TableHead>
          <TableHead className="text-right">Peso</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {positions.map((p) => {
          const key = `${p.isin}-${p.broker}`;
          const isExpanded = expandedIsin === p.isin;
          const detail = details.get(p.isin);
          const isLoadingThis = loadingDetail === p.isin;
          const plPositive =
            p.unrealized_pl_eur != null && p.unrealized_pl_eur >= 0;
          const plClass = plPositive
            ? "text-emerald-600"
            : "text-red-600";
          return (
            <Fragment key={key}>
              <TableRow
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => onExpand(p.isin)}
              >
                <TableCell className="w-8 pr-0">
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    <div className="flex flex-col">
                      <span className="font-medium">
                        {p.ticker || p.isin}
                      </span>
                      <span className="text-xs text-muted-foreground truncate max-w-50">
                        {p.name}
                      </span>
                    </div>
                    {(() => {
                      const signal = geoByTicker.get(
                        (p.ticker ?? p.isin).toUpperCase(),
                      );
                      if (!signal) return null;
                      return (
                        <button
                          type="button"
                          title={`Señal geo activa: ${signal.headline} (importancia ${signal.importance})`}
                          onClick={(e) => {
                            e.stopPropagation();
                            router.push("/geo-intel");
                          }}
                          className="shrink-0 rounded-full p-1 text-amber-600 hover:bg-amber-50"
                        >
                          <AlertTriangle className="h-3.5 w-3.5" />
                        </button>
                      );
                    })()}
                  </div>
                  <Badge variant="outline" className="text-[10px] mt-1">
                    {p.broker}
                  </Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {fmt(p.quantity, 2)}
                </TableCell>
                <TableCell className="text-right tabular-nums fv-sensitive">
                  {p.avg_cost_eur != null ? `${fmt(p.avg_cost_eur, 2)} €` : "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {!pricesLoaded ? (
                    <span className="inline-flex gap-0.5 text-muted-foreground">
                      <span className="animate-pulse">·</span>
                      <span className="animate-pulse [animation-delay:150ms]">
                        ·
                      </span>
                      <span className="animate-pulse [animation-delay:300ms]">
                        ·
                      </span>
                    </span>
                  ) : p.current_price_eur != null ? (
                    `${fmt(p.current_price_eur, 2)} €`
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums font-medium fv-sensitive">
                  {!pricesLoaded ? (
                    <span className="inline-flex gap-0.5 text-muted-foreground">
                      <span className="animate-pulse">·</span>
                      <span className="animate-pulse [animation-delay:150ms]">
                        ·
                      </span>
                      <span className="animate-pulse [animation-delay:300ms]">
                        ·
                      </span>
                    </span>
                  ) : p.market_value_eur != null ? (
                    `${fmt(p.market_value_eur)} €`
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell
                  className={`text-right tabular-nums ${pricesLoaded ? plClass : ""}`}
                >
                  {!pricesLoaded ? (
                    <span className="inline-flex gap-0.5 text-muted-foreground">
                      <span className="animate-pulse">·</span>
                      <span className="animate-pulse [animation-delay:150ms]">
                        ·
                      </span>
                      <span className="animate-pulse [animation-delay:300ms]">
                        ·
                      </span>
                    </span>
                  ) : p.unrealized_pl_eur != null ? (
                    <div>
                      <div className="fv-sensitive">
                        {plPositive ? "+" : ""}
                        {fmt(p.unrealized_pl_eur)} €
                      </div>
                      <div className="text-xs">
                        {plPositive ? "+" : ""}
                        {fmt(p.unrealized_pl_pct)}%
                      </div>
                    </div>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {!pricesLoaded ? (
                    <span className="inline-flex gap-0.5 text-muted-foreground">
                      <span className="animate-pulse">·</span>
                      <span className="animate-pulse [animation-delay:150ms]">
                        ·
                      </span>
                      <span className="animate-pulse [animation-delay:300ms]">
                        ·
                      </span>
                    </span>
                  ) : p.weight_pct != null ? (
                    `${fmt(p.weight_pct, 1)}%`
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell className="text-center">
                  {zcWatchlist.has((p.ticker ?? p.isin).toUpperCase()) ? (
                    <Badge variant="secondary" className="px-1.5 text-[10px]">
                      <Target className="h-3 w-3" />
                    </Badge>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      title="Añadir a Zonas Clave"
                      disabled={zcAdding.has(p.ticker ?? p.isin)}
                      onClick={async (e) => {
                        e.stopPropagation();
                        await onAddToZonas(p);
                      }}
                    >
                      {zcAdding.has(p.ticker ?? p.isin) ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Target className="h-4 w-4 text-muted-foreground" />
                      )}
                    </Button>
                  )}
                </TableCell>
              </TableRow>

              {/* Expanded detail */}
              {isExpanded && (
                <TableRow key={`${key}-detail`}>
                  <TableCell colSpan={9} className="bg-muted/30 p-4">
                    <PositionDetailPanel
                      p={p}
                      detail={detail}
                      isLoadingThis={isLoadingThis}
                      plClass={plClass}
                      ohlcByIsin={ohlcByIsin}
                      chartScope={chartScope}
                      setChartScope={setChartScope}
                    />
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          );
        })}
      </TableBody>
    </Table>
  );
}
