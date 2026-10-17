"use client";

import { ExternalLink } from "lucide-react";
import { Bar, BarChart, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingDots } from "@/components/loading-dots";
import { ErrorState } from "@/components/ErrorState";
import { api } from "@/lib/api";
import {
  type AiExposure,
  type AiHolding,
  type AiIndustryIndex,
  betaPct,
  mentionsText,
  quotesNote,
  releaseEs,
} from "@/lib/aiExposure";
import { sourceName } from "@/lib/exposure";

import { useAnnualReports } from "./useExposure";

const ROW_HEIGHT = 34;

function pct(n: number) {
  return `${n.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;
}

function ThemeChart({ exposure }: { exposure: AiExposure }) {
  if (exposure.themes.length === 0) return null;
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium">Temas de las citas, por valor de la cartera</h3>
      <ResponsiveContainer width="100%" height={exposure.themes.length * ROW_HEIGHT + 8}>
        <BarChart
          data={exposure.themes}
          layout="vertical"
          margin={{ top: 0, right: 8, bottom: 0, left: 0 }}
          barCategoryGap={4}
        >
          <XAxis type="number" hide domain={[0, (max: number) => max * 1.4]} />
          <YAxis
            type="category"
            dataKey="label"
            width={150}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
          />
          <Bar dataKey="pct" radius={[0, 4, 4, 0]} isAnimationActive={false} fill="var(--chart-1)">
            <LabelList
              dataKey="pct"
              content={({ x, y, width, height, value }) => (
                <text
                  x={Number(x) + Number(width) + 6}
                  y={Number(y) + Number(height) / 2}
                  dominantBaseline="central"
                  fill="var(--foreground)"
                  fontSize={12}
                >
                  {pct(Number(value))}
                </text>
              )}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-1 text-xs text-muted-foreground">
        Parte del valor en empresas con al menos una cita de ese tema. Una empresa puede
        aparecer en varios.
      </p>
    </div>
  );
}

function IndustryIndex({ index }: { index: AiIndustryIndex }) {
  const { occupations, employment } = index.sources;
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-medium">Índice por industria (cálculo de FinView)</h3>
      {index.score === null ? (
        <p className="text-sm text-muted-foreground">
          Aún no hay posiciones con ingresos por negocio asignados a una industria.
        </p>
      ) : (
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-muted-foreground">Tareas expuestas (β), media ponderada</dt>
            <dd className="text-lg font-semibold tabular-nums">{betaPct(index.score)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Valor que cubre</dt>
            <dd className="text-lg font-semibold tabular-nums">{pct(index.value_pct)}</dd>
          </div>
        </dl>
      )}
      {index.industries.length > 0 && (
        <ul className="space-y-1 text-sm">
          {index.industries.map((i) => (
            <li key={i.code} className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span>
                {i.title} <span className="text-xs text-muted-foreground">NAICS {i.code}</span>
              </span>
              <span className="tabular-nums text-muted-foreground">
                {pct(i.value_pct)} del valor · β {betaPct(i.score)}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        Calculado por FinView con el método de{" "}
        <a
          href={`https://doi.org/${index.sources.method.doi}`}
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-2"
        >
          {index.sources.method.citation}
        </a>
        : la exposición
        β de cada ocupación (la parte de sus tareas que un modelo de lenguaje podría hacer al
        menos el doble de rápido con la misma calidad, contando la mitad si necesita software
        adicional; anotación humana) de{" "}
        <a
          href={`https://doi.org/${occupations.doi}`}
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-2"
        >
          Eloundou et al., Science 2024
        </a>{" "}
        (
        <a href={occupations.url} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
          datos {occupations.license}, versión {occupations.commit.slice(0, 7)}
        </a>
        ), ponderada por el empleo de cada ocupación en cada industria de EE. UU. (
        <a href={employment.url} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
          BLS OEWS, {releaseEs(employment.release)}
        </a>
        , NAICS a 4 dígitos) y después por los ingresos de cada segmento del último informe anual.
        Un modelo de IA asigna cada segmento a una industria. Describe el trabajo en esas
        industrias en EE. UU.; no es una predicción sobre ninguna empresa.
      </p>
    </section>
  );
}

function IndustryDetail({ h }: { h: AiHolding }) {
  if (!h.industry) {
    return h.industry_detail ? (
      <p className="text-xs text-muted-foreground">Índice por industria: {h.industry_detail}.</p>
    ) : null;
  }
  return (
    <div className="space-y-1">
      <p>
        Índice por industria: <strong className="tabular-nums">{betaPct(h.industry.score)}</strong>{" "}
        <span className="text-muted-foreground">
          sobre el {pct(h.industry.revenue_pct)} de sus ingresos ({h.industry.fiscal_year})
        </span>
      </p>
      <ul className="space-y-0.5 text-xs text-muted-foreground">
        {h.industry.parts.map((part) => (
          <li key={part.label}>
            {part.label} ({pct(part.pct)}) →{" "}
            {part.title ? `${part.title} · β ${betaPct(part.score ?? 0)}` : "sin industria asignada"}
          </li>
        ))}
      </ul>
    </div>
  );
}

function HoldingRow({ h }: { h: AiHolding }) {
  const side = [h.url ? mentionsText(h) : h.detail, h.industry && `β ${betaPct(h.industry.score)}`]
    .filter(Boolean)
    .join(" · ");
  if (!h.url && !h.industry) {
    return (
      <li className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 border-b border-border py-2 last:border-b-0">
        <span className="font-medium">{h.name}</span>
        <span className="text-xs text-muted-foreground">{side}</span>
      </li>
    );
  }
  const note = quotesNote(h);
  return (
    <li className="border-b border-border py-2 last:border-b-0">
      <details>
        <summary className="flex cursor-pointer list-none flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
          <span className="font-medium">{h.name}</span>
          <span className="text-xs text-muted-foreground">{side}</span>
        </summary>
        <div className="mt-2 space-y-3 text-sm">
          {h.url && (
            <a
              href={h.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:underline"
            >
              {sourceName(h.source)} {h.fiscal_year} · {h.scope_label}
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
          {h.quotes.map((q) => (
            <figure key={q.text} className="border-l-2 border-border pl-3">
              <blockquote className="italic text-foreground/90">“{q.text}”</blockquote>
              <figcaption className="text-xs text-muted-foreground">{q.theme_label}</figcaption>
            </figure>
          ))}
          {h.summary && (
            <p className="text-muted-foreground">
              <span className="text-xs font-medium uppercase tracking-wide">Resumen (IA): </span>
              {h.summary}
            </p>
          )}
          {h.url && note && <p className="text-xs text-muted-foreground">{note}</p>}
          <IndustryDetail h={h} />
        </div>
      </details>
    </li>
  );
}

export function AiExposureCard({ ready }: { ready: boolean }) {
  const { view, error, reading, stalled, retry } = useAnnualReports(
    ready,
    api.portfolio.aiExposure,
    api.portfolio.refreshAiExposure,
    "No se pudo cargar la exposición a la IA",
  );

  if (error) return <ErrorState message={error} onRetry={retry} />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Exposición a la IA</CardTitle>
        <CardDescription>
          Dos medidas, cada una con su fuente. Primero, lo que cada empresa dice de la
          inteligencia artificial en su último informe anual (en EE. UU., los factores de riesgo
          del 10-K; en la UE, el informe ESEF completo): FinView cuenta las menciones y un modelo
          de IA elige hasta tres citas, que solo se muestran si aparecen palabra por palabra en el
          informe. Después, un índice por industria que calcula FinView a partir de datos
          publicados. Ninguna es una puntuación de riesgo de la empresa ni una probabilidad.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {!view ? (
          <LoadingDots text="Cargando exposición a la IA" />
        ) : (
          <>
            {(reading || stalled) && (
              <div className="text-xs text-muted-foreground">
                {reading && <LoadingDots text="Leyendo informes anuales" />}
                {!reading && stalled && (
                  <p>Algunos informes no se han podido leer ahora; se reintentará más tarde.</p>
                )}
              </div>
            )}
            <section className="space-y-4">
              <h3 className="text-sm font-medium">Lo que dicen los informes</h3>
              <dl className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <dt className="text-muted-foreground">Valor con informe leído</dt>
                  <dd className="text-lg font-semibold tabular-nums">{pct(view.read_pct)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Valor en empresas que mencionan la IA</dt>
                  <dd className="text-lg font-semibold tabular-nums">
                    {pct(view.mentioning_pct)}
                  </dd>
                </div>
              </dl>
              <ThemeChart exposure={view} />
            </section>
            <IndustryIndex index={view.industry_index} />
            <section>
              <h3 className="mb-1 text-sm font-medium">Por posición</h3>
              <ul>
                {view.holdings.map((h) => (
                  <HoldingRow key={h.isin} h={h} />
                ))}
              </ul>
            </section>
          </>
        )}
      </CardContent>
    </Card>
  );
}
