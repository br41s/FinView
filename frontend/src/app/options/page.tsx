"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  CheckCircle2,
  ChevronRight,
  Eye,
  EyeOff,
  FlaskConical,
  MessageSquare,
  Send,
  Sparkles,
  Square,
  RefreshCw,
  Target,
  Trash2,
  TrendingUp,
  TrendingDown,
  Zap,
  AlertCircle,
  XCircle,
} from "lucide-react";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as ChartTooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
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
import { QuickNav } from "@/components/QuickNav";
import { useInstrumentDrawer } from "@/components/InstrumentDrawer";

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
  regime_alignment?: string | null;
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

interface BacktestSignal {
  id: number;
  recorded_at: string;
  ticker: string;
  signal_type: string;
  direction: string;
  price_at_signal: string | number;
  alert_message: string;
  price_at_1d: string | number | null;
  price_at_3d: string | number | null;
  price_at_7d: string | number | null;
  outcome_1d: string | null;
  outcome_3d: string | null;
  outcome_7d: string | null;
}

interface BacktestHorizonStats {
  evaluated: number;
  correct: number;
  incorrect: number;
  neutral: number;
  accuracy_pct: number | null;
}

interface BacktestStats {
  total: number;
  evaluated: number;
  by_horizon: Record<string, BacktestHorizonStats>;
  by_signal_type: Record<string, { correct: number; total: number; accuracy_pct: number | null }>;
  by_alignment?: Record<string, { correct: number; total: number; accuracy_pct: number | null }>;
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

// ── MEFF Spanish tickers (verified May 2026) ────────────────────────

const MEFF_TICKERS: { ticker: string; name: string }[] = [
  { ticker: "ACX.MC", name: "Acerinox" },
  { ticker: "AENA.MC", name: "AENA" },
  { ticker: "AMS.MC", name: "Amadeus IT" },
  { ticker: "ANA.MC", name: "Acciona" },
  { ticker: "BBVA.MC", name: "BBVA" },
  { ticker: "BKT.MC", name: "Bankinter" },
  { ticker: "CABK.MC", name: "CaixaBank" },
  { ticker: "CIE.MC", name: "CIE Automotive" },
  { ticker: "CLNX.MC", name: "Cellnex" },
  { ticker: "COL.MC", name: "Inmobiliaria Colonial" },
  { ticker: "ELE.MC", name: "Endesa" },
  { ticker: "ENG.MC", name: "Enagás" },
  { ticker: "FER.MC", name: "Ferrovial" },
  { ticker: "GRF.MC", name: "Grifols" },
  { ticker: "IAG.MC", name: "IAG (Iberia)" },
  { ticker: "IBE.MC", name: "Iberdrola" },
  { ticker: "IDR.MC", name: "Indra" },
  { ticker: "ITX.MC", name: "Inditex" },
  { ticker: "MAP.MC", name: "MAPFRE" },
  { ticker: "MEL.MC", name: "Meliá Hotels" },
  { ticker: "MRL.MC", name: "Merlin Properties" },
  { ticker: "NTGY.MC", name: "Naturgy" },
  { ticker: "PHM.MC", name: "PharmaMar" },
  { ticker: "RED.MC", name: "REDEIA" },
  { ticker: "REP.MC", name: "Repsol" },
  { ticker: "SAB.MC", name: "Banco Sabadell" },
  { ticker: "SAN.MC", name: "Banco Santander" },
  { ticker: "SLR.MC", name: "Solaria" },
  { ticker: "TEF.MC", name: "Telefónica" },
  { ticker: "VIS.MC", name: "Viscofan" },
];

// ── Component ───────────────────────────────────────────────────────

export default function OptionsPage() {
  const { openInstrument } = useInstrumentDrawer();
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
  const [hiddenTickers, setHiddenTickers] = useState<Set<string>>(new Set());
  const [noOptionsTickers, setNoOptionsTickers] = useState<Set<string>>(new Set());
  const [availabilityChecked, setAvailabilityChecked] = useState(false);
  const [backtestSignals, setBacktestSignals] = useState<BacktestSignal[]>([]);
  const [backtestStats, setBacktestStats] = useState<BacktestStats | null>(null);
  const [loadingBacktest, setLoadingBacktest] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [analysisCycle, setAnalysisCycle] = useState(0);
  const [monitorFilter, setMonitorFilter] = useState<"alerts" | "unusual">("alerts");
  const [activeTab, setActiveTab] = useState("portfolio");
  const [errorPositions, setErrorPositions] = useState<string | null>(null);
  const [errorOptions, setErrorOptions] = useState<string | null>(null);
  const [retryPositions, setRetryPositions] = useState(0);
  const [retryOptions, setRetryOptions] = useState(0);

  // N6: auto-expand ticker from URL param (?ticker=X)
  const initialTickerRef = useRef<string | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    initialTickerRef.current = params.get("ticker");
  }, []);

  // Load portfolio positions with skip_prices=true — no yfinance calls, instant response
  useEffect(() => {
    setErrorPositions(null);
    api.portfolio
      .positions(true)
      .then(async (pos) => {
        const loaded = pos as Position[];
        setPositions(loaded);
        if (loaded.length === 0) return;
        const tickers = [...new Set(loaded.map((p) => (p.ticker || p.isin).toUpperCase()))];
        // Auto-expand ticker from URL param if it exists in positions
        if (initialTickerRef.current) {
          const hint = initialTickerRef.current.toUpperCase();
          initialTickerRef.current = null;
          if (tickers.includes(hint)) openInstrument(hint, { tab: "opciones" });
        }
        try {
          const { no_options } = await api.options.checkAvailability(tickers);
          setNoOptionsTickers(new Set(no_options));
        } catch {
          // ignore — positions remain visible if check fails
        }
      })
      .catch((e) => {
        console.error("Failed to load positions:", e);
        setErrorPositions("No se pudieron cargar las posiciones de cartera.");
      })
      .finally(() => {
        setLoadingPositions(false);
        setAvailabilityChecked(true);
      });
  }, [retryPositions]);

  // Load options data in parallel (independent of positions)
  useEffect(() => {
    setErrorOptions(null);
    Promise.all([
      api.options.snapshots() as Promise<Snapshot[]>,
      api.options.alerts() as Promise<Alert[]>,
      api.options.unusual() as Promise<Unusual[]>,
      api.options.watchlist() as Promise<WatchlistItem[]>,
      api.options.agentStatus() as Promise<AgentStatus>,
      api.options.hiddenPortfolioTickers() as Promise<string[]>,
    ])
      .then(([snaps, alts, unu, wl, status, hidden]) => {
        setSnapshots(snaps);
        setAlerts(alts);
        setUnusual(unu);
        setWatchlist(wl);
        setAgentStatus(status);
        setHiddenTickers(new Set(hidden));
      })
      .catch((e) => {
        console.error("Failed to load options data:", e);
        setErrorOptions("No se pudieron cargar los datos de opciones.");
      })
      .finally(() => setLoadingOptions(false));
  }, [retryOptions]);

  // Auto-sync: portfolio positions get added to the options watchlist so
  // Sentimiento/P-C Ratio/IV vs HV populate without a manual click. Waits for
  // the availability check (so we skip tickers with no options chain) and for
  // the watchlist itself to be loaded (so we don't re-add what's already
  // there). Re-fetching the watchlist after adding converges this to a no-op
  // once everything is synced — no infinite loop.
  useEffect(() => {
    if (!availabilityChecked || loadingOptions || positions.length === 0) return;
    const watchlistSet = new Set(watchlist.map((w) => w.ticker));
    const toAdd = new Map(
      positions
        .map((p) => ({ ticker: (p.ticker || p.isin || "").toUpperCase(), name: p.name }))
        .filter(
          ({ ticker }) =>
            ticker !== "" &&
            !hiddenTickers.has(ticker) &&
            !noOptionsTickers.has(ticker) &&
            !watchlistSet.has(ticker),
        )
        .map((t) => [t.ticker, t]),
    );
    if (toAdd.size === 0) return;
    let cancelled = false;
    (async () => {
      for (const { ticker, name } of toAdd.values()) {
        if (cancelled) return;
        try {
          await api.options.addToWatchlist(ticker, name);
        } catch {
          // ignore — e.g. already added by a concurrent sync, will settle next pass
        }
      }
      if (cancelled) return;
      const wl = (await api.options.watchlist()) as WatchlistItem[];
      if (!cancelled) setWatchlist(wl);
    })();
    return () => {
      cancelled = true;
    };
  }, [availabilityChecked, loadingOptions, positions, watchlist, hiddenTickers, noOptionsTickers]);

  async function reloadOptions() {
    const [snaps, alts, unu, wl, status, hidden] = await Promise.all([
      api.options.snapshots() as Promise<Snapshot[]>,
      api.options.alerts() as Promise<Alert[]>,
      api.options.unusual() as Promise<Unusual[]>,
      api.options.watchlist() as Promise<WatchlistItem[]>,
      api.options.agentStatus() as Promise<AgentStatus>,
      api.options.hiddenPortfolioTickers() as Promise<string[]>,
    ]);
    setSnapshots(snaps);
    setAlerts(alts);
    setUnusual(unu);
    setWatchlist(wl);
    setAgentStatus(status);
    setHiddenTickers(new Set(hidden));
  }

  async function handleRunCycle() {
    setRunning(true);
    try {
      await api.options.runCycle();
      await reloadOptions();
      setAnalysisCycle((c) => c + 1);
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

  async function handleRemoveTicker(id: number, ticker?: string) {
    await api.options.removeFromWatchlist(id);
    setWatchlist((prev) => prev.filter((w) => w.id !== id));
    if (ticker) {
      setAlerts((prev) => prev.filter((a) => a.ticker !== ticker));
      setUnusual((prev) => prev.filter((u) => u.ticker !== ticker));
    }
  }

  async function handleRemoveFromCartera(ticker: string) {
    const item = watchlist.find((w) => w.ticker === ticker);
    if (!item) return;
    await handleRemoveTicker(item.id, ticker);
  }

  async function handleHidePosition(ticker: string) {
    // Remove from watchlist if present
    const item = watchlist.find((w) => w.ticker === ticker);
    if (item) await handleRemoveTicker(item.id, ticker);
    // Persist exclusion from options monitor
    await api.options.hidePortfolioTicker(ticker);
    setHiddenTickers((prev) => new Set([...prev, ticker]));
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

  async function loadBacktest() {
    setLoadingBacktest(true);
    try {
      const [sigs, stats] = await Promise.all([
        api.options.backtestSignals({ days: 30 }) as Promise<BacktestSignal[]>,
        api.options.backtestStats() as Promise<BacktestStats>,
      ]);
      setBacktestSignals(sigs);
      setBacktestStats(stats);
    } catch (e) {
      console.error("Failed to load backtest data:", e);
    } finally {
      setLoadingBacktest(false);
    }
  }

  async function handleEvaluate() {
    setEvaluating(true);
    try {
      await api.options.backtestEvaluate();
      await loadBacktest();
    } finally {
      setEvaluating(false);
    }
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

  // Global P/C sentiment — average put_call_ratio_volume across all latest snapshots
  const globalPC = (() => {
    const ratios = Array.from(latestByTicker.values())
      .map((s) => (s.put_call_ratio_volume != null ? Number(s.put_call_ratio_volume) : null))
      .filter((v): v is number => v !== null && !isNaN(v));
    if (ratios.length === 0) return null;
    const avg = ratios.reduce((a, b) => a + b, 0) / ratios.length;
    const label = avg < 0.7 ? "Alcista" : avg > 1.0 ? "Bajista" : "Neutral";
    const color = avg < 0.7 ? "text-emerald-600" : avg > 1.0 ? "text-red-600" : "text-amber-500";
    return { avg, label, color, count: ratios.length };
  })();

  // Portfolio tab: split into positions with/without options (hidden excluded entirely)
  const visiblePositions = positions.filter((p) => !hiddenTickers.has((p.ticker || p.isin).toUpperCase()));
  const mainPositions = visiblePositions.filter((p) => !noOptionsTickers.has((p.ticker || p.isin).toUpperCase()));
  const noOptPositions = visiblePositions.filter((p) => noOptionsTickers.has((p.ticker || p.isin).toUpperCase()));

  // Get alerts/snapshots/unusual for a specific ticker
  function getTickerAlerts(ticker: string) {
    return alerts.filter((a) => a.ticker === ticker && !a.acknowledged);
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

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Activity className="h-6 w-6" />
            Options Monitor
          </h1>
          <p className="text-muted-foreground">
            Análisis de opciones en tiempo real sobre tu cartera
          </p>
        </div>
        <div className="flex items-center gap-3">
          <QuickNav current="/options" />
          <Button variant="outline" size="sm" onClick={handleRunCycle} disabled={running} title="Run Cycle">
            <RefreshCw className={`h-4 w-4 ${running ? "animate-spin" : ""}`} />
          </Button>
          <Button
            variant={agentStatus?.running ? "destructive" : "default"}
            size="sm"
            onClick={handleToggleAgent}
            title={agentStatus?.running ? "Stop Auto" : "Auto"}
          >
            {agentStatus?.running ? <Square className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid gap-2 sm:gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Card>
          <div className="flex items-center justify-between px-4 py-3 sm:hidden">
            <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Posiciones</span> en cartera · {watchlist.length} en watchlist</p>
            <span className="ml-3 shrink-0 text-base font-bold">{positions.length}</span>
          </div>
          <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
            <CardTitle className="text-sm font-medium">Posiciones</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="hidden sm:block">
            <div className="text-2xl font-bold">{positions.length}</div>
            <p className="text-xs text-muted-foreground">en cartera · {watchlist.length} en watchlist</p>
          </CardContent>
        </Card>
        <Card>
          <div className="flex items-center justify-between px-4 py-3 sm:hidden">
            <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Ciclos</span>{" "}{agentStatus?.last_cycle ? `último ${new Date(agentStatus.last_cycle).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}` : "sin ciclos aún"}</p>
            <span className="ml-3 shrink-0 text-base font-bold">{agentStatus?.total_cycles ?? 0}</span>
          </div>
          <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
            <CardTitle className="text-sm font-medium">Ciclos</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="hidden sm:block">
            <div className="text-2xl font-bold">{agentStatus?.total_cycles ?? 0}</div>
            <p className="text-xs text-muted-foreground">{agentStatus?.last_cycle ? `Último: ${new Date(agentStatus.last_cycle).toLocaleString("es-ES")}` : "Sin ciclos aún"}</p>
          </CardContent>
        </Card>
        <Card>
          <div className="flex items-center justify-between px-4 py-3 sm:hidden">
            <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Alertas</span> {alerts.length} total (7d)</p>
            <span className="ml-3 shrink-0 text-base font-bold">{unreadAlerts.length}</span>
          </div>
          <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
            <CardTitle className="text-sm font-medium">Alertas</CardTitle>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="hidden sm:block">
            <div className="text-2xl font-bold">{unreadAlerts.length}</div>
            <p className="text-xs text-muted-foreground">{alerts.length} total (7d)</p>
          </CardContent>
        </Card>
        <Card>
          <div className="flex items-center justify-between px-4 py-3 sm:hidden">
            <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Smart Money</span> actividad inusual (7d)</p>
            <span className="ml-3 shrink-0 text-base font-bold">{unusual.length}</span>
          </div>
          <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
            <CardTitle className="text-sm font-medium">Smart Money</CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="hidden sm:block">
            <div className="text-2xl font-bold">{unusual.length}</div>
            <p className="text-xs text-muted-foreground">Actividad inusual (7d)</p>
          </CardContent>
        </Card>
        <Card>
          <div className="flex items-center justify-between px-4 py-3 sm:hidden">
            <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Sentimiento</span> P/C {globalPC ? `${globalPC.avg.toFixed(2)} · ${globalPC.count} tickers` : "—"}</p>
            <span className={`ml-3 shrink-0 text-base font-bold ${globalPC?.color ?? "text-muted-foreground"}`}>{globalPC?.label ?? "—"}</span>
          </div>
          <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
            <CardTitle className="text-sm font-medium">Sentimiento P/C</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="hidden sm:block">
            {globalPC ? (
              <>
                <div className={`text-2xl font-bold ${globalPC.color}`}>{globalPC.label}</div>
                <p className="text-xs text-muted-foreground">P/C medio {globalPC.avg.toFixed(2)} · {globalPC.count} tickers</p>
              </>
            ) : (
              <>
                <div className="text-2xl font-bold text-muted-foreground">—</div>
                <p className="text-xs text-muted-foreground">Sin datos aún</p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="w-full overflow-x-auto">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="portfolio">
            <BarChart3 className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">Cartera</span>
          </TabsTrigger>
          <TabsTrigger value="watchlist">
            <Eye className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">Watchlist</span>
          </TabsTrigger>
          <TabsTrigger value="monitor">
            <Bell className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">Monitor</span>
            {unreadAlerts.length > 0 && (
              <Badge variant="destructive" className="ml-1 px-1.5 py-0.5 text-xs">
                {unreadAlerts.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="backtest" onClick={() => { if (!backtestStats) loadBacktest(); }}>
            <FlaskConical className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">Backtesting</span>
          </TabsTrigger>
          <TabsTrigger value="ia">
            <Sparkles className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">IA</span>
          </TabsTrigger>
        </TabsList>
        </div>

        {/* ── Portfolio / Positions Tab ── */}
        <TabsContent value="portfolio" className="space-y-4">
          {loadingPositions ? (
            <div className="flex min-h-[30vh] items-center justify-center">
              <LoadingDots text="Obteniendo precios de mercado" />
            </div>
          ) : errorPositions ? (
            <Card>
              <CardContent className="py-10 text-center space-y-3">
                <AlertCircle className="mx-auto h-8 w-8 text-destructive" />
                <p className="text-sm text-muted-foreground">{errorPositions}</p>
                <Button variant="outline" size="sm" onClick={() => setRetryPositions((k) => k + 1)}>
                  Reintentar
                </Button>
              </CardContent>
            </Card>
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
                <CardTitle>Posiciones ({mainPositions.length})</CardTitle>
                <CardDescription>
                  Pulsa en una posición para ver sus datos de opciones
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                {/* Mobile */}
                <div className="divide-y sm:hidden">
                  {mainPositions.map((p) => {
                    const ticker = (p.ticker || p.isin || "").toUpperCase();
                    const tickerAlerts = getTickerAlerts(ticker);
                    const snap = latestByTicker.get(ticker);
                    const sentiment = sentimentLabel(snap);
                    const ivHv = ivHvLabel(snap);
                    return (
                      <div
                        key={`${p.isin}-${p.broker}-card`}
                        className="flex cursor-pointer flex-col gap-2 p-3 hover:bg-muted/50"
                        onClick={() => openInstrument(ticker, { tab: "opciones", name: p.name })}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{ticker}</span>
                            {tickerAlerts.length > 0 && (
                              <Badge variant="destructive" className="px-1 py-0 text-[10px]">
                                {tickerAlerts.length}
                              </Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-0.5">
                            {watchlistTickers.has(ticker) ? (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 w-7 p-0"
                                title="Eliminar de watchlist"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRemoveFromCartera(ticker);
                                }}
                              >
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            ) : (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 w-7 p-0"
                                title="Añadir a watchlist"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleAddPositionToWatchlist(ticker, p.name);
                                }}
                              >
                                <Eye className="h-4 w-4 text-muted-foreground" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0"
                              title="Ocultar del monitor de opciones"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleHidePosition(ticker);
                              }}
                            >
                              <EyeOff className="h-4 w-4 text-muted-foreground" />
                            </Button>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                          <span>
                            Sentimiento <strong className={sentiment.className}>{sentiment.label}</strong>
                          </span>
                          <span>
                            P/C{" "}
                            <strong className="text-foreground">
                              {snap?.put_call_ratio_volume != null ? fmt(snap.put_call_ratio_volume) : "—"}
                            </strong>
                          </span>
                          <span className="flex items-center gap-1">
                            IV/HV <Badge variant={ivHv.variant} className="text-[10px]">{ivHv.label}</Badge>
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
                {/* Desktop */}
                <Table className="hidden sm:table">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8" />
                      <TableHead>Ticker</TableHead>
                      <TableHead className="text-right">Sentimiento</TableHead>
                      <TableHead className="text-right">P/C Ratio</TableHead>
                      <TableHead className="text-right">IV vs HV</TableHead>
                      <TableHead className="w-16" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {mainPositions.map((p) => {
                      const ticker = (p.ticker || p.isin || "").toUpperCase();
                      const tickerAlerts = getTickerAlerts(ticker);
                      const snap = latestByTicker.get(ticker);
                      const sentiment = sentimentLabel(snap);
                      const ivHv = ivHvLabel(snap);

                      return (
                        <Fragment key={`${p.isin}-${p.broker}`}>
                          <TableRow
                            className="cursor-pointer hover:bg-muted/50"
                            onClick={() =>
                              openInstrument(ticker, { tab: "opciones", name: p.name })
                            }
                          >
                            <TableCell className="w-8 pr-0">
                              <ChevronRight className="h-4 w-4 text-muted-foreground" />
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
                            <TableCell className="text-center">
                              <div className="flex items-center justify-center gap-0.5">
                                {watchlistTickers.has(ticker) ? (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 w-7 p-0"
                                    title="Eliminar de watchlist"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleRemoveFromCartera(ticker);
                                    }}
                                  >
                                    <Trash2 className="h-4 w-4 text-destructive" />
                                  </Button>
                                ) : (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 w-7 p-0"
                                    title="Añadir a watchlist"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleAddPositionToWatchlist(ticker, p.name);
                                    }}
                                  >
                                    <Eye className="h-4 w-4 text-muted-foreground" />
                                  </Button>
                                )}
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 w-7 p-0"
                                  title="Ocultar del monitor de opciones"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleHidePosition(ticker);
                                  }}
                                >
                                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>

                        </Fragment>
                      );
                    })}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
          {noOptPositions.length > 0 && (
            <p className="px-1 text-sm text-muted-foreground">
              Los siguientes tickers no se muestran en posiciones ya que no
              tienen opciones disponibles en los mercados:{" "}
              <span className="font-medium">
                {noOptPositions.map((p) => p.ticker || p.isin).join(", ")}
              </span>
              .
            </p>
          )}
        </TabsContent>

        {/* ── Watchlist Tab ── */}
        <TabsContent value="watchlist" className="space-y-4">
          {loadingOptions ? (
            <div className="flex min-h-[30vh] items-center justify-center">
              <LoadingDots text="Cargando watchlist" />
            </div>
          ) : errorOptions ? (
            <Card>
              <CardContent className="py-10 text-center space-y-3">
                <AlertCircle className="mx-auto h-8 w-8 text-destructive" />
                <p className="text-sm text-muted-foreground">{errorOptions}</p>
                <Button variant="outline" size="sm" onClick={() => setRetryOptions((k) => k + 1)}>
                  Reintentar
                </Button>
              </CardContent>
            </Card>
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
                          onClick={() =>
                            api.options.addToWatchlist(ticker, name).then(async () => {
                              const wl = (await api.options.watchlist()) as WatchlistItem[];
                              setWatchlist(wl);
                            })
                          }
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

                {/* Mobile */}
                <div className="divide-y sm:hidden">
                  {watchlist.length === 0 ? (
                    <p className="p-4 text-center text-sm text-muted-foreground">
                      Sin tickers en la watchlist
                    </p>
                  ) : (
                    watchlist.map((w) => (
                      <div key={w.id} className="flex flex-col gap-2 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <span className="font-medium">{w.ticker}</span>
                            <span className="ml-2 text-sm text-muted-foreground">
                              {w.name || "—"}
                            </span>
                          </div>
                          <Badge variant={w.enabled ? "default" : "secondary"}>
                            {w.enabled ? "Activo" : "Pausado"}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>Añadido {new Date(w.created_at).toLocaleDateString("es-ES")}</span>
                          <div className="flex gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 text-xs"
                              onClick={() =>
                                api.options.toggleWatchlistItem(w.id).then(() =>
                                  setWatchlist((prev) =>
                                    prev.map((item) =>
                                      item.id === w.id
                                        ? { ...item, enabled: !item.enabled }
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
                              className="h-7 text-xs text-destructive"
                              onClick={() => handleRemoveTicker(w.id, w.ticker)}
                            >
                              Eliminar
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
                {/* Desktop */}
                <Table className="hidden sm:table">
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
                              onClick={() => handleRemoveTicker(w.id, w.ticker)}
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

        {/* ── Monitor Tab (Alertas + Smart Money) ── */}
        <TabsContent value="monitor" className="space-y-4">
          {loadingOptions ? (
            <div className="flex min-h-[30vh] items-center justify-center">
              <LoadingDots text="Cargando monitor" />
            </div>
          ) : errorOptions ? (
            <Card>
              <CardContent className="py-10 text-center space-y-3">
                <AlertCircle className="mx-auto h-8 w-8 text-destructive" />
                <p className="text-sm text-muted-foreground">{errorOptions}</p>
                <Button variant="outline" size="sm" onClick={() => setRetryOptions((k) => k + 1)}>
                  Reintentar
                </Button>
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2">
                <div className="flex gap-2">
                  <Button
                    variant={monitorFilter === "alerts" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setMonitorFilter("alerts")}
                  >
                    <Bell className="mr-1.5 h-3.5 w-3.5" />
                    Alertas
                    {unreadAlerts.length > 0 && (
                      <Badge variant="destructive" className="ml-1.5 px-1.5 py-0.5 text-xs">
                        {unreadAlerts.length}
                      </Badge>
                    )}
                  </Button>
                  <Button
                    variant={monitorFilter === "unusual" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setMonitorFilter("unusual")}
                  >
                    <Zap className="mr-1.5 h-3.5 w-3.5" />
                    <span className="hidden sm:inline">Smart Money</span>
                    <span className="sm:hidden">Smart $</span>
                    {unusual.length > 0 && (
                      <span className="ml-1.5 text-xs opacity-70">{unusual.length}</span>
                    )}
                  </Button>
                </div>
                {monitorFilter === "alerts" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleAckAll}
                    disabled={unreadAlerts.length === 0}
                  >
                    <span className="hidden sm:inline">Marcar todas leídas</span>
                    <span className="sm:hidden">Leídas</span>
                  </Button>
                )}
              </div>

              {monitorFilter === "alerts" && (
                <Card>
                  <CardContent className="p-0">
                    {alerts.length === 0 ? (
                      <p className="p-4 text-center text-sm text-muted-foreground">Sin alertas aún</p>
                    ) : (
                      <>
                        {/* Mobile */}
                        <div className="divide-y sm:hidden">
                          {alerts.map((a) => (
                            <div key={a.id} className={`flex flex-col gap-1 p-3 ${a.acknowledged ? "opacity-50" : ""}`}>
                              <div className="flex flex-wrap items-center gap-2">
                                <span
                                  className="font-medium cursor-pointer text-primary hover:underline"
                                  onClick={() => openInstrument(a.ticker, { tab: "opciones" })}
                                >
                                  {a.ticker}
                                </span>
                                <Badge variant="outline" className="text-xs">{a.alert_type}</Badge>
                                <Badge variant={severityColor(a.severity) as "destructive" | "secondary" | "outline"} className="text-xs">{a.severity}</Badge>
                                <AlignmentTag alignment={a.regime_alignment} />
                                <span className="ml-auto text-xs text-muted-foreground">
                                  {new Date(a.timestamp).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}
                                </span>
                              </div>
                              <p className="text-sm text-muted-foreground">{a.message}</p>
                              {!a.acknowledged && (
                                <Button variant="ghost" size="sm" className="self-end h-7 text-xs" onClick={() => handleAckAlert(a.id)}>Ack</Button>
                              )}
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
                              <TableHead>Mensaje</TableHead>
                              <TableHead>Severidad</TableHead>
                              <TableHead className="text-right">Acción</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {alerts.map((a) => (
                              <TableRow key={a.id} className={a.acknowledged ? "opacity-50" : ""}>
                                <TableCell className="text-xs">{new Date(a.timestamp).toLocaleString("es-ES")}</TableCell>
                                <TableCell className="font-medium cursor-pointer text-primary hover:underline" title="Ver opciones" onClick={() => openInstrument(a.ticker, { tab: "opciones" })}>{a.ticker}</TableCell>
                                <TableCell><Badge variant="outline">{a.alert_type}</Badge></TableCell>
                                <TableCell>{a.message}</TableCell>
                                <TableCell><div className="flex items-center gap-1"><Badge variant={severityColor(a.severity) as "destructive" | "secondary" | "outline"}>{a.severity}</Badge><AlignmentTag alignment={a.regime_alignment} /></div></TableCell>
                                <TableCell className="text-right">
                                  {!a.acknowledged && <Button variant="ghost" size="sm" onClick={() => handleAckAlert(a.id)}>Ack</Button>}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </>
                    )}
                  </CardContent>
                </Card>
              )}

              {monitorFilter === "unusual" && (
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
                                <TableCell className="text-xs">{new Date(u.timestamp).toLocaleString("es-ES")}</TableCell>
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
              )}
            </>
          )}
        </TabsContent>
        {/* ── Backtesting Tab ── */}
        <TabsContent value="backtest" className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-lg font-semibold">Backtesting de señales</h3>
              <p className="text-sm text-muted-foreground">Precisión histórica de las alertas a +1D / +3D / +7D</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={loadBacktest} disabled={loadingBacktest}>
                <RefreshCw className={`mr-2 h-4 w-4 ${loadingBacktest ? "animate-spin" : ""}`} />
                Actualizar
              </Button>
              <Button variant="outline" size="sm" onClick={handleEvaluate} disabled={evaluating}>
                <Target className={`mr-2 h-4 w-4 ${evaluating ? "animate-spin" : ""}`} />
                <span className="sm:hidden">Evaluar</span>
                <span className="hidden sm:inline">Evaluar pendientes</span>
              </Button>
            </div>
          </div>

          {loadingBacktest ? (
            <div className="flex min-h-[20vh] items-center justify-center">
              <LoadingDots text="Cargando backtesting" />
            </div>
          ) : !backtestStats ? (
            <Card>
              <CardContent className="py-10 text-center text-muted-foreground">
                <FlaskConical className="mx-auto mb-3 h-8 w-8 opacity-40" />
                <p>Abre esta pestaña para cargar los datos de backtesting.</p>
                <Button className="mt-4" size="sm" onClick={loadBacktest}>Cargar</Button>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Accuracy stats by horizon */}
              <div className="grid gap-4 sm:grid-cols-3">
                {(["1d", "3d", "7d"] as const).map((h) => {
                  const s = backtestStats.by_horizon[h];
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
              {Object.keys(backtestStats.by_signal_type).length > 0 && (() => {
                const signalChartData = Object.entries(backtestStats.by_signal_type).map(
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
                      {Object.entries(backtestStats.by_signal_type).map(([type, v]) => {
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
                          {Object.entries(backtestStats.by_signal_type).map(([type, v]) => {
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
              {backtestStats.by_alignment &&
                Object.keys(backtestStats.by_alignment).length > 0 && (
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
                        .filter((k) => backtestStats.by_alignment?.[k])
                        .map((k) => {
                          const v = backtestStats.by_alignment![k];
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
                            .filter((k) => backtestStats.by_alignment?.[k])
                            .map((k) => {
                              const v = backtestStats.by_alignment![k];
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
                  <CardDescription>{backtestSignals.length} señales registradas</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  {backtestSignals.length === 0 ? (
                    <div className="py-8 text-center text-muted-foreground">
                      Sin señales registradas. Ejecuta un ciclo del agente para empezar a acumular datos.
                    </div>
                  ) : (
                    <>
                      {/* Mobile: vertical cards */}
                      <div className="flex flex-col divide-y sm:hidden">
                        {backtestSignals.map((s) => (
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
                            {backtestSignals.map((s) => (
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

        {/* ── IA Tab (Análisis + Agente) ── */}
        <TabsContent value="ia">
          <Tabs defaultValue="informe">
            <TabsList className="mb-4">
              <TabsTrigger value="informe">
                <Sparkles className="mr-1 h-3.5 w-3.5" /> Informe
              </TabsTrigger>
              <TabsTrigger value="chat">
                <MessageSquare className="mr-1 h-3.5 w-3.5" /> Chat
              </TabsTrigger>
            </TabsList>
            <TabsContent value="informe">
              <AnalysisTab key={analysisCycle} />
            </TabsContent>
            <TabsContent value="chat">
              <AgentChat />
            </TabsContent>
          </Tabs>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Agent Chat component ─────────────────────────────────────────────────────

type ChatMsg = { role: "user" | "assistant"; content: string };

function AgentChat() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage() {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    setError(null);
    const nextMessages: ChatMsg[] = [...messages, { role: "user", content: q }];
    setMessages(nextMessages);
    setLoading(true);
    try {
      const { answer } = await api.options.ask(
        q,
        messages.map((m) => ({ role: m.role, content: m.content })),
      );
      setMessages((prev) => [...prev, { role: "assistant", content: answer }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="flex flex-col" style={{ height: "65vh" }}>
      <CardHeader className="border-b pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageSquare className="h-4 w-4" />
          Agente de opciones
        </CardTitle>
        <CardDescription className="text-xs">
          Pregunta sobre tus posiciones, alertas activas o señales de mercado.
          El contexto se construye con los datos más recientes del agente.
        </CardDescription>
      </CardHeader>

      {/* Messages */}
      <CardContent className="flex-1 overflow-y-auto space-y-3 py-4">
        {messages.length === 0 && (
          <p className="text-center text-sm text-muted-foreground py-8">
            Empieza con una pregunta — p.ej. &ldquo;¿Qué ticker tiene la IV más alta?&rdquo;
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${
              m.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-[80%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-xl bg-muted px-3 py-2 text-sm text-muted-foreground">
              Analizando...
            </div>
          </div>
        )}
        {error && (
          <div className="flex justify-center">
            <p className="text-xs text-destructive">{error}</p>
          </div>
        )}
        <div ref={bottomRef} />
      </CardContent>

      {/* Input */}
      <div className="border-t p-3 flex gap-2">
        <input
          className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          placeholder="Escribe tu pregunta..."
          value={input}
          disabled={loading}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          }}
        />
        <Button size="sm" disabled={loading || !input.trim()} onClick={sendMessage}>
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </Card>
  );
}

// ── Analysis Tab component ────────────────────────────────────────────────────

type LastAnalysis = {
  timestamp: string | null;
  cycle: number | null;
  tickers_analyzed: number | null;
  alerts: number | null;
  unusual: number | null;
  market_sentiment: string | null;
  claude_analysis: string | null;
  ai_configured: boolean;
  macro: {
    regime: string;
    vix: number | null;
    yield_spread: number | null;
    financial_stress: number | null;
    hy_spread: number | null;
    as_of: string | null;
  } | null;
};

/** Macro-regime annotation badge (FRED). Annotation only — does not affect signals. */
function MacroBadge({ macro }: { macro: LastAnalysis["macro"] }) {
  if (!macro) return null;
  const label =
    macro.regime === "risk_off"
      ? "Risk-off"
      : macro.regime === "risk_on"
        ? "Risk-on"
        : "Neutral";
  const color =
    macro.regime === "risk_off"
      ? "bg-red-500/10 text-red-600 border-red-500/20"
      : macro.regime === "risk_on"
        ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
        : "bg-muted text-muted-foreground border-border";
  const fmt = (v: number | null, suffix = "") =>
    v == null ? "n/d" : `${v.toFixed(2)}${suffix}`;
  const title =
    `Régimen macro (FRED${macro.as_of ? `, ${macro.as_of}` : ""}) — ` +
    `VIX ${fmt(macro.vix)} · Curva 10a-2a ${fmt(macro.yield_spread, "%")} · ` +
    `Estrés ${fmt(macro.financial_stress)} · HY ${fmt(macro.hy_spread, "%")}`;
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${color}`}
    >
      Macro: {label}
      <span className="text-muted-foreground font-normal">VIX {fmt(macro.vix)}</span>
    </span>
  );
}

/** Macro-regime alignment tag for an alert (Phase 2b, informational only). */
function AlignmentTag({ alignment }: { alignment?: string | null }) {
  if (!alignment || alignment === "neutral") return null;
  const aligned = alignment === "aligned";
  const color = aligned
    ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
    : "bg-amber-500/10 text-amber-600 border-amber-500/20";
  return (
    <Badge
      variant="outline"
      className={`text-xs ${color}`}
      title={
        aligned
          ? "A favor del régimen macro (informativo — no cambia la señal)"
          : "En contra del régimen macro (informativo — no cambia la señal)"
      }
    >
      {aligned ? "macro ✓" : "macro ✗"}
    </Badge>
  );
}

/** Parse a Markdown string with "## N. Title\n..." into [{title, body}] sections. */
function parseAnalysisSections(text: string): { title: string; body: string }[] {
  const parts = text.split(/(?=^## \d+\.)/m);
  return parts
    .map((part) => {
      const firstNewline = part.indexOf("\n");
      if (firstNewline === -1) return null;
      const title = part.slice(0, firstNewline).replace(/^##\s*/, "").trim();
      const body = part.slice(firstNewline + 1).trim();
      return { title, body };
    })
    .filter(Boolean) as { title: string; body: string }[];
}

function AnalysisTab() {
  const [analysis, setAnalysis] = useState<LastAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.options
      .lastAnalysis()
      .then((data) => setAnalysis(data))
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Error cargando análisis")
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-3 p-4">
        {new Array(4).fill(null).map((_: null, i: number) => (
          <Skeleton key={`skel-${i}`} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Card className="p-6 text-center">
        <p className="text-sm text-destructive">{error}</p>
      </Card>
    );
  }

  if (!analysis?.claude_analysis) {
    const hasRun = analysis?.cycle != null;
    const configured = analysis?.ai_configured ?? false;
    return (
      <Card className="p-6 text-center space-y-2">
        {analysis?.macro && (
          <div className="flex justify-center pb-1">
            <MacroBadge macro={analysis.macro} />
          </div>
        )}
        {!hasRun && (
          <p className="text-sm text-muted-foreground">
            No hay análisis disponible. Ejecuta un ciclo del agente para generar el informe.
          </p>
        )}
        {hasRun && !configured && (
          <p className="text-sm text-destructive font-medium">
            API key no configurada. Establece <code className="text-xs bg-muted px-1 rounded">FINVIEW_OPENROUTER_API_KEY</code> en las variables de entorno del servidor.
          </p>
        )}
        {hasRun && configured && (
          <p className="text-sm text-muted-foreground">
            Ciclo #{analysis!.cycle} completado ({analysis!.alerts ?? 0} alertas) — el análisis IA falló o no hubo alertas.
          </p>
        )}
        {hasRun && configured && (analysis!.alerts ?? 0) === 0 && (
          <p className="text-xs text-muted-foreground">
            El análisis sólo se genera cuando el ciclo produce alertas. Añade tickers activos al watchlist.
          </p>
        )}
      </Card>
    );
  }

  const sections = parseAnalysisSections(analysis.claude_analysis);
  let sentimentColor = "text-muted-foreground";
  if (analysis.market_sentiment === "alcista") sentimentColor = "text-emerald-600";
  else if (analysis.market_sentiment === "bajista") sentimentColor = "text-red-500";

  return (
    <div className="space-y-4">
      {/* Meta header */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">Informe VolatilityEdge</CardTitle>
                <MacroBadge macro={analysis.macro} />
              </div>
              <CardDescription>
                {analysis.timestamp
                  ? `Ciclo #${analysis.cycle ?? "—"} · ${new Date(analysis.timestamp).toLocaleString("es-ES")}`
                  : "Fecha desconocida"}
              </CardDescription>
            </div>
            <div className="flex gap-4 text-sm">
              <span>
                <span className="text-muted-foreground">Tickers: </span>
                <span className="font-medium">{analysis.tickers_analyzed ?? "—"}</span>
              </span>
              <span>
                <span className="text-muted-foreground">Alertas: </span>
                <span className="font-medium">{analysis.alerts ?? "—"}</span>
              </span>
              <span>
                <span className="text-muted-foreground">Sentimiento: </span>
                <span className={`font-medium capitalize ${sentimentColor}`}>
                  {analysis.market_sentiment ?? "—"}
                </span>
              </span>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Sections */}
      {sections.map(({ title, body }) => (
        <Card key={title}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">{title}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm text-foreground/90 leading-relaxed">
              {body}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
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
