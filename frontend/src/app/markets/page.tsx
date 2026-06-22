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

const STORAGE_KEY = "fv-markets-watchlist";
const DEFAULT_TICKERS = ["AAPL", "MSFT", "SPY"];

function loadWatchlist(): string[] {
  if (typeof window === "undefined") return DEFAULT_TICKERS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_TICKERS;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : DEFAULT_TICKERS;
  } catch {
    return DEFAULT_TICKERS;
  }
}

function fmt(n: number | null | undefined, d = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d });
}

export default function MarketsPage() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [ohlcByTicker, setOhlcByTicker] = useState<Record<string, OhlcBar[]>>({});
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const [scope, setScope] = useState<ChartScope>("1A");
  const [input, setInput] = useState("");

  // Hydrate from localStorage on mount.
  useEffect(() => {
    const wl = loadWatchlist();
    setWatchlist(wl);
    setSelected(wl[0] ?? null);
  }, []);

  // Persist whenever the watchlist changes (skip the pre-hydration empty state).
  useEffect(() => {
    if (watchlist.length === 0 && selected === null) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(watchlist));
  }, [watchlist]); // eslint-disable-line react-hooks/exhaustive-deps

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

  function addTicker() {
    const t = input.trim().toUpperCase();
    if (!t) return;
    if (!watchlist.includes(t)) setWatchlist((prev) => [...prev, t]);
    setSelected(t);
    setInput("");
  }

  function removeTicker(t: string) {
    setWatchlist((prev) => {
      const next = prev.filter((x) => x !== t);
      if (selected === t) setSelected(next[0] ?? null);
      return next;
    });
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
            <div className="mb-2 flex items-center gap-1 px-1">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addTicker()}
                placeholder="Añadir ticker…"
                className="h-8 w-full rounded-md border bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-ring"
              />
              <Button size="icon" className="h-8 w-8 shrink-0" onClick={addTicker} title="Añadir">
                <Plus className="h-4 w-4" />
              </Button>
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
