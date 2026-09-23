"use client";

import { Fragment } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  EyeOff,
  Pause,
  Play,
  Target,
  Trash2,
} from "lucide-react";

import { fmt, fmtDateTime } from "@/lib/format";
import type { WatchlistRow } from "@/lib/optionsWatchlistRows";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingDots } from "@/components/loading-dots";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TabsContent } from "@/components/ui/tabs";
import { OpcionesTab } from "@/components/instrument/OpcionesTab";

import { MEFF_TICKERS } from "./meffTickers";
import type { Alert, Position, Snapshot, WatchlistItem } from "./types";

/**
 * The Watchlist tab: manual add + MEFF quick-add, then the unified list
 * (mobile cards / desktop table) with the inline OpcionesTab expansion.
 *
 * Every binding the body reads from the page arrives as an explicit prop —
 * the state stays owned by OptionsPage because the Monitor tab and the stats
 * cards read the same alerts/watchlist, and Radix unmounts inactive
 * `TabsContent`, so owning any of it here would drop it on every tab switch.
 * Markup and classes are unchanged from page.tsx.
 */

/** A watchlist row enriched with the latest snapshot and its unread alerts. */
export type EnrichedWatchlistRow = WatchlistRow<Position, WatchlistItem> & {
  snap: Snapshot | undefined;
  rowAlerts: Alert[];
};

export interface WatchlistTabProps {
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  rows: EnrichedWatchlistRow[];
  watchlistTickers: ReadonlySet<string>;
  errorPositions: string | null;
  /** Held tickers with no options chain — explained in a note under the list. */
  noOptPositions: Position[];
  newTicker: string;
  onNewTickerChange: (value: string) => void;
  onAddTicker: () => void;
  onAddMeffTicker: (ticker: string, name: string) => void;
  expandedTicker: string | null;
  onExpandedTickerChange: (ticker: string | null) => void;
  /** Zonas (técnico) lens: ticker → zonas item id, and tickers mid-toggle. */
  zonasMap: ReadonlyMap<string, number>;
  zonasBusy: ReadonlySet<string>;
  onToggleZonasLens: (ticker: string, name: string) => void;
  onToggleItem: (id: number) => void;
  onHidePosition: (ticker: string) => void;
  onRemoveTicker: (id: number, ticker?: string) => void;
}

// Sentiment/IV-HV badge for a position row — sourced from the already-loaded
// snapshot (latestByTicker), no extra fetch. Mirrors OpcionesTab.tsx's ivHvBadge
// threshold (diff > 5 → cara, < -5 → barata).
function sentimentLabel(s?: Snapshot) {
  const sentiment = s?.market_sentiment;
  if (!sentiment) return { label: "—", className: "text-muted-foreground" };
  const lower = sentiment.toLowerCase();
  const className =
    lower === "alcista"
      ? "text-emerald-600"
      : lower === "bajista"
        ? "text-red-600"
        : "text-amber-500";
  return { label: sentiment, className };
}

function ivHvLabel(s?: Snapshot): { label: string; variant: "destructive" | "secondary" | "outline" } {
  if (!s?.avg_call_iv || !s?.historical_volatility) return { label: "—", variant: "outline" };
  const diff = Number(s.avg_call_iv) - Number(s.historical_volatility);
  if (diff > 5) return { label: "IV cara", variant: "destructive" };
  if (diff < -5) return { label: "IV barata", variant: "secondary" };
  return { label: "IV normal", variant: "outline" };
}

export function WatchlistTab({
  loading,
  error,
  onRetry,
  rows,
  watchlistTickers,
  errorPositions,
  noOptPositions,
  newTicker,
  onNewTickerChange,
  onAddTicker,
  onAddMeffTicker,
  expandedTicker,
  onExpandedTickerChange,
  zonasMap,
  zonasBusy,
  onToggleZonasLens,
  onToggleItem,
  onHidePosition,
  onRemoveTicker,
}: WatchlistTabProps) {
  const heldCount = rows.filter((r) => r.lots.length > 0).length;

  // Held tickers auto-sync back into the watchlist on the next load, so plain
  // removal doesn't stick for them — "Ocultar" (which also persists the
  // exclusion) is their only real off-switch. Non-held tickers have no such
  // problem, so they keep a straight delete.
  const renderRemoveButton = (w: WatchlistItem, held: boolean) =>
    held ? (
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        title="Ocultar del monitor de opciones"
        onClick={() => onHidePosition(w.ticker)}
      >
        <EyeOff className="mr-1 h-4 w-4" />
        Ocultar
      </Button>
    ) : (
      <Button
        variant="ghost"
        size="sm"
        className="text-destructive"
        title="Eliminar de la watchlist"
        onClick={() => onRemoveTicker(w.id, w.ticker)}
      >
        <Trash2 className="mr-1 h-4 w-4" />
        Eliminar
      </Button>
    );

  const renderZonasChip = (w: WatchlistItem) => {
    const active = zonasMap.has(w.ticker);
    const busy = zonasBusy.has(w.ticker);
    return (
      <button
        title={
          active
            ? "Quitar del análisis técnico (Zonas Clave)"
            : "Analizar en Zonas Clave (soportes/resistencias)"
        }
        disabled={busy}
        onClick={() => onToggleZonasLens(w.ticker, w.name)}
        className={[
          "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
          busy ? "opacity-50 cursor-wait" : "cursor-pointer",
          active
            ? "border-transparent bg-primary/10 text-primary"
            : "border-border bg-background text-muted-foreground hover:bg-primary hover:text-primary-foreground hover:border-primary",
        ].join(" ")}
      >
        <Target className="h-3 w-3" />
        Técnico
        {active && <CheckCircle2 className="h-3 w-3" />}
      </button>
    );
  };

  return (
    <TabsContent value="watchlist" className="space-y-4">
      {loading ? (
        <div className="flex min-h-[30vh] items-center justify-center">
          <LoadingDots text="Cargando watchlist" />
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-10 text-center space-y-3">
            <AlertCircle className="mx-auto h-8 w-8 text-destructive" />
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>
              Reintentar
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>
              Watchlist ({rows.length})
              {heldCount > 0 && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  {heldCount} en cartera
                </span>
              )}
            </CardTitle>
            <CardDescription>
              Tus posiciones se añaden solas. Pulsa en una fila para ver su
              gráfica y su cadena de opciones.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 p-0 sm:p-6 sm:pt-0">
            <div className="space-y-4 p-4 pb-0 sm:p-0">
              <div className="flex gap-2">
                <input
                  className="flex h-9 w-full max-w-xs rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  placeholder="Ticker (ej. AAPL, ACX.MC)"
                  value={newTicker}
                  onChange={(e) => onNewTickerChange(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && onAddTicker()}
                />
                <Button size="sm" onClick={onAddTicker}>
                  Añadir
                </Button>
              </div>

              {/* ── Spanish stocks quick-add (MEFF) ── */}
              <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Acciones Españolas — MEFF
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {MEFF_TICKERS.map(({ ticker, name }) => {
                    const already = watchlistTickers.has(ticker);
                    return (
                      <button
                        key={ticker}
                        title={name}
                        disabled={already}
                        onClick={() => onAddMeffTicker(ticker, name)}
                        className={[
                          "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
                          already
                            ? "border-transparent bg-primary/10 text-primary cursor-default"
                            : "border-border bg-background text-foreground hover:bg-primary hover:text-primary-foreground hover:border-primary cursor-pointer",
                        ].join(" ")}
                      >
                        {already && <CheckCircle2 className="h-3 w-3" />}
                        {ticker.replace(".MC", "")}
                      </button>
                    );
                  })}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Pasa el cursor para ver el nombre. Los marcados ya están en tu watchlist.
                </p>
              </div>

              {errorPositions && (
                <p className="text-xs text-muted-foreground">
                  {errorPositions} La watchlist funciona igual, pero no se puede
                  marcar qué tickers tienes en cartera.
                </p>
              )}
            </div>

            {/* Mobile */}
            <div className="divide-y border-t sm:hidden">
              {rows.length === 0 ? (
                <p className="p-4 text-center text-sm text-muted-foreground">
                  Sin tickers en la watchlist
                </p>
              ) : (
                rows.map(({ item: w, snap, lots, rowAlerts }) => {
                  const sentiment = sentimentLabel(snap);
                  const ivHv = ivHvLabel(snap);
                  const held = lots.length > 0;
                  const isExpanded = expandedTicker === w.ticker;
                  return (
                    <div key={w.id}>
                      <div
                        className="flex cursor-pointer flex-col gap-2 p-3 hover:bg-muted/50"
                        onClick={() =>
                          onExpandedTickerChange(isExpanded ? null : w.ticker)
                        }
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-2">
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                            )}
                            <span className="font-medium">{w.ticker}</span>
                            {held && (
                              <Badge variant="outline" className="px-1 py-0 text-[10px]">
                                Cartera
                              </Badge>
                            )}
                            {!w.enabled && (
                              <Badge variant="secondary" className="px-1 py-0 text-[10px]">
                                Pausado
                              </Badge>
                            )}
                            {rowAlerts.length > 0 && (
                              <Badge variant="destructive" className="px-1 py-0 text-[10px]">
                                {rowAlerts.length}
                              </Badge>
                            )}
                          </div>
                          {/* Actions live in the collapsed header, not the
                              expansion: expanding mounts OpcionesTab, which
                              fetches expirations + chain. Removing a row
                              shouldn't cost a network round-trip. */}
                          <div
                            className="flex shrink-0 items-center gap-0.5"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {renderZonasChip(w)}
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0"
                              title={w.enabled ? "Pausar" : "Activar"}
                              onClick={() => onToggleItem(w.id)}
                            >
                              {w.enabled ? (
                                <Pause className="h-4 w-4 text-muted-foreground" />
                              ) : (
                                <Play className="h-4 w-4 text-muted-foreground" />
                              )}
                            </Button>
                            {held ? (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 w-7 p-0"
                                title="Ocultar del monitor de opciones"
                                onClick={() => onHidePosition(w.ticker)}
                              >
                                <EyeOff className="h-4 w-4 text-muted-foreground" />
                              </Button>
                            ) : (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 w-7 p-0"
                                title="Eliminar de la watchlist"
                                onClick={() => onRemoveTicker(w.id, w.ticker)}
                              >
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-3 pl-6 text-xs text-muted-foreground">
                          <span>
                            Sentimiento{" "}
                            <strong className={sentiment.className}>{sentiment.label}</strong>
                          </span>
                          <span>
                            P/C{" "}
                            <strong className="text-foreground">
                              {snap?.put_call_ratio_volume != null
                                ? fmt(snap.put_call_ratio_volume)
                                : "—"}
                            </strong>
                          </span>
                          <span className="flex items-center gap-1">
                            IV/HV{" "}
                            <Badge variant={ivHv.variant} className="text-[10px]">
                              {ivHv.label}
                            </Badge>
                          </span>
                        </div>
                      </div>
                      {isExpanded && (
                        <div className="space-y-3 border-t bg-muted/30 p-3 pl-9 text-sm">
                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                            <span>{w.name || "—"}</span>
                            {lots.map((p) => (
                              <span key={`${p.isin}-${p.broker}`}>
                                {p.broker} · {fmt(p.quantity, 2)} uds
                                {p.avg_cost_eur != null && (
                                  <span className="fv-sensitive">
                                    {" "}
                                    · coste medio {fmt(p.avg_cost_eur, 2)} €
                                  </span>
                                )}
                              </span>
                            ))}
                          </div>
                          {rowAlerts.length > 0 && (
                            <div className="space-y-1.5">
                              {rowAlerts.map((a) => (
                                <div key={a.id} className="rounded-md border bg-background p-2 text-xs">
                                  <div className="flex items-center gap-2">
                                    <Badge variant="outline" className="text-[10px]">
                                      {a.alert_type}
                                    </Badge>
                                    <span className="text-muted-foreground">
                                      {fmtDateTime(a.timestamp)}
                                    </span>
                                  </div>
                                  <p className="mt-1 text-foreground">{a.message}</p>
                                </div>
                              ))}
                            </div>
                          )}
                          <OpcionesTab symbol={w.ticker} />
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Desktop */}
            <Table className="hidden sm:table">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Ticker</TableHead>
                  <TableHead>Nombre</TableHead>
                  <TableHead className="text-right">Sentimiento</TableHead>
                  <TableHead className="text-right">P/C Ratio</TableHead>
                  <TableHead className="text-right">IV vs HV</TableHead>
                  <TableHead>Técnico</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center text-muted-foreground">
                      Sin tickers en la watchlist
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map(({ item: w, snap, lots, rowAlerts }) => {
                    const sentiment = sentimentLabel(snap);
                    const ivHv = ivHvLabel(snap);
                    const held = lots.length > 0;
                    const isExpanded = expandedTicker === w.ticker;
                    return (
                      <Fragment key={w.id}>
                        <TableRow
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() =>
                            onExpandedTickerChange(isExpanded ? null : w.ticker)
                          }
                        >
                          <TableCell className="w-8 pr-0">
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="h-4 w-4 text-muted-foreground" />
                            )}
                          </TableCell>
                          <TableCell className="font-medium">
                            <span className="flex items-center gap-2">
                              {w.ticker}
                              {held && (
                                <Badge variant="outline" className="px-1 py-0 text-[10px]">
                                  Cartera
                                </Badge>
                              )}
                              {!w.enabled && (
                                <Badge variant="secondary" className="px-1 py-0 text-[10px]">
                                  Pausado
                                </Badge>
                              )}
                              {rowAlerts.length > 0 && (
                                <Badge variant="destructive" className="px-1 py-0 text-[10px]">
                                  {rowAlerts.length}
                                </Badge>
                              )}
                            </span>
                          </TableCell>
                          <TableCell className="text-muted-foreground">{w.name || "—"}</TableCell>
                          <TableCell className={`text-right font-medium ${sentiment.className}`}>
                            {sentiment.label}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {snap?.put_call_ratio_volume != null
                              ? fmt(snap.put_call_ratio_volume)
                              : "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <Badge variant={ivHv.variant} className="text-[10px]">
                              {ivHv.label}
                            </Badge>
                          </TableCell>
                          <TableCell onClick={(e) => e.stopPropagation()}>
                            {renderZonasChip(w)}
                          </TableCell>
                          <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => onToggleItem(w.id)}
                            >
                              {w.enabled ? "Pausar" : "Activar"}
                            </Button>
                            {renderRemoveButton(w, held)}
                          </TableCell>
                        </TableRow>
                        {isExpanded && (
                          <TableRow>
                            <TableCell colSpan={8} className="bg-muted/30 p-4">
                              <div className="space-y-3">
                                {lots.length > 0 && (
                                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                                    {lots.map((p) => (
                                      <span key={`${p.isin}-${p.broker}`}>
                                        {p.broker} · {fmt(p.quantity, 2)} uds
                                        {p.avg_cost_eur != null && (
                                          <span className="fv-sensitive">
                                            {" "}
                                            · coste medio {fmt(p.avg_cost_eur, 2)} €
                                          </span>
                                        )}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                <OpcionesTab symbol={w.ticker} />
                              </div>
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
      {noOptPositions.length > 0 && (
        <p className="px-1 text-sm text-muted-foreground">
          Los siguientes tickers de tu cartera no aparecen porque no tienen
          opciones disponibles en los mercados:{" "}
          <span className="font-medium">
            {noOptPositions.map((p) => p.ticker || p.isin).join(", ")}
          </span>
          .
        </p>
      )}
    </TabsContent>
  );
}
