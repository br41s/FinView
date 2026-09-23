"use client";

import { useEffect, useRef, useState } from "react";
import {
  Activity,
  Bell,
  Bot,
  Eye,
  FlaskConical,
  MessageSquare,
  Sparkles,
  Square,
  RefreshCw,
} from "lucide-react";

import { api, type TechnicalSignal } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";

import { AgentChat } from "./AgentChat";
import { AnalysisTab } from "./AnalysisTab";
import { BacktestTab } from "./BacktestTab";
import { MonitorTab } from "./MonitorTab";
import { OptionsStatsCards } from "./OptionsStatsCards";
import { WatchlistTab } from "./WatchlistTab";
import type { Alert, AgentStatus, Position, Snapshot, Unusual, WatchlistItem } from "./types";
import { useBacktest } from "./useBacktest";
import { selectPositionsToSync } from "@/lib/optionsWatchlistSync";
import { buildWatchlistRows } from "@/lib/optionsWatchlistRows";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { QuickNav } from "@/components/QuickNav";
import { HeaderActions } from "@/components/HeaderActions";
import { usePrivacyToggle } from "@/hooks/use-privacy-toggle";

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

  // MEFF quick-add chip: same call as handleAddTicker, with the curated name.
  async function handleAddMeffTicker(ticker: string, name: string) {
    await api.options.addToWatchlist(ticker, name);
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

  // Get alerts/snapshots/unusual for a specific ticker
  function getTickerAlerts(ticker: string) {
    return alerts.filter((a) => a.ticker === ticker && !a.acknowledged);
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
      <OptionsStatsCards
        positionsCount={positions.length}
        watchlistCount={watchlist.length}
        agentStatus={agentStatus}
        alertsTotal={alerts.length}
        unreadCount={unreadAlerts.length}
        unusualCount={unusual.length}
        latestSnapshots={Array.from(latestByTicker.values())}
      />

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
        <WatchlistTab
          loading={loadingOptions}
          error={errorOptions}
          onRetry={retryOptionsLoad}
          rows={rows}
          watchlistTickers={watchlistTickers}
          errorPositions={errorPositions}
          noOptPositions={noOptPositions}
          newTicker={newTicker}
          onNewTickerChange={setNewTicker}
          onAddTicker={handleAddTicker}
          onAddMeffTicker={handleAddMeffTicker}
          expandedTicker={expandedOptionsTicker}
          onExpandedTickerChange={setExpandedOptionsTicker}
          zonasMap={zonasMap}
          zonasBusy={zonasBusy}
          onToggleZonasLens={toggleZonasLens}
          onToggleItem={handleToggleWatchlistItem}
          onHidePosition={handleHidePosition}
          onRemoveTicker={handleRemoveTicker}
        />

        {/* ── Monitor Tab (Alertas + Smart Money) ── */}
        <MonitorTab
          loading={loadingOptions}
          error={errorOptions}
          onRetry={retryOptionsLoad}
          filter={monitorFilter}
          onFilterChange={setMonitorFilter}
          alerts={alerts}
          unreadCount={unreadAlerts.length}
          unusual={unusual}
          techSignals={techSignals}
          expandedTicker={expandedOptionsTicker}
          onExpandedTickerChange={setExpandedOptionsTicker}
          geoTickers={geoTickers}
          onAckAlert={handleAckAlert}
          onAckAll={handleAckAll}
        />
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

