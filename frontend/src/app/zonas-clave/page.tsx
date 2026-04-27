"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  RefreshCw,
  Target,
  TrendingDown,
  TrendingUp,
  Play,
  Square,
} from "lucide-react";
import {
  ComposedChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

import { api, type ZcAnalysis, type ZcWatchlistItem } from "@/lib/api";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// ── Helpers ──────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, d = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("es-ES", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}

const ISIN_RE = /^[A-Z]{2}[A-Z0-9]{10}$/;

function tickerLabel(item: ZcWatchlistItem): string {
  if (ISIN_RE.test(item.ticker)) {
    // ISIN stored instead of a real ticker — derive a short display label from name
    return item.name.trim().split(/\s+/).slice(0, 2).join(" ").substring(0, 14);
  }
  return item.ticker;
}

function macdLabel(signal: string | null) {
  if (signal === "bullish") return "Alcista";
  if (signal === "bearish") return "Bajista";
  return "Neutral";
}

function macdColor(signal: string | null) {
  if (signal === "bullish") return "text-emerald-600";
  if (signal === "bearish") return "text-red-600";
  return "text-muted-foreground";
}

// ── Component ────────────────────────────────────────────────────────

export default function ZonasClavePage() {
  const router = useRouter();
  const [watchlist, setWatchlist] = useState<ZcWatchlistItem[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, ZcAnalysis>>({});
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState<Set<string>>(new Set());
  const [schedulerRunning, setSchedulerRunning] = useState(false);

  // Initial load
  useEffect(() => {
    Promise.all([
      api.zonasClav.watchlist(),
      api.zonasClav.allAnalyses(),
      api.zonasClav.schedulerStatus(),
    ])
      .then(([wl, analysisArr, status]) => {
        setWatchlist(wl);
        const map: Record<string, ZcAnalysis> = {};
        for (const a of analysisArr) {
          const item = wl.find((w) => w.id === a.watchlist_item_id);
          if (item) map[item.ticker] = a;
        }
        setAnalyses(map);
        setSchedulerRunning(status.running);
        if (wl.length > 0 && !selectedTicker) {
          setSelectedTicker(wl[0].ticker);
        }
      })
      .catch((e) => console.error("Failed to load Zonas Clave:", e))
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRemove(item: ZcWatchlistItem) {
    await api.zonasClav.removeTicker(item.id);
    setWatchlist((prev) => prev.filter((w) => w.id !== item.id));
    setAnalyses((prev) => {
      const next = { ...prev };
      delete next[item.ticker];
      return next;
    });
    if (selectedTicker === item.ticker) {
      const remaining = watchlist.filter((w) => w.id !== item.id);
      setSelectedTicker(remaining[0]?.ticker ?? null);
    }
  }

  async function handleRefresh(ticker: string) {
    setAnalyzing((prev) => new Set(prev).add(ticker));
    try {
      const result = await api.zonasClav.triggerAnalysis(ticker);
      setAnalyses((prev) => ({ ...prev, [ticker]: result }));
    } catch (e) {
      console.error("Analysis failed:", e);
    } finally {
      setAnalyzing((prev) => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    }
  }

  async function handleRefreshAll() {
    const tickers = watchlist.map((w) => w.ticker);
    setAnalyzing(new Set(tickers));
    try {
      await api.zonasClav.triggerAll();
      // Re-fetch analyses after a short delay to pick up background results
      setTimeout(async () => {
        const analysisArr = await api.zonasClav.allAnalyses();
        const map: Record<string, ZcAnalysis> = {};
        for (const a of analysisArr) {
          const item = watchlist.find((w) => w.id === a.watchlist_item_id);
          if (item) map[item.ticker] = a;
        }
        setAnalyses(map);
        setAnalyzing(new Set());
      }, 3000);
    } catch (e) {
      console.error("Refresh all failed:", e);
      setAnalyzing(new Set());
    }
  }

  async function handleToggleScheduler() {
    if (schedulerRunning) {
      await api.zonasClav.stopScheduler();
      setSchedulerRunning(false);
    } else {
      await api.zonasClav.startScheduler();
      setSchedulerRunning(true);
    }
  }

  const analysis = selectedTicker ? analyses[selectedTicker] : null;
  const isAnalyzing = selectedTicker ? analyzing.has(selectedTicker) : false;

  // Chart data — filter zones within ±30% of current price
  const priceHistory = analysis?.price_history ?? [];
  const currentPrice = analysis?.current_price ?? 0;
  const visibleZones = (analysis?.zones ?? []).filter(
    (z) => currentPrice === 0 || Math.abs(z.level - currentPrice) / currentPrice < 0.3,
  );

  const allPrices = priceHistory.map((p) => p.close);
  const allLevels = visibleZones.map((z) => z.level);
  const yMin =
    allPrices.length > 0
      ? Math.min(...allPrices, ...allLevels) * 0.97
      : undefined;
  const yMax =
    allPrices.length > 0
      ? Math.max(...allPrices, ...allLevels) * 1.03
      : undefined;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Zonas Clave</h1>
          <p className="text-muted-foreground">
            Soportes, resistencias y tendencia algorítmica
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefreshAll}
            disabled={watchlist.length === 0 || analyzing.size > 0}
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${analyzing.size > 0 ? "animate-spin" : ""}`} />
            Actualizar todo
          </Button>
          <Button
            variant={schedulerRunning ? "destructive" : "default"}
            size="sm"
            onClick={handleToggleScheduler}
          >
            {schedulerRunning ? (
              <><Square className="mr-2 h-4 w-4" /> Parar auto</>
            ) : (
              <><Play className="mr-2 h-4 w-4" /> Auto (24h)</>
            )}
          </Button>
          <Button variant="outline" size="sm" onClick={() => router.push("/portfolio")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Cartera
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex min-h-[50vh] items-center justify-center">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Activity className="h-5 w-5 animate-pulse" />
            <span>Cargando análisis...</span>
          </div>
        </div>
      ) : watchlist.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-muted-foreground">
            <Target className="mx-auto mb-4 h-10 w-10 opacity-30" />
            <p className="text-sm">
              No tienes valores en Zonas Clave. Añádelos desde la sección{" "}
              <button
                className="text-primary underline"
                onClick={() => router.push("/portfolio")}
              >
                Cartera
              </button>
              .
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr]">
          {/* Left — ticker list */}
          <Card className="h-fit">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Valores</CardTitle>
            </CardHeader>
            <CardContent className="p-2">
              <div className="space-y-1">
                {watchlist.map((item) => {
                  const a = analyses[item.ticker];
                  const isSelected = selectedTicker === item.ticker;
                  const isPending = analyzing.has(item.ticker);
                  return (
                    <div
                      key={item.id}
                      className={`group flex items-center justify-between rounded-md px-3 py-2 cursor-pointer transition-colors ${
                        isSelected
                          ? "bg-primary text-primary-foreground"
                          : "hover:bg-muted"
                      }`}
                      onClick={() => setSelectedTicker(item.ticker)}
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {tickerLabel(item)}
                        </p>
                        {a?.trend_bias_bullish_pct != null && (
                          <p className={`text-xs ${isSelected ? "text-primary-foreground/70" : "text-muted-foreground"}`}>
                            {a.trend_bias_bullish_pct.toFixed(0)}% alcista
                          </p>
                        )}
                        {!a && !isPending && (
                          <p className={`text-xs ${isSelected ? "text-primary-foreground/70" : "text-muted-foreground"}`}>
                            Analizando...
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-1 shrink-0 ml-2">
                        {isPending && (
                          <RefreshCw className="h-3 w-3 animate-spin opacity-60" />
                        )}
                        <button
                          className={`opacity-0 group-hover:opacity-100 transition-opacity text-xs ${
                            isSelected ? "text-primary-foreground/70 hover:text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                          }`}
                          title="Actualizar"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRefresh(item.ticker);
                          }}
                        >
                          <RefreshCw className="h-3 w-3" />
                        </button>
                        <button
                          className={`opacity-0 group-hover:opacity-100 transition-opacity text-xs ${
                            isSelected ? "text-primary-foreground/70 hover:text-primary-foreground" : "text-muted-foreground hover:text-destructive"
                          }`}
                          title="Eliminar"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemove(item);
                          }}
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Right — chart + details */}
          <div className="space-y-4">
            {isAnalyzing || (!analysis && selectedTicker) ? (
              <Card>
                <CardContent className="flex min-h-[400px] items-center justify-center">
                  <div className="text-center text-muted-foreground">
                    <RefreshCw className="mx-auto mb-3 h-8 w-8 animate-spin opacity-40" />
                    <p className="text-sm">Analizando {selectedTicker}...</p>
                    <p className="text-xs mt-1 opacity-60">
                      Descargando 5 años de datos y calculando zonas
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : analysis ? (
              <>
                {/* Trend bias card */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">
                      Tendencia estimada — {selectedTicker}
                      <span className="ml-2 text-xs font-normal text-muted-foreground">
                        {new Date(analysis.timestamp).toLocaleString("es-ES")}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center gap-6">
                      <div className="flex items-center gap-2">
                        <TrendingUp className="h-5 w-5 text-emerald-600" />
                        <span className="text-2xl font-bold text-emerald-600">
                          {fmt(analysis.trend_bias_bullish_pct, 0)}%
                        </span>
                        <span className="text-sm text-muted-foreground">alcista</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <TrendingDown className="h-5 w-5 text-red-600" />
                        <span className="text-2xl font-bold text-red-600">
                          {fmt(analysis.trend_bias_bearish_pct, 0)}%
                        </span>
                        <span className="text-sm text-muted-foreground">bajista</span>
                      </div>
                    </div>
                    <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-emerald-500 transition-all"
                        style={{ width: `${analysis.trend_bias_bullish_pct ?? 50}%` }}
                      />
                    </div>
                    <div className="mt-3 flex gap-6 text-sm text-muted-foreground">
                      <span>
                        RSI:{" "}
                        <span
                          className={
                            (analysis.rsi ?? 50) > 70
                              ? "font-medium text-red-600"
                              : (analysis.rsi ?? 50) < 30
                                ? "font-medium text-emerald-600"
                                : "font-medium text-foreground"
                          }
                        >
                          {fmt(analysis.rsi, 1)}
                        </span>
                      </span>
                      <span>
                        MACD:{" "}
                        <span className={`font-medium ${macdColor(analysis.macd_signal)}`}>
                          {macdLabel(analysis.macd_signal)}
                        </span>
                      </span>
                      <span>
                        Precio:{" "}
                        <span className="font-medium text-foreground">
                          {fmt(analysis.current_price, 2)}
                        </span>
                      </span>
                    </div>
                  </CardContent>
                </Card>

                {/* Price chart with zones */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">
                      Gráfico de precio y zonas clave
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {priceHistory.length === 0 ? (
                      <Skeleton className="h-64 w-full" />
                    ) : (
                      <ResponsiveContainer width="100%" height={360}>
                        <ComposedChart
                          data={priceHistory}
                          margin={{ top: 4, right: 60, bottom: 4, left: 4 }}
                        >
                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke="hsl(var(--border))"
                            opacity={0.5}
                          />
                          <XAxis
                            dataKey="date"
                            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                            tickFormatter={(d: string) =>
                              new Date(d).toLocaleDateString("es-ES", {
                                month: "short",
                                year: "2-digit",
                              })
                            }
                            interval="preserveStartEnd"
                          />
                          <YAxis
                            domain={[yMin ?? "auto", yMax ?? "auto"]}
                            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                            tickFormatter={(v: number) => v.toFixed(0)}
                            width={55}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: "hsl(var(--popover))",
                              border: "1px solid hsl(var(--border))",
                              borderRadius: 8,
                              fontSize: 12,
                            }}
                            formatter={(value: unknown) => [fmt(Number(value), 2), "Precio"]}
                            labelFormatter={(label: unknown) =>
                              new Date(String(label)).toLocaleDateString("es-ES")
                            }
                          />
                          <Line
                            dataKey="close"
                            stroke="#60a5fa"
                            dot={false}
                            strokeWidth={1.5}
                            isAnimationActive={false}
                          />
                          {visibleZones.map((z, i) => (
                            <ReferenceLine
                              key={i}
                              y={z.level}
                              stroke={z.zone_type === "support" ? "#22c55e" : "#ef4444"}
                              strokeDasharray={z.strength > 0.7 ? undefined : "4 2"}
                              strokeWidth={Math.max(1, Math.round(z.strength * 2.5))}
                              label={{
                                value: fmt(z.level, 2),
                                fill: z.zone_type === "support" ? "#22c55e" : "#ef4444",
                                fontSize: 10,
                                position: "right",
                              }}
                            />
                          ))}
                        </ComposedChart>
                      </ResponsiveContainer>
                    )}
                  </CardContent>
                </Card>

                {/* Zones table */}
                {analysis.zones.length > 0 && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium">
                        Zonas detectadas ({analysis.zones.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Tipo</TableHead>
                            <TableHead className="text-right">Nivel</TableHead>
                            <TableHead className="text-right">Fuerza</TableHead>
                            <TableHead className="text-right">Toques</TableHead>
                            <TableHead className="text-right">Vol. score</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {analysis.zones.map((z, i) => (
                            <TableRow key={i}>
                              <TableCell>
                                <Badge
                                  variant={z.zone_type === "support" ? "default" : "destructive"}
                                  className="text-[10px]"
                                >
                                  {z.zone_type === "support" ? "Soporte" : "Resistencia"}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-right tabular-nums font-medium">
                                {fmt(z.level, 2)}
                              </TableCell>
                              <TableCell className="text-right tabular-nums">
                                <div className="flex items-center justify-end gap-2">
                                  <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                                    <div
                                      className={`h-full rounded-full ${z.zone_type === "support" ? "bg-emerald-500" : "bg-red-500"}`}
                                      style={{ width: `${z.strength * 100}%` }}
                                    />
                                  </div>
                                  <span className="text-xs text-muted-foreground w-8">
                                    {(z.strength * 100).toFixed(0)}%
                                  </span>
                                </div>
                              </TableCell>
                              <TableCell className="text-right tabular-nums">
                                {z.touches}
                              </TableCell>
                              <TableCell className="text-right tabular-nums text-muted-foreground">
                                {fmt(z.volume_score, 2)}x
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
