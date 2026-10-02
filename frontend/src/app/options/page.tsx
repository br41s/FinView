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

import { api } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";

import { AgentChat } from "./AgentChat";
import { AnalysisTab } from "./AnalysisTab";
import { BacktestTab } from "./BacktestTab";
import { MonitorTab } from "./MonitorTab";
import { OptionsStatsCards } from "./OptionsStatsCards";
import { WatchlistTab } from "./WatchlistTab";
import type { Snapshot } from "./types";
import { useBacktest } from "./useBacktest";
import { useCrossLens } from "./useCrossLens";
import { useOptionsData } from "./useOptionsData";
import { buildWatchlistRows } from "@/lib/optionsWatchlistRows";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/PageHeader";
import { usePrivacyToggle } from "@/hooks/use-privacy-toggle";
import { AiDisclaimer } from "@/components/AiDisclaimer";

// ── Component ───────────────────────────────────────────────────────

export default function OptionsPage() {
  const { privacy, togglePrivacy } = usePrivacyToggle();
  const backtest = useBacktest();
  const { zonasMap, zonasBusy, toggleZonasLens } = useCrossLens();
  // Tickers with an active geo signal — gates the per-alert "Ideas" link.
  const [geoTickers, setGeoTickers] = useState<Set<string>>(new Set());
  const [running, setRunning] = useState(false);
  const [newTicker, setNewTicker] = useState("");
  const [analysisCycle, setAnalysisCycle] = useState(0);
  const [monitorFilter, setMonitorFilter] = useState<"alerts" | "unusual" | "technical">("alerts");
  const [activeTab, setActiveTab] = useState("watchlist");
  // Mobile-only: tapping a Posiciones card expands inline (like Cartera)
  // instead of opening the drawer; the drawer stays one tap away via its own
  // button inside the expanded card.
  const [expandedOptionsTicker, setExpandedOptionsTicker] = useState<string | null>(null);

  // N6: auto-expand ticker from URL param (?ticker=X)
  const initialTickerRef = useRef<string | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    initialTickerRef.current = params.get("ticker");
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

  // Server data, its loads, the watchlist auto-sync and every mutation. Called
  // after the geo effect so the mount-time fetch order is unchanged.
  const options = useOptionsData();
  const {
    positions,
    snapshots,
    alerts,
    unusual,
    watchlist,
    agentStatus,
    hiddenTickers,
    noOptionsTickers,
    techSignals,
    loadingOptions,
    errorPositions,
    errorOptions,
  } = options;

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

  async function handleRunCycle() {
    setRunning(true);
    try {
      await options.runCycle();
      setAnalysisCycle((c) => c + 1);
    } finally {
      setRunning(false);
    }
  }

  async function handleAddTicker() {
    if (!newTicker.trim()) return;
    await options.addTicker(newTicker.trim().toUpperCase());
    setNewTicker("");
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
      <PageHeader
        icon={Activity}
        title="Options Monitor"
        subtitle="Datos y análisis de opciones sobre tu cartera"
        current="/options"
        privacy={privacy}
        onTogglePrivacy={togglePrivacy}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={handleRunCycle} disabled={running} title="Run Cycle">
              <RefreshCw className={`h-4 w-4 ${running ? "animate-spin" : ""}`} />
            </Button>
            <Button
              variant={agentStatus?.running ? "destructive" : "default"}
              size="sm"
              onClick={options.toggleAgent}
              disabled={agentStatus?.external_scheduler}
              title={agentStatus?.external_scheduler ? "Gestionado por Cloud Scheduler" : agentStatus?.running ? "Stop Auto" : "Auto"}
            >
              {agentStatus?.running ? <Square className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
              {agentStatus?.external_scheduler && <span>Cloud Scheduler</span>}
            </Button>
          </>
        }
      />

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
          onRetry={options.retryOptionsLoad}
          rows={rows}
          watchlistTickers={watchlistTickers}
          errorPositions={errorPositions}
          noOptPositions={noOptPositions}
          newTicker={newTicker}
          onNewTickerChange={setNewTicker}
          onAddTicker={handleAddTicker}
          onAddMeffTicker={options.addTicker}
          expandedTicker={expandedOptionsTicker}
          onExpandedTickerChange={setExpandedOptionsTicker}
          zonasMap={zonasMap}
          zonasBusy={zonasBusy}
          onToggleZonasLens={toggleZonasLens}
          onToggleItem={options.toggleItem}
          onHidePosition={options.hidePosition}
          onRemoveTicker={options.removeTicker}
        />

        {/* ── Monitor Tab (Alertas + Smart Money) ── */}
        <MonitorTab
          loading={loadingOptions}
          error={errorOptions}
          onRetry={options.retryOptionsLoad}
          filter={monitorFilter}
          onFilterChange={setMonitorFilter}
          alerts={alerts}
          unreadCount={unreadAlerts.length}
          unusual={unusual}
          techSignals={techSignals}
          expandedTicker={expandedOptionsTicker}
          onExpandedTickerChange={setExpandedOptionsTicker}
          geoTickers={geoTickers}
          onAckAlert={options.ackAlert}
          onAckAll={options.ackAll}
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

      <footer className="border-t border-border pt-4">
        <AiDisclaimer />
      </footer>
    </div>
  );
}

