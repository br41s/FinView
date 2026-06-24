"use client";

import { useEffect, useMemo, useState } from "react";
import { CandlestickChart, Plus, X, TrendingUp, TrendingDown } from "lucide-react";

import { api, type OhlcBar } from "@/lib/api";
import { PriceChart } from "@/components/charts/PriceChart";
import { CHART_SCOPES, sliceOhlc, type ChartScope } from "@/lib/chartMarkers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { QuickNav } from "@/components/QuickNav";

// Legacy localStorage key — read once on mount to migrate into the DB, then cleared.
const STORAGE_KEY = "fv-markets-watchlist";
const DEFAULT_TICKERS = ["AAPL", "MSFT", "SPY"];

function fmt(n: number | null | undefined, d = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d });
}

export default function MarketsPage() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [idByTicker, setIdByTicker] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [ohlcByTicker, setOhlcByTicker] = useState<Record<string, OhlcBar[]>>({});
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const [scope, setScope] = useState<ChartScope>("1A");
  const [input, setInput] = useState("");
  const [suggestions, setSuggestions] = useState<
    { ticker: string; name: string; isin: string }[]
  >([]);

  // Load the DB-backed watchlist on mount, migrating any legacy localStorage list
  // once (then clearing it). Seeds defaults for first-time users with no list.
  useEffect(() => {
    (async () => {
      let legacy: string[] = [];
      try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) legacy = parsed.filter((x) => typeof x === "string");
        }
      } catch {
        /* ignore corrupt legacy value */
      }

      let items = await api.markets.watchlist();
      if (legacy.length > 0) {
        items = await api.markets.importTickers(legacy);
        window.localStorage.removeItem(STORAGE_KEY);
      } else if (items.length === 0) {
        items = await api.markets.importTickers(DEFAULT_TICKERS);
      }

      setWatchlist(items.map((i) => i.ticker));
      setIdByTicker(Object.fromEntries(items.map((i) => [i.ticker, i.id])));
      setSelected((prev) => prev ?? items[0]?.ticker ?? null);
    })().catch(() => {});
  }, []);

  // Suggestions come from the user's portfolio positions (name + ticker + ISIN).
  useEffect(() => {
    api.portfolio
      .positions(true)
      .then((pos) => {
        const p = pos as { ticker: string | null; isin: string; name: string }[];
        setSuggestions(
          p
            .filter((x) => x.ticker)
            .map((x) => ({ ticker: x.ticker!.toUpperCase(), name: x.name, isin: x.isin })),
        );
      })
      .catch(() => {});
  }, []);

  // Fetch full history for the selected ticker once; scopes slice it client-side.
  useEffect(() => {
    if (!selected || ohlcByTicker[selected] !== undefined) return;
    setLoading((prev) => new Set(prev).add(selected));
    api.charts
      .priceHistory(selected, "max")
      .then((bars) => setOhlcByTicker((prev) => ({ ...prev, [selected]: bars })))
      .catch(() => setOhlcByTicker((prev) => ({ ...prev, [selected]: [] })))
      .finally(() =>
        setLoading((prev) => {
          const next = new Set(prev);
          next.delete(selected);
          return next;
        }),
      );
  }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps

  async function addSpecific(ticker: string) {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setInput("");
    if (watchlist.includes(t)) {
      setSelected(t);
      return;
    }
    try {
      const item = await api.markets.addTicker(t);
      setWatchlist((prev) => [...prev, item.ticker]);
      setIdByTicker((prev) => ({ ...prev, [item.ticker]: item.id }));
      setSelected(item.ticker);
    } catch {
      // 409 (already exists) or transient error — select it if it's somehow present
      setSelected(t);
    }
  }

  function addTicker() {
    void addSpecific(input);
  }

  // Match suggestions by ticker, name or ISIN; hide ones already in the list.
  const matches = useMemo(() => {
    const q = input.trim().toUpperCase();
    if (!q) return [];
    return suggestions
      .filter(
        (s) =>
          s.ticker.includes(q) ||
          s.name.toUpperCase().includes(q) ||
          s.isin.toUpperCase().includes(q),
      )
      .filter((s) => !watchlist.includes(s.ticker))
      .slice(0, 8);
  }, [input, suggestions, watchlist]);

  function removeTicker(t: string) {
    const id = idByTicker[t];
    setWatchlist((prev) => {
      const next = prev.filter((x) => x !== t);
      if (selected === t) setSelected(next[0] ?? null);
      return next;
    });
    setIdByTicker((prev) => {
      const next = { ...prev };
      delete next[t];
      return next;
    });
    if (id != null) api.markets.removeTicker(id).catch(() => {});
  }

  const bars = selected ? (ohlcByTicker[selected] ?? []) : [];
  const isLoading = selected ? loading.has(selected) : false;

  // Last close + change vs previous close, for the header readout.
  const change = useMemo(() => {
    if (bars.length < 2) return null;
    const last = bars[bars.length - 1].close;
    const prev = bars[bars.length - 2].close;
    return { last, pct: ((last - prev) / prev) * 100 };
  }, [bars]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <CandlestickChart className="h-6 w-6" />
            Mercados
          </h1>
          <p className="text-muted-foreground">Lista de seguimiento y gráfico de velas</p>
        </div>
        <QuickNav current="/markets" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr]">
        {/* Left — watchlist */}
        <Card className="h-fit">
          <CardContent className="p-2 pt-3">
            <div className="relative mb-2 px-1">
              <div className="flex items-center gap-1">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addTicker()}
                  placeholder="Ticker, nombre o ISIN…"
                  className="h-8 w-full rounded-md border bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-ring"
                />
                <Button size="icon" className="h-8 w-8 shrink-0" onClick={addTicker} title="Añadir">
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              {matches.length > 0 && (
                <div className="absolute left-1 right-1 top-full z-10 mt-1 overflow-hidden rounded-md border bg-popover shadow-md">
                  {matches.map((s) => (
                    <button
                      key={s.isin}
                      onClick={() => void addSpecific(s.ticker)}
                      className="flex w-full flex-col items-start px-3 py-1.5 text-left hover:bg-muted"
                    >
                      <span className="text-sm font-medium">{s.ticker}</span>
                      <span className="w-full truncate text-xs text-muted-foreground">
                        {s.name}
                      </span>
                      <span className="text-[10px] text-muted-foreground/70">{s.isin}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {watchlist.length === 0 ? (
              <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                Añade un ticker para empezar.
              </p>
            ) : (
              <div className="space-y-1">
                {watchlist.map((t) => {
                  const isSelected = selected === t;
                  return (
                    <div
                      key={t}
                      className={`group flex items-center justify-between rounded-md px-3 py-2 cursor-pointer transition-colors ${
                        isSelected ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                      }`}
                      onClick={() => setSelected(t)}
                    >
                      <span className="text-sm font-medium">{t}</span>
                      <button
                        className={`opacity-0 group-hover:opacity-100 transition-opacity text-xs ${
                          isSelected
                            ? "text-primary-foreground/70 hover:text-primary-foreground"
                            : "text-muted-foreground hover:text-destructive"
                        }`}
                        title="Quitar"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeTicker(t);
                        }}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Right — chart */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-3 text-sm font-medium">
                {selected ?? "—"}
                {change && (
                  <span
                    className={`flex items-center gap-1 text-xs font-normal ${
                      change.pct >= 0 ? "text-emerald-600" : "text-red-600"
                    }`}
                  >
                    {change.pct >= 0 ? (
                      <TrendingUp className="h-3.5 w-3.5" />
                    ) : (
                      <TrendingDown className="h-3.5 w-3.5" />
                    )}
                    {fmt(change.last)} ({change.pct >= 0 ? "+" : ""}
                    {fmt(change.pct)}%)
                  </span>
                )}
              </CardTitle>
              <div className="flex items-center gap-0.5">
                {CHART_SCOPES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setScope(s)}
                    className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                      scope === s
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {!selected ? (
              <div className="flex h-[420px] items-center justify-center text-sm text-muted-foreground">
                Selecciona un valor de la lista.
              </div>
            ) : isLoading ? (
              <Skeleton className="h-[420px] w-full" />
            ) : bars.length === 0 ? (
              <div className="flex h-[420px] flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
                <p>Sin datos de precio para {selected}.</p>
                <Button variant="outline" size="sm" onClick={() => removeTicker(selected)}>
                  Quitar de la lista
                </Button>
              </div>
            ) : (
              <PriceChart data={sliceOhlc(bars, scope)} height={420} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
