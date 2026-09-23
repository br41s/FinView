"use client";

import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Target, Loader2, AlertTriangle } from "lucide-react";

import { fmt } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PositionDetailPanel } from "./PositionDetailPanel";
import type { PositionsListProps } from "./types";

// Mobile rendering of the positions list (stacked cards instead of a
// horizontally-scrolling table, hidden from `sm` up); same props as
// PositionsTable.tsx.
export function PositionsMobileList({
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
    <div className="divide-y sm:hidden">
      {positions.map((p) => {
        const key = `${p.isin}-${p.broker}`;
        const isExpanded = expandedIsin === p.isin;
        const detail = details.get(p.isin);
        const isLoadingThis = loadingDetail === p.isin;
        const plPositive =
          p.unrealized_pl_eur != null && p.unrealized_pl_eur >= 0;
        const plClass = plPositive ? "text-emerald-600" : "text-red-600";
        const signal = geoByTicker.get((p.ticker ?? p.isin).toUpperCase());
        const zcTicker = p.ticker ?? p.isin;

        return (
          <div key={key} className="p-3">
            <div
              className="flex cursor-pointer items-start justify-between gap-2"
              onClick={() => onExpand(p.isin)}
            >
              <div className="flex min-w-0 items-start gap-1.5">
                {isExpanded ? (
                  <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                )}
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium">{p.ticker || p.isin}</span>
                    {signal && (
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
                    )}
                  </div>
                  <p className="max-w-[180px] truncate text-xs text-muted-foreground">
                    {p.name}
                  </p>
                  <Badge variant="outline" className="mt-1 text-[10px]">
                    {p.broker}
                  </Badge>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-medium tabular-nums fv-sensitive">
                  {!pricesLoaded ? (
                    <span className="inline-flex gap-0.5 text-muted-foreground">
                      <span className="animate-pulse">·</span>
                      <span className="animate-pulse [animation-delay:150ms]">·</span>
                      <span className="animate-pulse [animation-delay:300ms]">·</span>
                    </span>
                  ) : p.market_value_eur != null ? (
                    `${fmt(p.market_value_eur)} €`
                  ) : (
                    "—"
                  )}
                </p>
                <p
                  className={`text-xs tabular-nums fv-sensitive ${pricesLoaded ? plClass : "text-muted-foreground"}`}
                >
                  {pricesLoaded && p.unrealized_pl_eur != null
                    ? `${plPositive ? "+" : ""}${fmt(p.unrealized_pl_eur)} € (${plPositive ? "+" : ""}${fmt(p.unrealized_pl_pct)}%)`
                    : !pricesLoaded
                      ? ""
                      : "—"}
                </p>
              </div>
            </div>

            <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {fmt(p.quantity, 2)} uds
                {p.avg_cost_eur != null && (
                  <span className="fv-sensitive"> · coste {fmt(p.avg_cost_eur, 2)} €</span>
                )}
              </span>
              <div className="flex items-center gap-2">
                <span>Peso {p.weight_pct != null ? `${fmt(p.weight_pct, 1)}%` : "—"}</span>
                {zcWatchlist.has(zcTicker.toUpperCase()) ? (
                  <Badge variant="secondary" className="px-1.5 text-[10px]">
                    <Target className="h-3 w-3" />
                  </Badge>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0"
                    title="Añadir a Zonas Clave"
                    disabled={zcAdding.has(zcTicker)}
                    onClick={async (e) => {
                      e.stopPropagation();
                      await onAddToZonas(p);
                    }}
                  >
                    {zcAdding.has(zcTicker) ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Target className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
                  </Button>
                )}
              </div>
            </div>

            {isExpanded && (
              <div className="mt-3 border-t pt-3">
                <PositionDetailPanel
                  p={p}
                  detail={detail}
                  isLoadingThis={isLoadingThis}
                  plClass={plClass}
                  ohlcByIsin={ohlcByIsin}
                  chartScope={chartScope}
                  setChartScope={setChartScope}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
