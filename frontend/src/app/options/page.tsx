"use client";

import Link from "next/link";
import { Fragment, useEffect, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  FlaskConical,
  Globe,
  MessageSquare,
  Pause,
  Play,
  Sparkles,
  Square,
  RefreshCw,
  Target,
  Trash2,
  TrendingUp,
  Zap,
  AlertCircle,
} from "lucide-react";

import { api, type TechnicalSignal } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";

import { AgentChat } from "./AgentChat";
import { AnalysisTab } from "./AnalysisTab";
import { BacktestTab } from "./BacktestTab";
import { AlignmentTag, BreakProbability, DirBadge, severityColor } from "./badges";
import { fmt, fmtDateTime } from "@/lib/format";
import { useBacktest } from "./useBacktest";
import { selectPositionsToSync } from "@/lib/optionsWatchlistSync";
import { buildWatchlistRows } from "@/lib/optionsWatchlistRows";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import { LoadingDots } from "@/components/loading-dots";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { QuickNav } from "@/components/QuickNav";
import { HeaderActions } from "@/components/HeaderActions";
import { usePrivacyToggle } from "@/hooks/use-privacy-toggle";
import { OpcionesTab } from "@/components/instrument/OpcionesTab";

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

interface AgentStatus {
  running: boolean;
  external_scheduler: boolean;
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
  const { privacy, togglePrivacy } = usePrivacyToggle();
  const backtest = useBacktest();
  const [positions, setPositions] = useState<Position[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [unusual, setUnusual] = useState<Unusual[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  // Zonas (técnico) lens state for cross-section toggles: ticker → zonas item id
  const [zonasMap, setZonasMap] = useState<Map<string, number>>(new Map());
  const [zonasBusy, setZonasBusy] = useState<Set<string>>(new Set());
  // Tickers with an active geo signal — gates the per-alert "Ideas" link.
  const [geoTickers, setGeoTickers] = useState<Set<string>>(new Set());
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [running, setRunning] = useState(false);
  const [newTicker, setNewTicker] = useState("");
  const [hiddenTickers, setHiddenTickers] = useState<Set<string>>(new Set());
  const [noOptionsTickers, setNoOptionsTickers] = useState<Set<string>>(new Set());
  const [availabilityChecked, setAvailabilityChecked] = useState(false);
  const [analysisCycle, setAnalysisCycle] = useState(0);
  const [monitorFilter, setMonitorFilter] = useState<"alerts" | "unusual" | "technical">("alerts");
  const [techSignals, setTechSignals] = useState<TechnicalSignal[]>([]);
  const [activeTab, setActiveTab] = useState("watchlist");
  // Mobile-only: tapping a Posiciones card expands inline (like Cartera)
  // instead of opening the drawer; the drawer stays one tap away via its own
  // button inside the expanded card.
  const [expandedOptionsTicker, setExpandedOptionsTicker] = useState<string | null>(null);
  const [errorPositions, setErrorPositions] = useState<string | null>(null);
  const [errorOptions, setErrorOptions] = useState<string | null>(null);
  const [retryPositions] = useState(0);
  const [retryOptions, setRetryOptions] = useState(0);
  // The error banner clears when the user retries, not when the effect
  // re-runs: the reset belongs to the event, the fetch to the effect.
  function retryOptionsLoad() {
    setErrorOptions(null);
    setRetryOptions((k) => k + 1);
  }

  // N6: auto-expand ticker from URL param (?ticker=X)
  const initialTickerRef = useRef<string | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    initialTickerRef.current = params.get("ticker");
  }, []);

  // Zonas lens info for the watchlist's "Técnico" toggles — best-effort
  useEffect(() => {
    api.zonasClav
      .watchlist()
      .then((items) => setZonasMap(new Map(items.map((i) => [i.ticker, i.id]))))
      .catch(bestEffort("zonas lens map for the watchlist"));
  }, []);

  // Which tickers have an active geo signal — decides whether an alert offers an
  // "Ideas" link at all. Navigation metadata only: no thesis content crosses into
  // this page. Best-effort; without it the links just don't render.
  useEffect(() => {
    api.geo
      .signals("active")
      .then((sigs) => {
        const withSignal = new Set<string>();
        for (const s of sigs) {
          for (const t of s.tickers) withSignal.add(t.symbol.toUpperCase());
        }
        setGeoTickers(withSignal);
      })
      .catch(bestEffort("geo signals for the Ideas links"));
  }, []);

  // Technical (zone-break) signals. These come from Zonas Clave, the trigger
  // layer — they belong in the Monitor because acting on a trigger is what this
  // page is for. Best-effort: the options alerts stand on their own without them.
  useEffect(() => {
    api.zonasClav
      .signals()
      .then(setTechSignals)
      .catch(bestEffort("technical signals panel"));
  }, [retryOptions]);

  // Load portfolio positions with skip_prices=true — no yfinance calls, instant response
  useEffect(() => {
    api.portfolio
      .positions(true)
      .then(async (pos) => {
        const loaded = pos as Position[];
        setPositions(loaded);
        if (loaded.length === 0) return;
        const tickers = [...new Set(loaded.map((p) => (p.ticker || p.isin).toUpperCase()))];
        try {
          const { no_options } = await api.options.checkAvailability(tickers);
          setNoOptionsTickers(new Set(no_options));
        } catch (e) {
          // Positions remain visible if the check fails.
          bestEffort("options availability check")(e);
        }
      })
      .catch((e) => {
        console.error("Failed to load positions:", e);
        setErrorPositions("No se pudieron cargar las posiciones de cartera.");
      })
      .finally(() => setAvailabilityChecked(true));
  }, [retryPositions]);

  // Load options data in parallel (independent of positions)
  useEffect(() => {
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

  // Auto-expand the ticker from ?ticker= (Geo-Intel and Zonas Clave deep-link
  // here). Keyed off the watchlist, not the portfolio: the list is watchlist-
  // driven, and the tickers linked from elsewhere are often not held.
  useEffect(() => {
    const hint = initialTickerRef.current;
    if (!hint || watchlist.length === 0) return;
    initialTickerRef.current = null;
    const upper = hint.toUpperCase();
    if (watchlist.some((w) => w.ticker === upper)) setExpandedOptionsTicker(upper);
  }, [watchlist]);

  // Auto-sync: portfolio positions get added to the options watchlist so
  // Sentimiento/P-C Ratio/IV vs HV populate without a manual click. Waits for
  // the availability check (so we skip tickers with no options chain).
  // `watchlist` is intentionally NOT a dependency: it changes every time this
  // effect adds something (and whenever the user removes a ticker via the
  // Trash2 button), which would otherwise immediately re-add anything the
  // user just removed. Instead, `syncedTickersRef` remembers every ticker
  // this effect has ever seen on the watchlist (added by it or already
  // there), so a manual removal sticks — the effect only re-fires when the
  // portfolio itself changes. The current list is read through
  // `watchlistRef`, kept in sync by the effect above it, so the effect sees
  // the latest value without depending on it.
  const syncedTickersRef = useRef<Set<string>>(new Set());
  const watchlistRef = useRef(watchlist);
  useEffect(() => {
    watchlistRef.current = watchlist;
  }, [watchlist]);
  useEffect(() => {
    if (!availabilityChecked || loadingOptions || positions.length === 0) return;
    const watchlistSet = new Set(watchlistRef.current.map((w) => w.ticker));
    for (const ticker of watchlistSet) syncedTickersRef.current.add(ticker);
    const toAdd = selectPositionsToSync(
      positions,
      watchlistSet,
      hiddenTickers,
      noOptionsTickers,
      syncedTickersRef.current,
    );
    if (toAdd.size === 0) return;
    let cancelled = false;
    (async () => {
      for (const { ticker, name } of toAdd.values()) {
        if (cancelled) return;
        try {
          await api.options.addToWatchlist(ticker, name);
          syncedTickersRef.current.add(ticker);
        } catch (e) {
          // E.g. already added by a concurrent sync; settles on the next pass.
          bestEffort(`options watchlist sync ${ticker}`)(e);
        }
      }
      if (cancelled) return;
      const wl = (await api.options.watchlist()) as WatchlistItem[];
      if (!cancelled) setWatchlist(wl);
    })();
    return () => {
      cancelled = true;
    };
  }, [availabilityChecked, loadingOptions, positions, hiddenTickers, noOptionsTickers]);

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
      const before = agentStatus?.total_cycles ?? 0;
      const result = await api.options.runCycle();
      // Local mode returns immediately and needs polling. Cloud Run returns
      // only after the request-scoped cycle has completed.
      if (result.status === "started") {
        for (let attempt = 0; attempt < 100; attempt++) {
          await new Promise((resolve) => setTimeout(resolve, 3000));
          const status = (await api.options.agentStatus()) as AgentStatus;
          setAgentStatus(status);
          if (status.total_cycles > before) break;
        }
      }
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

  async function handleHidePosition(ticker: string) {
    // Remove from watchlist if present
    const item = watchlist.find((w) => w.ticker === ticker);
    if (item) await handleRemoveTicker(item.id, ticker);
    // Persist exclusion from options monitor
    await api.options.hidePortfolioTicker(ticker);
    setHiddenTickers((prev) => new Set([...prev, ticker]));
  }

  async function handleToggleWatchlistItem(id: number) {
    await api.options.toggleWatchlistItem(id);
    setWatchlist((prev) =>
      prev.map((item) => (item.id === id ? { ...item, enabled: !item.enabled } : item)),
    );
  }

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
        onClick={() => handleHidePosition(w.ticker)}
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
        onClick={() => handleRemoveTicker(w.id, w.ticker)}
      >
        <Trash2 className="mr-1 h-4 w-4" />
        Eliminar
      </Button>
    );

  // ── Zonas (técnico) lens — cross-section toggle from the watchlist ──
  async function toggleZonasLens(ticker: string, name: string) {
    if (zonasBusy.has(ticker)) return;
    setZonasBusy((prev) => new Set(prev).add(ticker));
    try {
      const id = zonasMap.get(ticker);
      if (id != null) {
        await api.zonasClav.removeTicker(id);
      } else {
        // Same semantics as adding from /zonas-clave: fires the S/R analysis.
        await api.zonasClav.addTicker(ticker, name);
      }
      const items = await api.zonasClav.watchlist();
      setZonasMap(new Map(items.map((i) => [i.ticker, i.id])));
    } catch (e) {
      console.error("zonas lens toggle:", e);
    } finally {
      setZonasBusy((prev) => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    }
  }

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
        onClick={() => toggleZonasLens(w.ticker, w.name)}
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

  // Per-alert jump-offs. An options alert says "something moved here" — acting on
  // it means seeing the chain (inline, this page) and the technical picture
  // (Zonas Clave). Ideas only shows up when that ticker actually has an active
  // geo signal: a link to an empty page is worse than no link. Links are
  // navigation, not content — no thesis or fundamentals render here.
  const renderTickerLinks = (ticker: string, expanded: boolean) => (
    <div className="flex flex-wrap items-center gap-1">
      <button
        onClick={() => setExpandedOptionsTicker(expanded ? null : ticker)}
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

  // Portfolio tickers with no options chain — surfaced as a note so their
  // absence from the list is explained rather than mysterious.
  const noOptPositions = positions.filter(
    (p) =>
      !hiddenTickers.has((p.ticker || p.isin).toUpperCase()) &&
      noOptionsTickers.has((p.ticker || p.isin).toUpperCase()),
  );

  // The unified list: one row per watchlist ticker, enriched with held lots and
  // the latest snapshot's analytics. See lib/optionsWatchlistRows.ts.
  const rows = buildWatchlistRows(watchlist, positions, hiddenTickers, noOptionsTickers).map(
    (row) => ({
      ...row,
      snap: latestByTicker.get(row.item.ticker),
      rowAlerts: getTickerAlerts(row.item.ticker),
    }),
  );
  const heldCount = rows.filter((r) => r.lots.length > 0).length;

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
    <div className="space-y-6 p-6" data-privacy={privacy ? "true" : "false"}>
      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Activity className="h-6 w-6" />
            Options Monitor
          </h1>
          <HeaderActions privacy={privacy} onTogglePrivacy={togglePrivacy} />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-muted-foreground">
            Análisis de opciones en tiempo real sobre tu cartera
          </p>
          <div className="flex items-center gap-3">
            <QuickNav current="/options" />
            <Button variant="outline" size="sm" onClick={handleRunCycle} disabled={running} title="Run Cycle">
              <RefreshCw className={`h-4 w-4 ${running ? "animate-spin" : ""}`} />
            </Button>
            <Button
              variant={agentStatus?.running ? "destructive" : "default"}
              size="sm"
              onClick={handleToggleAgent}
              disabled={agentStatus?.external_scheduler}
              title={agentStatus?.external_scheduler ? "Gestionado por Cloud Scheduler" : agentStatus?.running ? "Stop Auto" : "Auto"}
            >
              {agentStatus?.running ? <Square className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
              {agentStatus?.external_scheduler && <span>Cloud Scheduler</span>}
            </Button>
          </div>
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
            <p className="text-xs text-muted-foreground">{agentStatus?.last_cycle ? `Último: ${fmtDateTime(agentStatus.last_cycle)}` : "Sin ciclos aún"}</p>
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
          <TabsTrigger value="backtest" onClick={() => { if (!backtest.stats) backtest.load(); }}>
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
        {/* ── Watchlist Tab (portfolio positions + manually tracked tickers) ── */}
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
                <Button variant="outline" size="sm" onClick={retryOptionsLoad}>
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
                      const isExpanded = expandedOptionsTicker === w.ticker;
                      return (
                        <div key={w.id}>
                          <div
                            className="flex cursor-pointer flex-col gap-2 p-3 hover:bg-muted/50"
                            onClick={() =>
                              setExpandedOptionsTicker(isExpanded ? null : w.ticker)
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
                                  onClick={() => handleToggleWatchlistItem(w.id)}
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
                                    onClick={() => handleHidePosition(w.ticker)}
                                  >
                                    <EyeOff className="h-4 w-4 text-muted-foreground" />
                                  </Button>
                                ) : (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 w-7 p-0"
                                    title="Eliminar de la watchlist"
                                    onClick={() => handleRemoveTicker(w.id, w.ticker)}
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
                        const isExpanded = expandedOptionsTicker === w.ticker;
                        return (
                          <Fragment key={w.id}>
                            <TableRow
                              className="cursor-pointer hover:bg-muted/50"
                              onClick={() =>
                                setExpandedOptionsTicker(isExpanded ? null : w.ticker)
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
                                  onClick={() => handleToggleWatchlistItem(w.id)}
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
                <Button variant="outline" size="sm" onClick={retryOptionsLoad}>
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
                  <Button
                    variant={monitorFilter === "technical" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setMonitorFilter("technical")}
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
                          {alerts.map((a) => {
                            const tickerUp = a.ticker.toUpperCase();
                            const isAlertExpanded = expandedOptionsTicker === tickerUp;
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
                                  {renderTickerLinks(tickerUp, isAlertExpanded)}
                                  {!a.acknowledged && (
                                    <Button variant="ghost" size="sm" className="h-7 shrink-0 text-xs" onClick={() => handleAckAlert(a.id)}>Ack</Button>
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
                              const isAlertExpanded = expandedOptionsTicker === tickerUp;
                              return (
                                <Fragment key={a.id}>
                                  <TableRow className={a.acknowledged ? "opacity-50" : ""}>
                                    <TableCell className="text-xs">{fmtDateTime(a.timestamp)}</TableCell>
                                    <TableCell className="font-medium">{a.ticker}</TableCell>
                                    <TableCell><Badge variant="outline">{a.alert_type}</Badge></TableCell>
                                    <TableCell>{a.message}</TableCell>
                                    <TableCell><div className="flex items-center gap-1"><Badge variant={severityColor(a.severity) as "destructive" | "secondary" | "outline"}>{a.severity}</Badge><AlignmentTag alignment={a.regime_alignment} /></div></TableCell>
                                    <TableCell>{renderTickerLinks(tickerUp, isAlertExpanded)}</TableCell>
                                    <TableCell className="text-right">
                                      {!a.acknowledged && <Button variant="ghost" size="sm" onClick={() => handleAckAlert(a.id)}>Ack</Button>}
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
              )}

              {monitorFilter === "technical" && (
                <Card>
                  <CardContent className="p-0">
                    {sortedTechSignals.length === 0 ? (
                      <p className="p-4 text-center text-sm text-muted-foreground">
                        Sin señales técnicas. Se emiten cuando el precio de un ticker de
                        Zonas Clave se acerca a menos del 2% de una zona.
                      </p>
                    ) : (
                      <>
                        {/* Mobile */}
                        <div className="divide-y sm:hidden">
                          {sortedTechSignals.map((s) => {
                            const isExpanded = expandedOptionsTicker === s.ticker;
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
                                {renderTickerLinks(s.ticker, isExpanded)}
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
                            {sortedTechSignals.map((s) => {
                              const isExpanded = expandedOptionsTicker === s.ticker;
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
                                    <TableCell>{renderTickerLinks(s.ticker, isExpanded)}</TableCell>
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
              )}
            </>
          )}
        </TabsContent>
        {/* ── Backtesting Tab ── */}

        {/* ── IA Tab (Análisis + Agente) ── */}
        <BacktestTab backtest={backtest} />

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

