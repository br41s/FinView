"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Target } from "lucide-react";

import { api, type ZcAnalysis } from "@/lib/api";
import { ZonasClaveChart } from "@/components/charts/ZonasClaveChart";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

type Status = "loading" | "ok" | "absent" | "analyzing" | "error";

function macdLabel(signal: string | null) {
  if (signal === "bullish") return "Alcista";
  if (signal === "bearish") return "Bajista";
  return "Neutral";
}
function num(v: number | null | undefined, d = 2): string {
  return v == null ? "—" : v.toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d });
}

export function ZonasTab({ symbol, name }: { symbol: string; name?: string }) {
  const [status, setStatus] = useState<Status>("loading");
  const [analysis, setAnalysis] = useState<ZcAnalysis | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAnalysis = useCallback(async (): Promise<boolean> => {
    try {
      const a = await api.zonasClav.analysis(symbol);
      setAnalysis(a);
      setStatus("ok");
      return true;
    } catch {
      return false;
    }
  }, [symbol]);

  // Initial load. Any error (404 not-in-watchlist or no-analysis-yet) → "absent".
  useEffect(() => {
    setStatus("loading");
    setAnalysis(null);
    fetchAnalysis().then((ok) => {
      if (!ok) setStatus("absent");
    });
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [symbol, fetchAnalysis]);

  async function addAndAnalyze() {
    setStatus("analyzing");
    try {
      // 409 (already in watchlist) is fine — analysis may just not be ready yet.
      await api.zonasClav.addTicker(symbol, name ?? "").catch(() => {});
    } catch {
      /* ignore */
    }
    // Poll for the background analysis (add-ticker fires it server-side).
    let tries = 0;
    pollRef.current = setInterval(async () => {
      tries += 1;
      const ok = await fetchAnalysis();
      if (ok || tries >= 12) {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        if (!ok && tries >= 12) setStatus("absent");
      }
    }, 3000);
  }

  if (status === "loading") return <Skeleton className="h-[320px] w-full" />;

  if (status === "absent") {
    return (
      <div className="flex h-[280px] flex-col items-center justify-center gap-3 text-center">
        <Target className="h-6 w-6 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          {symbol} no está en tu watchlist de Zonas Clave.
        </p>
        <Button size="sm" onClick={addAndAnalyze} className="gap-1.5">
          <Target className="h-3.5 w-3.5" />
          Añadir y analizar
        </Button>
      </div>
    );
  }

  if (status === "analyzing") {
    return (
      <div className="space-y-2">
        <p className="text-center text-xs text-muted-foreground">Analizando {symbol}…</p>
        <Skeleton className="h-[280px] w-full" />
      </div>
    );
  }

  if (status === "error" || !analysis) {
    return (
      <div className="flex h-[280px] items-center justify-center text-sm text-destructive">
        No se pudo cargar el análisis.
      </div>
    );
  }

  const bull = analysis.trend_bias_bullish_pct ?? 50;

  return (
    <div className="space-y-3">
      {/* Trend card */}
      <div className="rounded-lg border p-3">
        <div className="mb-2 flex items-center justify-between text-xs">
          <span className="font-medium">{num(analysis.current_price)}</span>
          <div className="flex items-center gap-1.5">
            <Badge variant="outline">RSI {num(analysis.rsi, 0)}</Badge>
            <Badge variant="outline">MACD {macdLabel(analysis.macd_signal)}</Badge>
          </div>
        </div>
        <div className="flex justify-between text-[11px] text-muted-foreground">
          <span className="text-emerald-600">{num(analysis.trend_bias_bullish_pct, 0)}% alcista</span>
          <span className="text-red-500">{num(analysis.trend_bias_bearish_pct, 0)}% bajista</span>
        </div>
        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-red-500/30">
          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${bull}%` }} />
        </div>
      </div>

      {/* Chart with S/R zones */}
      {analysis.price_history.length > 0 && (
        <ZonasClaveChart data={analysis.price_history} zones={analysis.zones} />
      )}

      {/* Zones table */}
      {analysis.zones.length > 0 && (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-xs tabular-nums">
            <thead className="bg-muted/80 text-[10px] uppercase text-muted-foreground">
              <tr>
                <th className="px-2 py-1 text-left">Tipo</th>
                <th className="px-2 py-1 text-right">Nivel</th>
                <th className="px-2 py-1 text-right">Toques</th>
                <th className="px-2 py-1 text-right">Fuerza</th>
              </tr>
            </thead>
            <tbody>
              {analysis.zones.map((z, i) => (
                <tr key={`${z.zone_type}-${z.level}-${i}`} className="border-t">
                  <td className="px-2 py-1">
                    <span className={z.zone_type === "support" ? "text-emerald-600" : "text-red-500"}>
                      {z.zone_type === "support" ? "Soporte" : "Resistencia"}
                    </span>
                  </td>
                  <td className="px-2 py-1 text-right font-medium">{num(z.level)}</td>
                  <td className="px-2 py-1 text-right text-muted-foreground">{z.touches}</td>
                  <td className="px-2 py-1 text-right text-muted-foreground">{num(z.strength, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
