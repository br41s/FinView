"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type LastAnalysis } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { AiDisclaimer } from "@/components/AiDisclaimer";

// The last agent report, moved out of page.tsx unchanged along with the badge
// and parser only it used. The tab takes no props; its response shape is
// `LastAnalysis` from lib/api.

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

export function AnalysisTab() {
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
      <AiDisclaimer />
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
                  ? `Ciclo #${analysis.cycle ?? "—"} · ${fmtDateTime(analysis.timestamp)}`
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
