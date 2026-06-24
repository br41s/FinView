"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Sparkles } from "lucide-react";

import { api, type TickerAnalysis } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface ChainLeg {
  strike: number;
  lastPrice: number | null;
  impliedVolatility: number | null;
  volume: number;
  openInterest: number;
}
interface Chain {
  ticker: string;
  calls: ChainLeg[];
  puts: ChainLeg[];
}

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}
function num(v: number | null | undefined, d = 2): string {
  return v == null ? "—" : v.toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d });
}

// Split "## 1. Title\nbody" markdown into sections for card rendering.
function parseSections(text: string): { title: string; body: string }[] {
  return text
    .split(/(?=^## \d+\.)/m)
    .map((part) => {
      const nl = part.indexOf("\n");
      if (nl === -1) return null;
      return {
        title: part.slice(0, nl).replace(/^##\s*/, "").trim(),
        body: part.slice(nl + 1).trim(),
      };
    })
    .filter(Boolean) as { title: string; body: string }[];
}

function ivBadge(summary: TickerAnalysis["summary"]) {
  const iv = summary.avg_call_iv;
  const hv = summary.historical_volatility;
  if (iv == null || hv == null) return null;
  const diff = (iv - hv) * 100;
  if (diff > 5) return <Badge variant="destructive">IV cara</Badge>;
  if (diff < -5) return <Badge variant="secondary">IV barata</Badge>;
  return <Badge variant="outline">IV normal</Badge>;
}

export function OpcionesTab({ symbol }: { symbol: string }) {
  const [analysis, setAnalysis] = useState<TickerAnalysis | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const [expirations, setExpirations] = useState<string[] | null>(null);
  const [expIdx, setExpIdx] = useState(0);
  const [chain, setChain] = useState<Chain | null>(null);
  const [chainLoading, setChainLoading] = useState(false);

  // Load expirations once per symbol.
  useEffect(() => {
    let cancelled = false;
    setExpirations(null);
    setChain(null);
    setExpIdx(0);
    api.options
      .tickerExpirations(symbol)
      .then((d) => {
        if (cancelled) return;
        const exps = (d as { expirations: string[] }).expirations ?? [];
        setExpirations(exps);
      })
      .catch(() => {
        if (!cancelled) setExpirations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  // Load the chain for the selected expiry.
  const expiry = expirations?.[expIdx];
  useEffect(() => {
    if (!expiry) return;
    let cancelled = false;
    setChainLoading(true);
    api.options
      .tickerChain(symbol, expiry)
      .then((d) => {
        if (!cancelled) setChain(d as Chain);
      })
      .catch(() => {
        if (!cancelled) setChain(null);
      })
      .finally(() => {
        if (!cancelled) setChainLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, expiry]);

  async function runAi() {
    setAiLoading(true);
    setAiError(null);
    try {
      const res = await api.options.analyzeTicker(symbol);
      setAnalysis(res);
      if (!res.analysis && res.ai_error) {
        setAiError(res.ai_error === "not_configured" ? "IA no configurada en el servidor." : "El análisis IA falló.");
      }
    } catch (e) {
      setAiError(e instanceof Error ? e.message : "Error al generar el informe");
    } finally {
      setAiLoading(false);
    }
  }

  // Merge calls+puts by strike for the chain table.
  const rows = useMemo(() => {
    if (!chain) return [];
    const byStrike = new Map<number, { call?: ChainLeg; put?: ChainLeg }>();
    for (const c of chain.calls) {
      byStrike.set(c.strike, { ...(byStrike.get(c.strike) ?? {}), call: c });
    }
    for (const p of chain.puts) {
      byStrike.set(p.strike, { ...(byStrike.get(p.strike) ?? {}), put: p });
    }
    return [...byStrike.entries()].sort((a, b) => a[0] - b[0]).map(([strike, v]) => ({ strike, ...v }));
  }, [chain]);

  const sections = analysis?.analysis ? parseSections(analysis.analysis) : [];

  return (
    <div className="space-y-4">
      {/* AI report */}
      <div>
        {!analysis && !aiLoading && (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-6 text-center">
            <p className="text-sm text-muted-foreground">Informe IA por ticker (VolatilityEdge)</p>
            <Button size="sm" onClick={runAi} className="gap-1.5">
              <Sparkles className="h-3.5 w-3.5" />
              Generar informe IA
            </Button>
          </div>
        )}

        {aiLoading && (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-24 w-full rounded-lg" />
          </div>
        )}

        {analysis && !aiLoading && (
          <div className="space-y-3">
            {/* Summary chips */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-medium">{num(analysis.summary.current_price)}</span>
              {ivBadge(analysis.summary)}
              <span className="text-muted-foreground">
                P/C vol {num(analysis.summary.put_call_ratio_volume)} · IV {pct(analysis.summary.avg_call_iv)} / HV{" "}
                {pct(analysis.summary.historical_volatility)}
              </span>
              {analysis.summary.market_sentiment && (
                <Badge variant="outline">{analysis.summary.market_sentiment}</Badge>
              )}
              <Button variant="ghost" size="sm" className="ml-auto h-6 gap-1 px-2 text-xs" onClick={runAi}>
                <Sparkles className="h-3 w-3" />
                Regenerar
              </Button>
            </div>

            {aiError && <p className="text-xs text-destructive">{aiError}</p>}

            {sections.map(({ title, body }) => (
              <div key={title} className="rounded-lg border p-3">
                <p className="mb-1 text-xs font-semibold">{title}</p>
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/90">{body}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Chain */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <p className="text-xs font-semibold text-muted-foreground">Cadena de opciones</p>
          {expirations && expirations.length > 0 && (
            <div className="flex items-center gap-1 text-xs">
              <button
                disabled={expIdx === 0}
                onClick={() => setExpIdx((i) => Math.max(0, i - 1))}
                className="rounded p-0.5 hover:bg-muted disabled:opacity-30"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <span className="tabular-nums">{expiry}</span>
              <span className="text-muted-foreground/60">
                {expIdx + 1}/{expirations.length}
              </span>
              <button
                disabled={expIdx >= expirations.length - 1}
                onClick={() => setExpIdx((i) => Math.min(expirations.length - 1, i + 1))}
                className="rounded p-0.5 hover:bg-muted disabled:opacity-30"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>

        {expirations === null ? (
          <Skeleton className="h-32 w-full" />
        ) : expirations.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">Sin opciones para {symbol}.</p>
        ) : chainLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : rows.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">Sin datos para este vencimiento.</p>
        ) : (
          <div className="max-h-64 overflow-auto rounded-lg border">
            <table className="w-full text-right text-xs tabular-nums">
              <thead className="sticky top-0 bg-muted/80 text-[10px] uppercase text-muted-foreground">
                <tr>
                  <th className="px-2 py-1 text-right">C·Últ</th>
                  <th className="px-2 py-1 text-right">C·Vol</th>
                  <th className="px-2 py-1 text-center">Strike</th>
                  <th className="px-2 py-1 text-right">P·Últ</th>
                  <th className="px-2 py-1 text-right">P·Vol</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.strike} className="border-t">
                    <td className="px-2 py-1 text-emerald-600">{num(r.call?.lastPrice ?? null)}</td>
                    <td className="px-2 py-1 text-muted-foreground">{r.call?.volume?.toLocaleString() ?? "—"}</td>
                    <td className="px-2 py-1 text-center font-medium">{num(r.strike)}</td>
                    <td className="px-2 py-1 text-red-600">{num(r.put?.lastPrice ?? null)}</td>
                    <td className="px-2 py-1 text-muted-foreground">{r.put?.volume?.toLocaleString() ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
