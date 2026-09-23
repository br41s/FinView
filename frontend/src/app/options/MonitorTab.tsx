"use client";

import Link from "next/link";
import { Fragment } from "react";
import { Activity, AlertCircle, Bell, Globe, Target, Zap } from "lucide-react";

import type { TechnicalSignal } from "@/lib/api";
import { fmt, fmtDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { LoadingDots } from "@/components/loading-dots";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TabsContent } from "@/components/ui/tabs";
import { OpcionesTab } from "@/components/instrument/OpcionesTab";

import { AlignmentTag, BreakProbability, DirBadge, severityColor } from "./badges";
import type { Alert, Unusual } from "./types";

/**
 * The Monitor tab: one filter row over three panels — Alertas (options cycle
 * alerts), Smart Money (unusual activity) and Técnico (zone-break signals from
 * Zonas Clave). Each panel keeps its mobile card list and desktop table.
 *
 * Everything it reads arrives as an explicit prop; the alerts/unusual state
 * stays on OptionsPage because the watchlist rows and the stats cards read it
 * too, and Radix unmounts inactive `TabsContent`. Markup and classes are
 * unchanged from page.tsx.
 */

export type MonitorFilter = "alerts" | "unusual" | "technical";

export interface MonitorTabProps {
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  filter: MonitorFilter;
  onFilterChange: (filter: MonitorFilter) => void;
  alerts: Alert[];
  unreadCount: number;
  unusual: Unusual[];
  techSignals: TechnicalSignal[];
  expandedTicker: string | null;
  onExpandedTickerChange: (ticker: string | null) => void;
  /** Tickers with an active geo signal — gates the per-alert "Ideas" link. */
  geoTickers: ReadonlySet<string>;
  onAckAlert: (id: number) => void;
  onAckAll: () => void;
}

// Per-alert jump-offs. An options alert says "something moved here" — acting on
// it means seeing the chain (inline, this page) and the technical picture
// (Zonas Clave). Ideas only shows up when that ticker actually has an active
// geo signal: a link to an empty page is worse than no link. Links are
// navigation, not content — no thesis or fundamentals render here.
function TickerLinks({
  ticker,
  expanded,
  geoTickers,
  onExpandedTickerChange,
}: {
  ticker: string;
  expanded: boolean;
  geoTickers: ReadonlySet<string>;
  onExpandedTickerChange: (ticker: string | null) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      <button
        onClick={() => onExpandedTickerChange(expanded ? null : ticker)}
        title={expanded ? "Ocultar la cadena de opciones" : "Ver la cadena de opciones aquí"}
        className={[
          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors cursor-pointer",
          expanded
            ? "border-transparent bg-primary/10 text-primary"
            : "border-border bg-background text-muted-foreground hover:bg-primary hover:text-primary-foreground hover:border-primary",
        ].join(" ")}
      >
        <Activity className="h-3 w-3" />
        Opciones
      </button>
      <Link
        href={`/zonas-clave?ticker=${encodeURIComponent(ticker)}`}
        title="Ver soportes y resistencias en Zonas Clave"
        className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary hover:bg-primary hover:text-primary-foreground"
      >
        <Target className="h-3 w-3" />
        Técnico
      </Link>
      {geoTickers.has(ticker) && (
        <Link
          href={`/geo-intel?ticker=${encodeURIComponent(ticker)}`}
          title="Este ticker tiene una señal activa en Ideas"
          className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary hover:bg-primary hover:text-primary-foreground"
        >
          <Globe className="h-3 w-3" />
          Ideas
        </Link>
      )}
    </div>
  );
}

interface PanelExpansionProps {
  expandedTicker: string | null;
  onExpandedTickerChange: (ticker: string | null) => void;
  geoTickers: ReadonlySet<string>;
}

export function AlertsPanel({
  alerts,
  onAckAlert,
  expandedTicker,
  onExpandedTickerChange,
  geoTickers,
}: PanelExpansionProps & { alerts: Alert[]; onAckAlert: (id: number) => void }) {
  return (
    <Card>
      <CardContent className="p-0">
        {alerts.length === 0 ? (
          <p className="p-4 text-center text-sm text-muted-foreground">Sin alertas aún</p>
        ) : (
          <>
            {/* Mobile */}
            <div className="divide-y sm:hidden">
              {alerts.map((a) => {
                const tickerUp = a.ticker.toUpperCase();
                const isAlertExpanded = expandedTicker === tickerUp;
                return (
                  <div key={a.id} className={`flex flex-col gap-1.5 p-3 ${a.acknowledged ? "opacity-50" : ""}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{a.ticker}</span>
                      <Badge variant="outline" className="text-xs">{a.alert_type}</Badge>
                      <Badge variant={severityColor(a.severity) as "destructive" | "secondary" | "outline"} className="text-xs">{a.severity}</Badge>
                      <AlignmentTag alignment={a.regime_alignment} />
                      <span className="ml-auto text-xs text-muted-foreground">
                        {new Date(a.timestamp).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground">{a.message}</p>
                    <div className="flex items-end justify-between gap-2">
                      <TickerLinks
                        ticker={tickerUp}
                        expanded={isAlertExpanded}
                        geoTickers={geoTickers}
                        onExpandedTickerChange={onExpandedTickerChange}
                      />
                      {!a.acknowledged && (
                        <Button variant="ghost" size="sm" className="h-7 shrink-0 text-xs" onClick={() => onAckAlert(a.id)}>Ack</Button>
                      )}
                    </div>
                    {isAlertExpanded && (
                      <div className="mt-2 border-t pt-2">
                        <OpcionesTab symbol={tickerUp} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {/* Desktop */}
            <Table className="hidden sm:table">
              <TableHeader>
                <TableRow>
                  <TableHead>Hora</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Mensaje</TableHead>
                  <TableHead>Severidad</TableHead>
                  <TableHead>Ver en</TableHead>
                  <TableHead className="text-right">Acción</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.map((a) => {
                  const tickerUp = a.ticker.toUpperCase();
                  const isAlertExpanded = expandedTicker === tickerUp;
                  return (
                    <Fragment key={a.id}>
                      <TableRow className={a.acknowledged ? "opacity-50" : ""}>
                        <TableCell className="text-xs">{fmtDateTime(a.timestamp)}</TableCell>
                        <TableCell className="font-medium">{a.ticker}</TableCell>
                        <TableCell><Badge variant="outline">{a.alert_type}</Badge></TableCell>
                        <TableCell>{a.message}</TableCell>
                        <TableCell><div className="flex items-center gap-1"><Badge variant={severityColor(a.severity) as "destructive" | "secondary" | "outline"}>{a.severity}</Badge><AlignmentTag alignment={a.regime_alignment} /></div></TableCell>
                        <TableCell>
                          <TickerLinks
                            ticker={tickerUp}
                            expanded={isAlertExpanded}
                            geoTickers={geoTickers}
                            onExpandedTickerChange={onExpandedTickerChange}
                          />
                        </TableCell>
                        <TableCell className="text-right">
                          {!a.acknowledged && <Button variant="ghost" size="sm" onClick={() => onAckAlert(a.id)}>Ack</Button>}
                        </TableCell>
                      </TableRow>
                      {isAlertExpanded && (
                        <TableRow>
                          <TableCell colSpan={7} className="bg-muted/30 p-4">
                            <OpcionesTab symbol={tickerUp} />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function UnusualPanel({ unusual }: { unusual: Unusual[] }) {
  return (
    <Card>
      <CardContent className="p-0">
        {unusual.length === 0 ? (
          <p className="p-4 text-center text-sm text-muted-foreground">Sin actividad inusual detectada</p>
        ) : (
          <>
            {/* Mobile */}
            <div className="divide-y sm:hidden">
              {unusual.map((u) => (
                <div key={u.id} className="flex flex-col gap-1 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{u.ticker}</span>
                    <Badge variant={u.option_type === "CALL" ? "default" : "secondary"} className="text-xs">{u.option_type}</Badge>
                    <span className="text-sm">${fmt(u.strike)}</span>
                    <span className="text-xs text-muted-foreground">{u.expiration}</span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {new Date(u.timestamp).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span>Vol <strong className="text-foreground">{u.volume.toLocaleString()}</strong></span>
                    <span>OI <strong className="text-foreground">{u.open_interest.toLocaleString()}</strong></span>
                    <span>Vol/OI <strong className="text-amber-600">{fmt(u.vol_oi_ratio, 1)}x</strong></span>
                    <span>IV <strong className="text-foreground">{u.implied_volatility ? `${fmt(Number(u.implied_volatility) * 100, 1)}%` : "—"}</strong></span>
                  </div>
                </div>
              ))}
            </div>
            {/* Desktop */}
            <Table className="hidden sm:table">
              <TableHeader>
                <TableRow>
                  <TableHead>Hora</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Strike</TableHead>
                  <TableHead>Exp</TableHead>
                  <TableHead>Volumen</TableHead>
                  <TableHead>OI</TableHead>
                  <TableHead>Vol/OI</TableHead>
                  <TableHead>IV</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {unusual.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="text-xs">{fmtDateTime(u.timestamp)}</TableCell>
                    <TableCell className="font-medium">{u.ticker}</TableCell>
                    <TableCell><Badge variant={u.option_type === "CALL" ? "default" : "secondary"}>{u.option_type}</Badge></TableCell>
                    <TableCell>${fmt(u.strike)}</TableCell>
                    <TableCell>{u.expiration}</TableCell>
                    <TableCell>{u.volume.toLocaleString()}</TableCell>
                    <TableCell>{u.open_interest.toLocaleString()}</TableCell>
                    <TableCell className="font-medium text-amber-600">{fmt(u.vol_oi_ratio, 1)}x</TableCell>
                    <TableCell>{u.implied_volatility ? `${fmt(Number(u.implied_volatility) * 100, 1)}%` : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function TechnicalSignalsPanel({
  signals,
  expandedTicker,
  onExpandedTickerChange,
  geoTickers,
}: PanelExpansionProps & { signals: TechnicalSignal[] }) {
  return (
    <Card>
      <CardContent className="p-0">
        {signals.length === 0 ? (
          <p className="p-4 text-center text-sm text-muted-foreground">
            Sin señales técnicas. Se emiten cuando el precio de un ticker de
            Zonas Clave se acerca a menos del 2% de una zona.
          </p>
        ) : (
          <>
            {/* Mobile */}
            <div className="divide-y sm:hidden">
              {signals.map((s) => {
                const isExpanded = expandedTicker === s.ticker;
                return (
                  <div key={s.id} className="flex flex-col gap-1.5 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{s.ticker}</span>
                      <DirBadge direction={s.direction} />
                      <BreakProbability signal={s} />
                      <span className="ml-auto text-xs text-muted-foreground">
                        {new Date(s.created_at).toLocaleTimeString("es-ES", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      A {(s.distance_pct * 100).toFixed(2)}% de la zona{" "}
                      <strong className="text-foreground">{fmt(s.zone_level)}</strong>{" "}
                      ({s.approach === "from_below" ? "por debajo" : "por encima"})
                      {s.zone_touches != null && ` · ${s.zone_touches} toques`}
                    </p>
                    {s.rationale && (
                      <p className="text-xs italic text-muted-foreground">
                        {s.rationale}
                      </p>
                    )}
                    <TickerLinks
                      ticker={s.ticker}
                      expanded={isExpanded}
                      geoTickers={geoTickers}
                      onExpandedTickerChange={onExpandedTickerChange}
                    />
                    {isExpanded && (
                      <div className="mt-2 border-t pt-2">
                        <OpcionesTab symbol={s.ticker} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {/* Desktop */}
            <Table className="hidden sm:table">
              <TableHeader>
                <TableRow>
                  <TableHead>Hora</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Dirección</TableHead>
                  <TableHead className="text-right">Zona</TableHead>
                  <TableHead className="text-right">Distancia</TableHead>
                  <TableHead className="text-right">P. ruptura</TableHead>
                  <TableHead>Razón</TableHead>
                  <TableHead>Ver en</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {signals.map((s) => {
                  const isExpanded = expandedTicker === s.ticker;
                  return (
                    <Fragment key={s.id}>
                      <TableRow className={s.alerted ? "" : "opacity-60"}>
                        <TableCell className="text-xs">
                          {fmtDateTime(s.created_at)}
                        </TableCell>
                        <TableCell className="font-medium">{s.ticker}</TableCell>
                        <TableCell>
                          <DirBadge direction={s.direction} />
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmt(s.zone_level)}
                          <span className="ml-1 text-xs text-muted-foreground">
                            {s.approach === "from_below" ? "↑" : "↓"}
                          </span>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {(s.distance_pct * 100).toFixed(2)}%
                        </TableCell>
                        <TableCell className="text-right">
                          <BreakProbability signal={s} />
                        </TableCell>
                        <TableCell className="max-w-[22rem] text-xs text-muted-foreground">
                          {s.rationale || "—"}
                        </TableCell>
                        <TableCell>
                          <TickerLinks
                            ticker={s.ticker}
                            expanded={isExpanded}
                            geoTickers={geoTickers}
                            onExpandedTickerChange={onExpandedTickerChange}
                          />
                        </TableCell>
                      </TableRow>
                      {isExpanded && (
                        <TableRow>
                          <TableCell colSpan={8} className="bg-muted/30 p-4">
                            <OpcionesTab symbol={s.ticker} />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
            <p className="border-t p-3 text-xs text-muted-foreground">
              Se muestran todos los candidatos puntuados, no solo los que alertan.
              La probabilidad la estima un modelo de lenguaje y{" "}
              <strong>no está calibrada</strong>: el corte en 70% es provisional
              hasta que el backtest diga si acierta.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function MonitorTab({
  loading,
  error,
  onRetry,
  filter,
  onFilterChange,
  alerts,
  unreadCount,
  unusual,
  techSignals,
  expandedTicker,
  onExpandedTickerChange,
  geoTickers,
  onAckAlert,
  onAckAll,
}: MonitorTabProps) {
  const techAlerting = techSignals.filter((s) => s.alerted).length;

  // Every scored candidate is shown, not just the alerting ones. Two reasons:
  // >70 is rare, so an alerted-only view would usually read empty (the exact
  // problem the cron just fixed); and showing the near-misses next to their
  // scores makes the threshold legible instead of magic. Alerting first, then
  // by score — an unscored signal (null) sorts last, since it's the least
  // actionable thing here, not the safest.
  const sortedTechSignals = [...techSignals].sort((a, b) => {
    if (a.alerted !== b.alerted) return a.alerted ? -1 : 1;
    return (b.break_probability ?? -1) - (a.break_probability ?? -1);
  });

  const expansion = { expandedTicker, onExpandedTickerChange, geoTickers };

  return (
    <TabsContent value="monitor" className="space-y-4">
      {loading ? (
        <div className="flex min-h-[30vh] items-center justify-center">
          <LoadingDots text="Cargando monitor" />
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
        <>
          <div className="flex items-center justify-between gap-2">
            <div className="flex gap-2">
              <Button
                variant={filter === "alerts" ? "default" : "outline"}
                size="sm"
                onClick={() => onFilterChange("alerts")}
              >
                <Bell className="mr-1.5 h-3.5 w-3.5" />
                Alertas
                {unreadCount > 0 && (
                  <Badge variant="destructive" className="ml-1.5 px-1.5 py-0.5 text-xs">
                    {unreadCount}
                  </Badge>
                )}
              </Button>
              <Button
                variant={filter === "unusual" ? "default" : "outline"}
                size="sm"
                onClick={() => onFilterChange("unusual")}
              >
                <Zap className="mr-1.5 h-3.5 w-3.5" />
                <span className="hidden sm:inline">Smart Money</span>
                <span className="sm:hidden">Smart $</span>
                {unusual.length > 0 && (
                  <span className="ml-1.5 text-xs opacity-70">{unusual.length}</span>
                )}
              </Button>
              <Button
                variant={filter === "technical" ? "default" : "outline"}
                size="sm"
                onClick={() => onFilterChange("technical")}
              >
                <Target className="mr-1.5 h-3.5 w-3.5" />
                Técnico
                {techAlerting > 0 && (
                  <Badge variant="destructive" className="ml-1.5 px-1.5 py-0.5 text-xs">
                    {techAlerting}
                  </Badge>
                )}
              </Button>
            </div>
            {filter === "alerts" && (
              <Button
                variant="outline"
                size="sm"
                onClick={onAckAll}
                disabled={unreadCount === 0}
              >
                <span className="hidden sm:inline">Marcar todas leídas</span>
                <span className="sm:hidden">Leídas</span>
              </Button>
            )}
          </div>

          {filter === "alerts" && (
            <AlertsPanel alerts={alerts} onAckAlert={onAckAlert} {...expansion} />
          )}

          {filter === "unusual" && <UnusualPanel unusual={unusual} />}

          {filter === "technical" && (
            <TechnicalSignalsPanel signals={sortedTechSignals} {...expansion} />
          )}
        </>
      )}
    </TabsContent>
  );
}
