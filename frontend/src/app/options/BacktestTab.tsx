"use client";

import {
  BarChart,
  Bar,
  Cell,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  CheckCircle2,
  FlaskConical,
  RefreshCw,
  Target,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { LoadingDots } from "@/components/loading-dots";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TabsContent } from "@/components/ui/tabs";

import { fmt } from "./format";
import type { AlignBucket, Calibration } from "./types";
import type { Backtest } from "./useBacktest";

/**
 * The Backtest tab.
 *
 * Roughly 320 lines of JSX plus the two helpers only it used, moved out of a
 * 2,457-line page.tsx. Its data lives in `useBacktest`, held by the parent so
 * switching tabs does not refetch — see that hook for why.
 *
 * A pure extraction: the markup and both helpers are unchanged apart from the
 * state references now reading through the `backtest` prop.
 */

/** Calibration digest: dedup health + aligned-vs-counter edge per signal type. */
function CalibrationPanel({ calibration }: { calibration: Calibration }) {
  const { by_type_alignment, dedup_health } = calibration;
  const worst = Math.max(
    0,
    ...Object.values(dedup_health).map((d) => d.rows_per_ticker_day ?? 0),
  );
  const healthy = worst <= 2; // ~1/ticker-day is clean; high = re-recording per cycle
  const types = Object.keys(by_type_alignment);
  const fmt = (b?: AlignBucket) =>
    b && b.accuracy_pct != null ? `${b.accuracy_pct}% (${b.total})` : "—";

  return (
    <Card className="border-dashed">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">Calibración · últimos {calibration.window_days}d</CardTitle>
          <span
            title="Filas por ticker-día: ~1 = sano; alto = la misma condición se re-registra cada ciclo"
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${
              healthy
                ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
                : "bg-red-500/10 text-red-600 border-red-500/20"
            }`}
          >
            Dedup {healthy ? "✓" : "✗"} · {worst.toFixed(1)}/ticker-día
          </span>
        </div>
        <CardDescription>
          {calibration.evaluated_7d} evaluadas (7d) de {calibration.total} señales · desde {calibration.since}
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {types.length === 0 ? (
          <p className="px-6 pb-4 text-xs text-muted-foreground">
            Aún sin señales alineadas/contrarias evaluadas en la ventana — se llenan al madurar (7d).
          </p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tipo</TableHead>
                  <TableHead className="text-right">A favor</TableHead>
                  <TableHead className="text-right">En contra</TableHead>
                  <TableHead className="text-right">Ventaja</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {types.map((t) => {
                  const a = by_type_alignment[t].aligned;
                  const c = by_type_alignment[t].counter;
                  const edge =
                    a?.accuracy_pct != null && c?.accuracy_pct != null
                      ? Math.round((a.accuracy_pct - c.accuracy_pct) * 10) / 10
                      : null;
                  const edgeColor =
                    edge == null ? "" : edge >= 10 ? "text-emerald-600" : edge <= -10 ? "text-red-600" : "text-muted-foreground";
                  return (
                    <TableRow key={t}>
                      <TableCell><Badge variant="outline" className="text-[10px] whitespace-nowrap">{t}</Badge></TableCell>
                      <TableCell className="text-right">{fmt(a)}</TableCell>
                      <TableCell className="text-right">{fmt(c)}</TableCell>
                      <TableCell className={`text-right font-semibold ${edgeColor}`}>
                        {edge == null ? "—" : `${edge > 0 ? "+" : ""}${edge}pts`}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function outcomeCell(outcome: string | null, price: string | number | null) {
  if (outcome === null) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  if (outcome === "CORRECT") {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-medium text-emerald-600">
        <CheckCircle2 className="h-3 w-3" />
        {price != null ? fmt(price) : ""}
      </span>
    );
  }
  if (outcome === "INCORRECT") {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-medium text-red-600">
        <XCircle className="h-3 w-3" />
        {price != null ? fmt(price) : ""}
      </span>
    );
  }
  return <span className="text-xs text-muted-foreground">{price != null ? fmt(price) : "~"}</span>;
}

export function BacktestTab({ backtest }: { backtest: Backtest }) {
  // Destructured rather than read through the prop: TypeScript narrows a local
  // `stats` inside the guards this markup already uses, and cannot narrow a
  // property access across them.
  const { signals, stats, calibration, loading, evaluating, load, evaluate } = backtest;

  return (
          <TabsContent value="backtest" className="space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-lg font-semibold">Backtesting de señales</h3>
                <p className="text-sm text-muted-foreground">Precisión histórica de las alertas a +1D / +3D / +7D</p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={load} disabled={loading}>
                  <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                  Actualizar
                </Button>
                <Button variant="outline" size="sm" onClick={evaluate} disabled={evaluating}>
                  <Target className={`mr-2 h-4 w-4 ${evaluating ? "animate-spin" : ""}`} />
                  <span className="sm:hidden">Evaluar</span>
                  <span className="hidden sm:inline">Evaluar pendientes</span>
                </Button>
              </div>
            </div>

            {calibration && <CalibrationPanel calibration={calibration} />}

            {loading ? (
              <div className="flex min-h-[20vh] items-center justify-center">
                <LoadingDots text="Cargando backtesting" />
              </div>
            ) : !stats ? (
              <Card>
                <CardContent className="py-10 text-center text-muted-foreground">
                  <FlaskConical className="mx-auto mb-3 h-8 w-8 opacity-40" />
                  <p>Abre esta pestaña para cargar los datos de backtesting.</p>
                  <Button className="mt-4" size="sm" onClick={load}>Cargar</Button>
                </CardContent>
              </Card>
            ) : (
              <>
                {/* Accuracy stats by horizon */}
                <div className="grid gap-4 sm:grid-cols-3">
                  {(["1d", "3d", "7d"] as const).map((h) => {
                    const s = stats.by_horizon[h];
                    const acc = s?.accuracy_pct;
                    const color = acc == null ? "text-muted-foreground" : acc >= 60 ? "text-emerald-600" : acc >= 45 ? "text-amber-500" : "text-red-600";
                    return (
                      <Card key={h}>
                        <CardHeader className="flex flex-row items-center justify-between pb-2">
                          <CardTitle className="text-sm font-medium">Precisión {h.toUpperCase()}</CardTitle>
                          <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
                        </CardHeader>
                        <CardContent>
                          <div className={`text-2xl font-bold ${color}`}>
                            {acc != null ? `${acc}%` : "—"}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {s?.evaluated ?? 0} evaluadas · {s?.correct ?? 0} correctas
                          </p>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>

                {/* Accuracy by signal type — chart + table */}
                {Object.keys(stats.by_signal_type).length > 0 && (() => {
                  const signalChartData = Object.entries(stats.by_signal_type).map(
                    ([type, v]) => ({ type, accuracy: v.accuracy_pct ?? 0, total: v.total }),
                  );
                  return (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm">Precisión por tipo de señal (7D)</CardTitle>
                    </CardHeader>
                    <CardContent className="pb-2">
                      <ResponsiveContainer width="100%" height={Math.max(120, signalChartData.length * 36)}>
                        <BarChart data={signalChartData} layout="vertical" margin={{ left: 8, right: 32, top: 0, bottom: 0 }}>
                          <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickFormatter={(v) => `${v}%`} />
                          <YAxis type="category" dataKey="type" width={120} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                          <ChartTooltip
                            contentStyle={{ backgroundColor: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                            formatter={(value, _name, props) => [`${value}% (${props.payload.total} señales)`, "Precisión"]}
                          />
                          <Bar dataKey="accuracy" radius={[0, 4, 4, 0]}>
                            {signalChartData.map((entry, i) => (
                              <Cell
                                key={i}
                                fill={entry.accuracy >= 60 ? "#22c55e" : entry.accuracy >= 45 ? "#f59e0b" : "#ef4444"}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                    <CardContent className="p-0">
                      {/* Mobile */}
                      <div className="divide-y sm:hidden">
                        {Object.entries(stats.by_signal_type).map(([type, v]) => {
                          const acc = v.accuracy_pct;
                          const color = acc == null ? "" : acc >= 60 ? "text-emerald-600" : acc >= 45 ? "text-amber-500" : "text-red-600";
                          return (
                            <div key={type} className="flex items-center justify-between p-3 text-sm">
                              <Badge variant="outline" className="text-[10px] whitespace-nowrap">{type}</Badge>
                              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                                <span>{v.correct}/{v.total}</span>
                                <span className={`font-semibold ${color}`}>
                                  {acc != null ? `${acc}%` : "—"}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      {/* Desktop */}
                      <div className="hidden overflow-x-auto sm:block">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Tipo</TableHead>
                              <TableHead className="text-right">Total</TableHead>
                              <TableHead className="text-right">Correctas</TableHead>
                              <TableHead className="text-right">Precisión</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {Object.entries(stats.by_signal_type).map(([type, v]) => {
                              const acc = v.accuracy_pct;
                              const color = acc == null ? "" : acc >= 60 ? "text-emerald-600" : acc >= 45 ? "text-amber-500" : "text-red-600";
                              return (
                                <TableRow key={type}>
                                  <TableCell><Badge variant="outline" className="text-[10px] whitespace-nowrap">{type}</Badge></TableCell>
                                  <TableCell className="text-right">{v.total}</TableCell>
                                  <TableCell className="text-right">{v.correct}</TableCell>
                                  <TableCell className={`text-right font-semibold ${color}`}>
                                    {acc != null ? `${acc}%` : "—"}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    </CardContent>
                  </Card>
                  );
                })()}

                {/* Aligned vs counter accuracy (Phase 2b) */}
                {stats.by_alignment &&
                  Object.keys(stats.by_alignment).length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm">Precisión por régimen macro (7D)</CardTitle>
                      <CardDescription>
                        ¿Las señales a favor del régimen aciertan más que las que van en contra?
                        Instrumentación — no altera qué alertas se emiten.
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="p-0">
                      {/* Mobile */}
                      <div className="divide-y sm:hidden">
                        {(["aligned", "counter", "neutral"] as const)
                          .filter((k) => stats.by_alignment?.[k])
                          .map((k) => {
                            const v = stats.by_alignment![k];
                            const acc = v.accuracy_pct;
                            const color = acc == null ? "" : acc >= 60 ? "text-emerald-600" : acc >= 45 ? "text-amber-500" : "text-red-600";
                            const label = k === "aligned" ? "A favor (aligned)" : k === "counter" ? "En contra (counter)" : "Neutral";
                            return (
                              <div key={k} className="flex items-center justify-between p-3 text-sm">
                                <Badge variant="outline" className="text-[10px] whitespace-nowrap">{label}</Badge>
                                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                                  <span>{v.correct}/{v.total}</span>
                                  <span className={`font-semibold ${color}`}>
                                    {acc != null ? `${acc}%` : "—"}
                                  </span>
                                </div>
                              </div>
                            );
                          })}
                      </div>
                      {/* Desktop */}
                      <div className="hidden overflow-x-auto sm:block">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Alineación</TableHead>
                              <TableHead className="text-right">Total</TableHead>
                              <TableHead className="text-right">Correctas</TableHead>
                              <TableHead className="text-right">Precisión</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {(["aligned", "counter", "neutral"] as const)
                              .filter((k) => stats.by_alignment?.[k])
                              .map((k) => {
                                const v = stats.by_alignment![k];
                                const acc = v.accuracy_pct;
                                const color = acc == null ? "" : acc >= 60 ? "text-emerald-600" : acc >= 45 ? "text-amber-500" : "text-red-600";
                                const label = k === "aligned" ? "A favor (aligned)" : k === "counter" ? "En contra (counter)" : "Neutral";
                                return (
                                  <TableRow key={k}>
                                    <TableCell><Badge variant="outline" className="text-[10px] whitespace-nowrap">{label}</Badge></TableCell>
                                    <TableCell className="text-right">{v.total}</TableCell>
                                    <TableCell className="text-right">{v.correct}</TableCell>
                                    <TableCell className={`text-right font-semibold ${color}`}>
                                      {acc != null ? `${acc}%` : "—"}
                                    </TableCell>
                                  </TableRow>
                                );
                              })}
                          </TableBody>
                        </Table>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Signals table */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Señales recientes (30d)</CardTitle>
                    <CardDescription>{signals.length} señales registradas</CardDescription>
                  </CardHeader>
                  <CardContent className="p-0">
                    {signals.length === 0 ? (
                      <div className="py-8 text-center text-muted-foreground">
                        Sin señales registradas. Ejecuta un ciclo del agente para empezar a acumular datos.
                      </div>
                    ) : (
                      <>
                        {/* Mobile: vertical cards */}
                        <div className="flex flex-col divide-y sm:hidden">
                          {signals.map((s) => (
                            <div key={s.id} className="flex flex-col gap-2 px-4 py-3">
                              <div className="flex items-center justify-between">
                                <span className="font-semibold">{s.ticker}</span>
                                <span className="text-xs text-muted-foreground">
                                  {new Date(s.recorded_at).toLocaleString("es-ES", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                                </span>
                              </div>
                              <div className="flex items-center gap-2">
                                <Badge variant="outline" className="text-[10px]">{s.signal_type}</Badge>
                                {s.direction === "BULLISH" ? (
                                  <span className="flex items-center gap-1 text-emerald-600 text-xs font-medium">
                                    <TrendingUp className="h-3 w-3" /> BULLISH
                                  </span>
                                ) : (
                                  <span className="flex items-center gap-1 text-red-600 text-xs font-medium">
                                    <TrendingDown className="h-3 w-3" /> BEARISH
                                  </span>
                                )}
                                <span className="ml-auto tabular-nums text-xs">{fmt(s.price_at_signal)} $</span>
                              </div>
                              <div className="flex gap-4">
                                <div className="flex flex-col items-center gap-0.5">
                                  <span className="text-[10px] text-muted-foreground">+1D</span>
                                  {outcomeCell(s.outcome_1d, s.price_at_1d)}
                                </div>
                                <div className="flex flex-col items-center gap-0.5">
                                  <span className="text-[10px] text-muted-foreground">+3D</span>
                                  {outcomeCell(s.outcome_3d, s.price_at_3d)}
                                </div>
                                <div className="flex flex-col items-center gap-0.5">
                                  <span className="text-[10px] text-muted-foreground">+7D</span>
                                  {outcomeCell(s.outcome_7d, s.price_at_7d)}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>

                        {/* Desktop: table */}
                        <div className="hidden overflow-x-auto sm:block">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>Fecha</TableHead>
                                <TableHead>Ticker</TableHead>
                                <TableHead>Tipo</TableHead>
                                <TableHead>Dirección</TableHead>
                                <TableHead className="text-right">Precio</TableHead>
                                <TableHead className="text-center">+1D</TableHead>
                                <TableHead className="text-center">+3D</TableHead>
                                <TableHead className="text-center">+7D</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {signals.map((s) => (
                                <TableRow key={s.id}>
                                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                                    {new Date(s.recorded_at).toLocaleString("es-ES", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                                  </TableCell>
                                  <TableCell className="font-medium">{s.ticker}</TableCell>
                                  <TableCell><Badge variant="outline" className="text-[10px]">{s.signal_type}</Badge></TableCell>
                                  <TableCell>
                                    {s.direction === "BULLISH" ? (
                                      <span className="flex items-center gap-1 text-emerald-600 text-xs font-medium">
                                        <TrendingUp className="h-3 w-3" /> BULLISH
                                      </span>
                                    ) : (
                                      <span className="flex items-center gap-1 text-red-600 text-xs font-medium">
                                        <TrendingDown className="h-3 w-3" /> BEARISH
                                      </span>
                                    )}
                                  </TableCell>
                                  <TableCell className="text-right tabular-nums">{fmt(s.price_at_signal)} $</TableCell>
                                  <TableCell className="text-center">{outcomeCell(s.outcome_1d, s.price_at_1d)}</TableCell>
                                  <TableCell className="text-center">{outcomeCell(s.outcome_3d, s.price_at_3d)}</TableCell>
                                  <TableCell className="text-center">{outcomeCell(s.outcome_7d, s.price_at_7d)}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </>
                    )}
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>
  );
}
