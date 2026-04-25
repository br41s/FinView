"use client";

import { Fragment, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  Bell,
  ChevronDown,
  ChevronRight,
  Eye,
  Play,
  Square,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Zap,
} from "lucide-react";

import { api } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingDots } from "@/components/loading-dots";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// ── Types ───────────────────────────────────────────────────────────

interface Position {
  isin: string;
  ticker: string | null;
  name: string;
  country: string | null;
  broker: string;
  quantity: number;
  avg_cost_eur: number;
  total_cost_eur: number;
  current_price_eur: number | null;
  market_value_eur: number | null;
  unrealized_pl_eur: number | null;
  unrealized_pl_pct: number | null;
  weight_pct: number | null;
}

interface Snapshot {
  id: number;
  timestamp: string;
  ticker: string;
  current_price: string | number;
  call_volume: number;
  put_volume: number;
  put_call_ratio_volume: string | number | null;
  avg_call_iv: string | number | null;
  avg_put_iv: string | number | null;
  historical_volatility: string | number | null;
  iv_skew: string | number | null;
  market_sentiment: string | null;
}

interface Alert {
  id: number;
  timestamp: string;
  ticker: string;
  alert_type: string;
  message: string;
  severity: string;
  acknowledged: boolean;
}

interface Unusual {
  id: number;
  timestamp: string;
  ticker: string;
  option_type: string;
  strike: string | number;
  expiration: string;
  volume: number;
  open_interest: number;
  vol_oi_ratio: string | number;
  implied_volatility: string | number | null;
  last_price: string | number | null;
}

interface AgentStatus {
  running: boolean;
  interval_minutes: number;
  last_cycle: string | null;
  total_cycles: number;
}

interface WatchlistItem {
  id: number;
  ticker: string;
  name: string;
  enabled: boolean;
  created_at: string;
}

// ── Helpers ─────────────────────────────────────────────────────────

function fmt(n: number | string | null | undefined, d = 2): string {
  if (n == null) return "—";
  const v = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(v)) return "—";
  return v.toLocaleString("es-ES", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}

function severityColor(s: string) {
  switch (s) {
    case "HIGH":
      return "destructive";
    case "MEDIUM":
      return "secondary";
    default:
      return "outline";
  }
}

function sentimentIcon(s: string | null) {
  if (!s) return null;
  if (s.includes("BULLISH"))
    return <TrendingUp className="h-4 w-4 text-green-500" />;
  if (s.includes("BEARISH"))
    return <TrendingDown className="h-4 w-4 text-red-500" />;
  return <Activity className="h-4 w-4 text-muted-foreground" />;
}

// ── Component ───────────────────────────────────────────────────────

export default function OptionsPage() {
  const router = useRouter();
  const [positions, setPositions] = useState<Position[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [unusual, setUnusual] = useState<Unusual[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [loadingPositions, setLoadingPositions] = useState(true);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [running, setRunning] = useState(false);
  const [newTicker, setNewTicker] = useState("");
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);

  // Load portfolio positions first (fast, no external calls if cached)
  useEffect(() => {
    api.portfolio
      .positions()
      .then((pos) => setPositions(pos as Position[]))
      .catch((e) => console.error("Failed to load positions:", e))
      .finally(() => setLoadingPositions(false));
  }, []);

  // Load options data in parallel (independent of positions)
  useEffect(() => {
    Promise.all([
      api.options.snapshots() as Promise<Snapshot[]>,
      api.options.alerts() as Promise<Alert[]>,
      api.options.unusual() as Promise<Unusual[]>,
      api.options.watchlist() as Promise<WatchlistItem[]>,
      api.options.agentStatus() as Promise<AgentStatus>,
    ])
      .then(([snaps, alts, unu, wl, status]) => {
        setSnapshots(snaps);
        setAlerts(alts);
        setUnusual(unu);
        setWatchlist(wl);
        setAgentStatus(status);
      })
      .catch((e) => console.error("Failed to load options data:", e))
      .finally(() => setLoadingOptions(false));
  }, []);

  async function reloadOptions() {
    const [snaps, alts, unu, wl, status] = await Promise.all([
      api.options.snapshots() as Promise<Snapshot[]>,
      api.options.alerts() as Promise<Alert[]>,
      api.options.unusual() as Promise<Unusual[]>,
      api.options.watchlist() as Promise<WatchlistItem[]>,
      api.options.agentStatus() as Promise<AgentStatus>,
    ]);
    setSnapshots(snaps);
    setAlerts(alts);
    setUnusual(unu);
    setWatchlist(wl);
    setAgentStatus(status);
  }

  async function handleRunCycle() {
    setRunning(true);
    try {
      await api.options.runCycle();
      await reloadOptions();
    } finally {
      setRunning(false);
    }
  }

  async function handleToggleAgent() {
    if (agentStatus?.running) {
      await api.options.stopAgent();
    } else {
      await api.options.startAgent();
    }
    const status = (await api.options.agentStatus()) as AgentStatus;
    setAgentStatus(status);
  }

  async function handleAddTicker() {
    if (!newTicker.trim()) return;
    await api.options.addToWatchlist(newTicker.trim().toUpperCase());
    setNewTicker("");
    const wl = (await api.options.watchlist()) as WatchlistItem[];
    setWatchlist(wl);
  }

  async function handleRemoveTicker(id: number) {
    await api.options.removeFromWatchlist(id);
    setWatchlist((prev) => prev.filter((w) => w.id !== id));
  }

  async function handleAddPositionToWatchlist(ticker: string, name: string) {
    await api.options.addToWatchlist(ticker, name);
    const wl = (await api.options.watchlist()) as WatchlistItem[];
    setWatchlist(wl);
  }

  async function handleAckAlert(id: number) {
    await api.options.ackAlert(id);
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, acknowledged: true } : a)),
    );
  }

  async function handleAckAll() {
    await api.options.ackAllAlerts();
    setAlerts((prev) => prev.map((a) => ({ ...a, acknowledged: true })));
  }

  // Group latest snapshot per ticker
  const latestByTicker = new Map<string, Snapshot>();
  for (const s of snapshots) {
    if (!latestByTicker.has(s.ticker)) {
      latestByTicker.set(s.ticker, s);
    }
  }

  const unreadAlerts = alerts.filter((a) => !a.acknowledged);
  const watchlistTickers = new Set(watchlist.map((w) => w.ticker));

  // Get alerts/snapshots/unusual for a specific ticker
  function getTickerAlerts(ticker: string) {
    return alerts.filter((a) => a.ticker === ticker && !a.acknowledged);
  }
  function getTickerUnusual(ticker: string) {
    return unusual.filter((u) => u.ticker === ticker);
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Options Monitor</h1>
          <p className="text-muted-foreground">
            Análisis de opciones en tiempo real sobre tu cartera
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRunCycle}
            disabled={running}
          >
            {running ? (
              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Run Cycle
          </Button>
          <Button
            variant={agentStatus?.running ? "destructive" : "default"}
            size="sm"
            onClick={handleToggleAgent}
          >
            {agentStatus?.running ? (
              <>
                <Square className="mr-2 h-4 w-4" /> Stop
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" /> Auto
              </>
            )}
          </Button>
          <Button variant="outline" size="sm" onClick={() => router.push("/dashboard")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Dashboard
          </Button>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Posiciones</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{positions.length}</div>
            <p className="text-xs text-muted-foreground">
              en cartera · {watchlist.length} en watchlist
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Ciclos</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {agentStatus?.total_cycles ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              {agentStatus?.last_cycle
                ? `Último: ${new Date(agentStatus.last_cycle).toLocaleString("es-ES")}`
                : "Sin ciclos aún"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Alertas</CardTitle>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{unreadAlerts.length}</div>
            <p className="text-xs text-muted-foreground">
              {alerts.length} total (7d)
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Smart Money</CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{unusual.length}</div>
            <p className="text-xs text-muted-foreground">
              Actividad inusual (7d)
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="portfolio">
        <TabsList>
          <TabsTrigger value="portfolio">
            <BarChart3 className="mr-1 h-4 w-4" /> Cartera
          </TabsTrigger>
          <TabsTrigger value="watchlist">
            <Eye className="mr-1 h-4 w-4" /> Watchlist
          </TabsTrigger>
          <TabsTrigger value="alerts">
            <Bell className="mr-1 h-4 w-4" /> Alertas
            {unreadAlerts.length > 0 && (
              <Badge
                variant="destructive"
                className="ml-1 px-1.5 py-0.5 text-xs"
              >
                {unreadAlerts.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="unusual">
            <Zap className="mr-1 h-4 w-4" /> Smart Money
          </TabsTrigger>
        </TabsList>

        {/* ── Portfolio / Positions Tab ── */}
        <TabsContent value="portfolio" className="space-y-4">
          {loadingPositions ? (
            <div className="flex min-h-[30vh] items-center justify-center">
              <LoadingDots text="Obteniendo precios de mercado" />
            </div>
          ) : positions.length === 0 ? (
            <Card>
              <CardContent className="py-10 text-center text-muted-foreground">
                Sin posiciones en cartera. Importa datos desde el dashboard
                fiscal.
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Posiciones ({positions.length})</CardTitle>
                <CardDescription>
                  Pulsa en una posición para ver sus datos de opciones
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8" />
                      <TableHead>Ticker</TableHead>
                      <TableHead>Nombre</TableHead>
                      <TableHead>Broker</TableHead>
                      <TableHead className="text-right">Cantidad</TableHead>
                      <TableHead className="text-right">Precio</TableHead>
                      <TableHead className="text-right">Valor</TableHead>
                      <TableHead className="text-right">P&L</TableHead>
                      <TableHead className="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {positions.map((p) => {
                      const ticker = p.ticker || p.isin;
                      const isExpanded = expandedTicker === ticker;
                      const snap = latestByTicker.get(ticker);
                      const tickerAlerts = getTickerAlerts(ticker);
                      const tickerUnusual = getTickerUnusual(ticker);
                      const plPositive =
                        p.unrealized_pl_eur != null && p.unrealized_pl_eur >= 0;
                      const plClass = plPositive
                        ? "text-emerald-600"
                        : "text-red-600";

                      return (
                        <Fragment key={`${p.isin}-${p.broker}`}>
                          <TableRow
                            className="cursor-pointer hover:bg-muted/50"
                            onClick={() =>
                              setExpandedTicker(isExpanded ? null : ticker)
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
                              {ticker}
                              {tickerAlerts.length > 0 && (
                                <Badge
                                  variant="destructive"
                                  className="ml-2 px-1 py-0 text-[10px]"
                                >
                                  {tickerAlerts.length}
                                </Badge>
                              )}
                            </TableCell>
                            <TableCell className="max-w-48 truncate text-muted-foreground">
                              {p.name}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline" className="text-[10px]">
                                {p.broker}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {fmt(p.quantity)}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">
                              {p.current_price_eur
                                ? `${fmt(p.current_price_eur)} €`
                                : "—"}
                            </TableCell>
                            <TableCell className="text-right tabular-nums font-medium">
                              {p.market_value_eur
                                ? `${fmt(p.market_value_eur)} €`
                                : "—"}
                            </TableCell>
                            <TableCell
                              className={`text-right tabular-nums ${plClass}`}
                            >
                              {p.unrealized_pl_eur != null ? (
                                <span>
                                  {plPositive ? "+" : ""}
                                  {fmt(p.unrealized_pl_eur)} €
                                </span>
                              ) : (
                                "—"
                              )}
                            </TableCell>
                            <TableCell className="text-center">
                              {watchlistTickers.has(ticker) ? (
                                <Badge
                                  variant="secondary"
                                  className="text-[10px] px-1.5"
                                >
                                  <Eye className="h-3 w-3" />
                                </Badge>
                              ) : (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 w-7 p-0"
                                  title="Añadir a watchlist"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleAddPositionToWatchlist(
                                      ticker,
                                      p.name,
                                    );
                                  }}
                                >
                                  <Eye className="h-4 w-4 text-muted-foreground" />
                                </Button>
                              )}
                            </TableCell>
                          </TableRow>

                          {/* Expanded details */}
                          {isExpanded && (
                            <TableRow key={`${p.isin}-${p.broker}-detail`}>
                              <TableCell
                                colSpan={9}
                                className="bg-muted/30 p-4"
                              >
                                <div className="space-y-4">
                                  {/* Position summary */}
                                  <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                                    <div>
                                      <p className="text-xs text-muted-foreground">
                                        Coste medio
                                      </p>
                                      <p className="font-medium">
                                        {fmt(p.avg_cost_eur)} €
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-xs text-muted-foreground">
                                        Invertido
                                      </p>
                                      <p className="font-medium">
                                        {fmt(p.total_cost_eur)} €
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-xs text-muted-foreground">
                                        Rentabilidad
                                      </p>
                                      <p className={`font-medium ${plClass}`}>
                                        {p.unrealized_pl_pct != null
                                          ? `${p.unrealized_pl_pct >= 0 ? "+" : ""}${fmt(p.unrealized_pl_pct)}%`
                                          : "—"}
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-xs text-muted-foreground">
                                        Peso cartera
                                      </p>
                                      <p className="font-medium">
                                        {p.weight_pct
                                          ? `${fmt(p.weight_pct, 1)}%`
                                          : "—"}
                                      </p>
                                    </div>
                                  </div>

                                  {/* Options snapshot data */}
                                  {snap ? (
                                    <div>
                                      <h4 className="mb-2 text-sm font-semibold">
                                        Datos de opciones
                                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                                          {new Date(
                                            snap.timestamp,
                                          ).toLocaleString("es-ES")}
                                        </span>
                                      </h4>
                                      <div className="grid grid-cols-3 gap-3 md:grid-cols-6">
                                        <div>
                                          <p className="text-xs text-muted-foreground">
                                            Call Vol
                                          </p>
                                          <p className="font-medium">
                                            {snap.call_volume.toLocaleString()}
                                          </p>
                                        </div>
                                        <div>
                                          <p className="text-xs text-muted-foreground">
                                            Put Vol
                                          </p>
                                          <p className="font-medium">
                                            {snap.put_volume.toLocaleString()}
                                          </p>
                                        </div>
                                        <div>
                                          <p className="text-xs text-muted-foreground">
                                            P/C Ratio
                                          </p>
                                          <p className="font-medium">
                                            {fmt(snap.put_call_ratio_volume)}
                                          </p>
                                        </div>
                                        <div>
                                          <p className="text-xs text-muted-foreground">
                                            IV Skew
                                          </p>
                                          <p className="font-medium">
                                            {fmt(snap.iv_skew, 1)}%
                                          </p>
                                        </div>
                                        <div>
                                          <p className="text-xs text-muted-foreground">
                                            Call IV
                                          </p>
                                          <p className="font-medium">
                                            {fmt(snap.avg_call_iv, 1)}%
                                          </p>
                                        </div>
                                        <div>
                                          <p className="text-xs text-muted-foreground">
                                            Sentimiento
                                          </p>
                                          <div className="flex items-center gap-1">
                                            {sentimentIcon(
                                              snap.market_sentiment,
                                            )}
                                            <span className="text-sm">
                                              {snap.market_sentiment || "—"}
                                            </span>
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  ) : (
                                    <p className="text-sm text-muted-foreground">
                                      Sin datos de opciones. Añade{" "}
                                      <span className="font-medium">
                                        {ticker}
                                      </span>{" "}
                                      a la watchlist y ejecuta un ciclo.
                                    </p>
                                  )}

                                  {/* Alerts for this ticker */}
                                  {tickerAlerts.length > 0 && (
                                    <div>
                                      <h4 className="mb-2 text-sm font-semibold text-destructive">
                                        Alertas activas ({tickerAlerts.length})
                                      </h4>
                                      <div className="space-y-1">
                                        {tickerAlerts.map((a) => (
                                          <div
                                            key={a.id}
                                            className="flex items-center gap-2 text-sm"
                                          >
                                            <Badge
                                              variant={
                                                severityColor(a.severity) as
                                                  | "destructive"
                                                  | "secondary"
                                                  | "outline"
                                              }
                                              className="text-[10px]"
                                            >
                                              {a.severity}
                                            </Badge>
                                            <span>{a.message}</span>
                                            <Button
                                              variant="ghost"
                                              size="sm"
                                              className="ml-auto h-6 px-2 text-xs"
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                handleAckAlert(a.id);
                                              }}
                                            >
                                              Ack
                                            </Button>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}

                                  {/* Unusual activity for this ticker */}
                                  {tickerUnusual.length > 0 && (
                                    <div>
                                      <h4 className="mb-2 text-sm font-semibold text-amber-600">
                                        Actividad inusual (
                                        {tickerUnusual.length})
                                      </h4>
                                      <div className="space-y-1">
                                        {tickerUnusual.map((u) => (
                                          <div
                                            key={u.id}
                                            className="flex items-center gap-3 text-sm"
                                          >
                                            <Badge
                                              variant={
                                                u.option_type === "CALL"
                                                  ? "default"
                                                  : "secondary"
                                              }
                                              className="text-[10px]"
                                            >
                                              {u.option_type}
                                            </Badge>
                                            <span>
                                              Strike ${fmt(u.strike)} · Exp{" "}
                                              {u.expiration}
                                            </span>
                                            <span className="font-medium text-amber-600">
                                              Vol/OI {fmt(u.vol_oi_ratio, 1)}x
                                            </span>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </Fragment>
                      );
                    })}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Watchlist Tab ── */}
        <TabsContent value="watchlist" className="space-y-4">
          {loadingOptions ? (
            <div className="flex min-h-[30vh] items-center justify-center">
              <LoadingDots text="Cargando watchlist" />
            </div>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Gestionar Watchlist</CardTitle>
                <CardDescription>
                  Añade tickers para monitorizar su actividad de opciones
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2">
                  <input
                    className="flex h-9 w-full max-w-xs rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    placeholder="Ticker (ej. AAPL, ACX.MC)"
                    value={newTicker}
                    onChange={(e) => setNewTicker(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAddTicker()}
                  />
                  <Button size="sm" onClick={handleAddTicker}>
                    Añadir
                  </Button>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Ticker</TableHead>
                      <TableHead>Nombre</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead>Añadido</TableHead>
                      <TableHead className="text-right">Acciones</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {watchlist.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={5}
                          className="text-center text-muted-foreground"
                        >
                          Sin tickers en la watchlist
                        </TableCell>
                      </TableRow>
                    ) : (
                      watchlist.map((w) => (
                        <TableRow key={w.id}>
                          <TableCell className="font-medium">
                            {w.ticker}
                          </TableCell>
                          <TableCell>{w.name || "—"}</TableCell>
                          <TableCell>
                            <Badge
                              variant={w.enabled ? "default" : "secondary"}
                            >
                              {w.enabled ? "Activo" : "Pausado"}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {new Date(w.created_at).toLocaleDateString("es-ES")}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                api.options.toggleWatchlistItem(w.id).then(() =>
                                  setWatchlist((prev) =>
                                    prev.map((item) =>
                                      item.id === w.id
                                        ? {
                                            ...item,
                                            enabled: !item.enabled,
                                          }
                                        : item,
                                    ),
                                  ),
                                )
                              }
                            >
                              {w.enabled ? "Pausar" : "Activar"}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive"
                              onClick={() => handleRemoveTicker(w.id)}
                            >
                              Eliminar
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Alerts Tab ── */}
        <TabsContent value="alerts" className="space-y-4">
          {loadingOptions ? (
            <div className="flex min-h-[30vh] items-center justify-center">
              <LoadingDots text="Cargando alertas" />
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">Alertas recientes</h3>
                {unreadAlerts.length > 0 && (
                  <Button variant="outline" size="sm" onClick={handleAckAll}>
                    Marcar todas leídas
                  </Button>
                )}
              </div>
              <Card>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Hora</TableHead>
                        <TableHead>Ticker</TableHead>
                        <TableHead>Tipo</TableHead>
                        <TableHead>Mensaje</TableHead>
                        <TableHead>Severidad</TableHead>
                        <TableHead className="text-right">Acción</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {alerts.length === 0 ? (
                        <TableRow>
                          <TableCell
                            colSpan={6}
                            className="text-center text-muted-foreground"
                          >
                            Sin alertas aún
                          </TableCell>
                        </TableRow>
                      ) : (
                        alerts.map((a) => (
                          <TableRow
                            key={a.id}
                            className={a.acknowledged ? "opacity-50" : ""}
                          >
                            <TableCell className="text-xs">
                              {new Date(a.timestamp).toLocaleString("es-ES")}
                            </TableCell>
                            <TableCell className="font-medium">
                              {a.ticker}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">{a.alert_type}</Badge>
                            </TableCell>
                            <TableCell>{a.message}</TableCell>
                            <TableCell>
                              <Badge
                                variant={
                                  severityColor(a.severity) as
                                    | "destructive"
                                    | "secondary"
                                    | "outline"
                                }
                              >
                                {a.severity}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right">
                              {!a.acknowledged && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleAckAlert(a.id)}
                                >
                                  Ack
                                </Button>
                              )}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        {/* ── Smart Money Tab ── */}
        <TabsContent value="unusual" className="space-y-4">
          {loadingOptions ? (
            <div className="flex min-h-[30vh] items-center justify-center">
              <LoadingDots text="Cargando actividad" />
            </div>
          ) : (
            <>
              <h3 className="text-lg font-semibold">Actividad Inusual</h3>
              <Card>
                <CardContent className="p-0">
                  <Table>
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
                      {unusual.length === 0 ? (
                        <TableRow>
                          <TableCell
                            colSpan={9}
                            className="text-center text-muted-foreground"
                          >
                            Sin actividad inusual detectada
                          </TableCell>
                        </TableRow>
                      ) : (
                        unusual.map((u) => (
                          <TableRow key={u.id}>
                            <TableCell className="text-xs">
                              {new Date(u.timestamp).toLocaleString("es-ES")}
                            </TableCell>
                            <TableCell className="font-medium">
                              {u.ticker}
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant={
                                  u.option_type === "CALL"
                                    ? "default"
                                    : "secondary"
                                }
                              >
                                {u.option_type}
                              </Badge>
                            </TableCell>
                            <TableCell>${fmt(u.strike)}</TableCell>
                            <TableCell>{u.expiration}</TableCell>
                            <TableCell>{u.volume.toLocaleString()}</TableCell>
                            <TableCell>
                              {u.open_interest.toLocaleString()}
                            </TableCell>
                            <TableCell className="font-medium text-amber-600">
                              {fmt(u.vol_oi_ratio, 1)}x
                            </TableCell>
                            <TableCell>
                              {u.implied_volatility
                                ? `${fmt(Number(u.implied_volatility) * 100, 1)}%`
                                : "—"}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
