"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ChevronDown,
  Plus,
  RefreshCw,
  Target,
  TrendingDown,
  TrendingUp,
  Play,
  Square,
  AlertCircle,
} from "lucide-react";
import {
  api,
  type ZcAnalysis,
  type ZcWatchlistItem,
  type ZcTickerSearchResult,
  type OhlcBar,
} from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";
import { SCOPE_PARAMS } from "@/lib/chartMarkers";
import { ZonasClaveChart } from "@/components/charts/ZonasClaveChart";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { QuickNav } from "@/components/QuickNav";
import { HeaderActions } from "@/components/HeaderActions";
import { usePrivacyToggle } from "@/hooks/use-privacy-toggle";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// ── Types ────────────────────────────────────────────────────────────

type Scope = "1D" | "1W" | "1M" | "1Y" | "5Y" | "MAX";

const SCOPES: Scope[] = ["1D", "1W", "1M", "1Y", "5Y", "MAX"];

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

// Only ever called with "1Y" | "5Y" | "MAX" — 1D/1W/1M use a fresh intraday
// fetch instead (see the intradayBars effect below).
function filterByScope(
  history: { date: string; close: number; volume: number }[],
  scope: Extract<Scope, "1Y" | "5Y" | "MAX">,
) {
  if (history.length === 0 || scope === "MAX") return history;

  // Use the last available bar as reference so weekends/holidays always return data
  const lastDate = new Date(history[history.length - 1].date + "T12:00:00");
  const cutoff = new Date(lastDate);

  if (scope === "1Y") cutoff.setFullYear(lastDate.getFullYear() - 1);
  else cutoff.setFullYear(lastDate.getFullYear() - 5);

  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const filtered = history.filter((p) => p.date >= cutoffStr);
  return filtered.length >= 2 ? filtered : history.slice(-5);
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
  const { privacy, togglePrivacy } = usePrivacyToggle();
  const [watchlist, setWatchlist] = useState<ZcWatchlistItem[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, ZcAnalysis>>({});
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>("1Y");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState<Set<string>>(new Set());
  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [externalScheduler, setExternalScheduler] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [portfolioSuggestions, setPortfolioSuggestions] = useState<
    { ticker: string; name: string; isin: string }[]
  >([]);
  // Options lens state for cross-section toggles: ticker → options watchlist id
  const [optionsMap, setOptionsMap] = useState<Map<string, number>>(new Map());
  const [optionsBusy, setOptionsBusy] = useState<Set<string>>(new Set());
  const [searchInput, setSearchInput] = useState("");
  const [remoteMatches, setRemoteMatches] = useState<ZcTickerSearchResult[]>([]);
  const [intradayBars, setIntradayBars] = useState<OhlcBar[]>([]);

  // U1: load portfolio tickers for quick-add suggestions (non-blocking)
  useEffect(() => {
    api.portfolio
      .positions(true)
      .then((pos) => {
        const p = pos as { ticker: string | null; isin: string; name: string }[];
        setPortfolioSuggestions(
          p
            .filter((x) => x.ticker)
            .map((x) => ({ ticker: x.ticker!.toUpperCase(), name: x.name, isin: x.isin })),
        );
      })
      .catch(bestEffort("portfolio tickers for autocomplete"));
  }, []);

  // Options lens info for the per-row "Opciones" toggles — best-effort
  useEffect(() => {
    (api.options.watchlist() as Promise<{ id: number; ticker: string }[]>)
      .then((wl) => setOptionsMap(new Map(wl.map((w) => [w.ticker, w.id]))))
      .catch(bestEffort("options lens map for the row toggles"));
  }, []);

  // Initial load
  useEffect(() => {
    setError(null);
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
        setExternalScheduler(status.external_scheduler);
        // N5: auto-select from URL param (?ticker=X), fallback to first item
        const params = new URLSearchParams(window.location.search);
        const urlTicker = params.get("ticker")?.toUpperCase();
        const match = urlTicker ? wl.find((w) => w.ticker.toUpperCase() === urlTicker) : null;
        const tickerToSelect = match ? match.ticker : (wl[0]?.ticker ?? null);
        if (!selectedTicker) setSelectedTicker(tickerToSelect);
      })
      .catch((e) => {
        console.error("Failed to load Zonas Clave:", e);
        setError("No se pudieron cargar las zonas clave.");
      })
      .finally(() => setLoading(false));
  }, [retryKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-poll every 3s when selected ticker has no analysis (e.g. just added)
  const hasAnalysis = selectedTicker != null && !!analyses[selectedTicker];
  useEffect(() => {
    if (!selectedTicker || hasAnalysis) return;
    const interval = setInterval(async () => {
      try {
        const arr = await api.zonasClav.allAnalyses();
        for (const a of arr) {
          const item = watchlist.find((w) => w.id === a.watchlist_item_id);
          if (item?.ticker === selectedTicker) {
            setAnalyses((prev) => ({ ...prev, [selectedTicker]: a }));
            break;
          }
        }
      } catch {
        // silent — backend may not have the result yet
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [selectedTicker, hasAnalysis]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Options lens — cross-section toggle from the zonas list ────────
  async function toggleOptionsLens(item: ZcWatchlistItem) {
    if (optionsBusy.has(item.ticker)) return;
    setOptionsBusy((prev) => new Set(prev).add(item.ticker));
    try {
      const id = optionsMap.get(item.ticker);
      if (id != null) {
        await api.options.removeFromWatchlist(id);
      } else {
        await api.options.addToWatchlist(item.ticker, item.name ?? "");
      }
      const wl = (await api.options.watchlist()) as { id: number; ticker: string }[];
      setOptionsMap(new Map(wl.map((w) => [w.ticker, w.id])));
    } catch (e) {
      console.error("options lens toggle:", e);
    } finally {
      setOptionsBusy((prev) => {
        const next = new Set(prev);
        next.delete(item.ticker);
        return next;
      });
    }
  }

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
      const result = await api.zonasClav.triggerAll();
      const attempts = result.status === "started" ? 10 : 1;
      for (let i = 0; i < attempts; i++) {
        if (result.status === "started") {
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
        const analysisArr = await api.zonasClav.allAnalyses();
        const map: Record<string, ZcAnalysis> = {};
        for (const a of analysisArr) {
          const item = watchlist.find((w) => w.id === a.watchlist_item_id);
          if (item) map[item.ticker] = a;
        }
        setAnalyses(map);
        if (tickers.every((t) => map[t])) break;
      }
    } catch (e) {
      console.error("Refresh all failed:", e);
    } finally {
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

  // Search box — add any ticker (not just portfolio suggestions), ported from /markets.
  async function addSpecific(ticker: string, name = "") {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setSearchInput("");
    if (watchlist.some((w) => w.ticker.toUpperCase() === t)) {
      setSelectedTicker(watchlist.find((w) => w.ticker.toUpperCase() === t)!.ticker);
      return;
    }
    try {
      const item = await api.zonasClav.addTicker(t, name);
      setWatchlist((prev) => [...prev, item]);
      setSelectedTicker(item.ticker);
    } catch {
      // 409 (already exists) or transient error — select it if it's somehow present
      const existing = watchlist.find((w) => w.ticker.toUpperCase() === t);
      if (existing) setSelectedTicker(existing.ticker);
    }
  }

  // Debounced live search against Yahoo Finance (any ticker worldwide, not just
  // portfolio holdings) — mirrors the alt-investments CNMV search box pattern.
  useEffect(() => {
    const q = searchInput.trim();
    if (q.length < 2) {
      setRemoteMatches([]);
      return;
    }
    const handle = setTimeout(() => {
      api.zonasClav.search(q).then(setRemoteMatches).catch(() => setRemoteMatches([]));
    }, 300);
    return () => clearTimeout(handle);
  }, [searchInput]);

  // Portfolio holdings match instantly (no network round-trip); remote results
  // fill in everything else. Merge and dedupe by ticker, portfolio first.
  const searchMatches = useMemo(() => {
    const q = searchInput.trim().toUpperCase();
    if (!q) return [];
    const watchlistSet = new Set(watchlist.map((w) => w.ticker.toUpperCase()));
    const portfolioMatches = portfolioSuggestions
      .filter(
        (s) =>
          s.ticker.includes(q) || s.name.toUpperCase().includes(q) || s.isin.toUpperCase().includes(q),
      )
      .filter((s) => !watchlistSet.has(s.ticker))
      .map((s) => ({ ticker: s.ticker, name: s.name, sublabel: s.isin }));
    const seen = new Set(portfolioMatches.map((s) => s.ticker));
    const combined = [...portfolioMatches];
    for (const r of remoteMatches) {
      const ticker = r.ticker.toUpperCase();
      if (seen.has(ticker) || watchlistSet.has(ticker)) continue;
      seen.add(ticker);
      combined.push({ ticker, name: r.name, sublabel: r.exchange });
    }
    return combined.slice(0, 8);
  }, [searchInput, portfolioSuggestions, watchlist, remoteMatches]);

  const analysis = selectedTicker ? analyses[selectedTicker] : null;
  const isAnalyzing = selectedTicker ? analyzing.has(selectedTicker) : false;

  // When 5Y/MAX is selected and stored data covers < 4 years, auto-refresh to
  // pull the full 20y history the analyzer now fetches.
  useEffect(() => {
    if (!selectedTicker || !analysis || isAnalyzing) return;
    if (scope !== "5Y" && scope !== "MAX") return;
    const firstBar = analysis.price_history[0]?.date;
    if (!firstBar) return;
    const yearsStored =
      (Date.now() - new Date(firstBar + "T12:00:00").getTime()) / (365.25 * 24 * 3600 * 1000);
    if (yearsStored < 4) handleRefresh(selectedTicker);
  }, [scope, selectedTicker]); // eslint-disable-line react-hooks/exhaustive-deps

  // 1D/1W/1M get real intraday candles from yfinance instead of slicing the
  // stored daily analysis down to a handful of bars. S/R zone lines (from the
  // daily analysis) stay overlaid regardless — they're a daily/weekly concept.
  useEffect(() => {
    if (!selectedTicker || (scope !== "1D" && scope !== "1W" && scope !== "1M")) {
      setIntradayBars([]);
      return;
    }
    let cancelled = false;
    const { period, interval } = SCOPE_PARAMS[scope];
    api.charts
      .priceHistory(selectedTicker, period, interval)
      .then((bars) => {
        if (!cancelled) setIntradayBars(bars);
      })
      .catch(() => {
        if (!cancelled) setIntradayBars([]);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedTicker, scope]);

  // Chart data — intraday fetch for 1D/1W/1M, daily analysis (scope-filtered)
  // otherwise. lightweight-charts autoscales the price axis either way.
  const priceHistory =
    scope === "1D" || scope === "1W" || scope === "1M"
      ? intradayBars
      : filterByScope(analysis?.price_history ?? [], scope);
  const visibleZones = analysis?.zones ?? [];

  // Last close vs previous close, in points and percent — from the full (unscoped)
  // history so it always reflects the latest session regardless of the chart scope.
  const priceChange = useMemo(() => {
    const hist = analysis?.price_history;
    if (!hist || hist.length < 2) return null;
    const last = hist[hist.length - 1].close;
    const prev = hist[hist.length - 2].close;
    return { last, delta: last - prev, pct: ((last - prev) / prev) * 100 };
  }, [analysis]);

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Target className="h-6 w-6" />
            Zonas Clave
          </h1>
          <HeaderActions privacy={privacy} onTogglePrivacy={togglePrivacy} />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-muted-foreground">
            Soportes, resistencias y tendencia algorítmica
          </p>
          <div className="flex items-center gap-3">
            <QuickNav current="/zonas-clave" />
            <Button
              variant="default"
              size="icon"
              onClick={handleRefreshAll}
              disabled={watchlist.length === 0 || analyzing.size > 0}
              title="Actualizar todos"
            >
              <RefreshCw className={`h-4 w-4 ${analyzing.size > 0 ? "animate-spin" : ""}`} />
            </Button>
            <Button
              variant={schedulerRunning ? "destructive" : "default"}
              size="icon"
              onClick={handleToggleScheduler}
              disabled={externalScheduler}
              title={externalScheduler ? "Gestionado por Cloud Scheduler" : schedulerRunning ? "Parar actualización automática" : "Activar actualización automática (24h)"}
            >
              {externalScheduler ? <span className="text-[10px]">Cloud</span> : schedulerRunning ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex min-h-[50vh] items-center justify-center">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Activity className="h-5 w-5 animate-pulse" />
            <span>Cargando análisis...</span>
          </div>
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-16 text-center space-y-3">
            <AlertCircle className="mx-auto h-8 w-8 text-destructive" />
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" size="sm" onClick={() => setRetryKey((k) => k + 1)}>
              Reintentar
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr]">
          {/* Left — ticker list */}
          <div className="space-y-2">
            {/* Mobile toggle — hidden on lg+ */}
            <button
              className="lg:hidden w-full flex items-center justify-between rounded-xl border bg-card px-4 py-3 text-sm font-medium shadow-sm ring-1 ring-foreground/10"
              onClick={() => setSidebarOpen((p) => !p)}
            >
              <span>
                {watchlist.find((w) => w.ticker === selectedTicker)
                  ? tickerLabel(watchlist.find((w) => w.ticker === selectedTicker)!)
                  : "Seleccionar valor"}
              </span>
              <ChevronDown
                className={`h-4 w-4 transition-transform text-muted-foreground ${sidebarOpen ? "rotate-180" : ""}`}
              />
            </button>

            <Card className={`h-fit ${sidebarOpen ? "" : "hidden"} lg:block`}>
            <CardContent className="p-2 pt-3">
              <div className="relative mb-2 px-1">
                <div className="flex items-center gap-1">
                  <input
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addSpecific(searchInput)}
                    placeholder="Ticker, nombre o ISIN…"
                    className="h-8 w-full rounded-md border bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-ring"
                  />
                  <Button
                    size="icon"
                    className="h-8 w-8 shrink-0"
                    onClick={() => addSpecific(searchInput)}
                    title="Añadir"
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                {searchMatches.length > 0 && (
                  <div className="absolute left-1 right-1 top-full z-10 mt-1 overflow-hidden rounded-md border bg-popover shadow-md">
                    {searchMatches.map((s) => (
                      <button
                        key={s.ticker}
                        onClick={() => void addSpecific(s.ticker, s.name)}
                        className="flex w-full flex-col items-start px-3 py-1.5 text-left hover:bg-muted"
                      >
                        <span className="text-sm font-medium">{s.ticker}</span>
                        <span className="w-full truncate text-xs text-muted-foreground">
                          {s.name}
                        </span>
                        <span className="text-[10px] text-muted-foreground/70">{s.sublabel}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {(() => {
                const analyzedItems = watchlist.filter((w) => analyses[w.ticker]);
                const unanalyzedItems = watchlist.filter((w) => !analyses[w.ticker]);
                const renderRow = (item: ZcWatchlistItem) => {
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
                      onClick={() => {
                        setSelectedTicker(item.ticker);
                        setSidebarOpen(false);
                      }}
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
                        {(() => {
                          const inOptions = optionsMap.has(item.ticker);
                          const busy = optionsBusy.has(item.ticker);
                          return (
                            <button
                              className={`transition-opacity text-xs ${
                                inOptions
                                  ? isSelected
                                    ? "text-primary-foreground"
                                    : "text-primary"
                                  : `opacity-0 group-hover:opacity-100 ${
                                      isSelected
                                        ? "text-primary-foreground/70 hover:text-primary-foreground"
                                        : "text-muted-foreground hover:text-foreground"
                                    }`
                              } ${busy ? "opacity-50 cursor-wait" : ""}`}
                              title={
                                inOptions
                                  ? "Quitar del monitor de opciones"
                                  : "Seguir en el monitor de opciones"
                              }
                              disabled={busy}
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleOptionsLens(item);
                              }}
                            >
                              <Activity className="h-3 w-3" />
                            </button>
                          );
                        })()}
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
                };

                return (
                  <div className="space-y-1">
                    {analyzedItems.length > 0 && (
                      <>
                        <p className="px-3 pb-1 pt-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                          Analizados
                        </p>
                        {analyzedItems.map((item) => renderRow(item))}
                      </>
                    )}
                    {unanalyzedItems.length > 0 && (
                      <>
                        {analyzedItems.length > 0 && <div className="my-1 border-t" />}
                        <p className="px-3 pb-1 pt-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                          Pendiente
                        </p>
                        {unanalyzedItems.map((item) => renderRow(item))}
                      </>
                    )}
                  </div>
                );
              })()}

              {/* Portfolio quick-add suggestions */}
              {(() => {
                const watchlistSet = new Set(watchlist.map((w) => w.ticker.toUpperCase()));
                const suggestions = portfolioSuggestions.filter((p) => !watchlistSet.has(p.ticker));
                if (suggestions.length === 0) return null;
                return (
                  <div className="mt-3 border-t border-border pt-3 px-1">
                    <p className="px-2 text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5">
                      Sin analizar
                    </p>
                    <div className="flex flex-wrap gap-1 px-1">
                      {suggestions.map(({ ticker, name }) => (
                        <button
                          key={ticker}
                          title={name}
                          onClick={() =>
                            api.zonasClav.addTicker(ticker, name).then(async () => {
                              const wl = await api.zonasClav.watchlist();
                              setWatchlist(wl);
                              setSelectedTicker(ticker);
                            })
                          }
                          className="inline-flex items-center rounded-full border border-border bg-background px-2 py-0.5 text-xs font-medium transition-colors hover:bg-primary hover:text-primary-foreground hover:border-primary cursor-pointer"
                        >
                          + {ticker}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </CardContent>
            </Card>
          </div>

          {/* Right — chart + details */}
          <div className="space-y-4">
            {isAnalyzing || (!analysis && selectedTicker) ? (
              <Card>
                <CardContent className="flex min-h-[400px] items-center justify-center">
                  <div className="text-center text-muted-foreground">
                    <RefreshCw className="mx-auto mb-3 h-8 w-8 animate-spin opacity-40" />
                    <p className="text-sm">Analizando {selectedTicker}...</p>
                    <p className="text-xs mt-1 opacity-60">
                      Descargando 10 años de datos y calculando zonas
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
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-3 text-sm font-medium">
                        Gráfico de precio y zonas clave
                        {priceChange && (
                          <span
                            className={`flex items-center gap-1 text-xs font-normal ${
                              priceChange.pct >= 0 ? "text-emerald-600" : "text-red-600"
                            }`}
                          >
                            {priceChange.pct >= 0 ? (
                              <TrendingUp className="h-3.5 w-3.5" />
                            ) : (
                              <TrendingDown className="h-3.5 w-3.5" />
                            )}
                            {priceChange.delta >= 0 ? "+" : ""}
                            {fmt(priceChange.delta)} ({priceChange.pct >= 0 ? "+" : ""}
                            {fmt(priceChange.pct)}%)
                          </span>
                        )}
                      </CardTitle>
                      <div className="flex items-center gap-0.5">
                        {SCOPES.map((s) => (
                          <button
                            key={s}
                            onClick={() => setScope(s)}
                            className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                              scope === s
                                ? "bg-primary text-primary-foreground"
                                : "text-muted-foreground hover:text-foreground hover:bg-muted"
                            }`}
                          >
                            {s}
                          </button>
                        ))}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {priceHistory.length === 0 ? (
                      <Skeleton className="h-64 w-full" />
                    ) : (
                      <ZonasClaveChart data={priceHistory} zones={visibleZones} />
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
                      {/* Mobile */}
                      <div className="divide-y sm:hidden">
                        {analysis.zones.map((z, i) => (
                          <div key={i} className="flex items-center justify-between gap-2 p-3">
                            <div className="flex items-center gap-2">
                              <Badge
                                variant={z.zone_type === "support" ? "default" : "destructive"}
                                className="text-[10px]"
                              >
                                {z.zone_type === "support" ? "Soporte" : "Resistencia"}
                              </Badge>
                              <span className="font-medium tabular-nums">{fmt(z.level, 2)}</span>
                            </div>
                            <div className="flex items-center gap-3 text-xs text-muted-foreground">
                              <div className="flex items-center gap-1">
                                <div className="h-1.5 w-10 overflow-hidden rounded-full bg-muted">
                                  <div
                                    className={`h-full rounded-full ${z.zone_type === "support" ? "bg-emerald-500" : "bg-red-500"}`}
                                    style={{ width: `${z.strength * 100}%` }}
                                  />
                                </div>
                                <span>{(z.strength * 100).toFixed(0)}%</span>
                              </div>
                              <span>{z.touches} toques</span>
                              <span>{fmt(z.volume_score, 2)}x</span>
                            </div>
                          </div>
                        ))}
                      </div>
                      {/* Desktop */}
                      <Table className="hidden sm:table">
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
            ) : (
              <Card>
                <CardContent className="py-16 text-center text-muted-foreground">
                  <Target className="mx-auto mb-4 h-10 w-10 opacity-30" />
                  <p className="text-sm">
                    Añade un valor con el buscador de la izquierda para empezar.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
