"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingDots } from "@/components/loading-dots";
import { ErrorState } from "@/components/ErrorState";
import { formatEur } from "@/lib/format";
import {
  type Exposure,
  type ExposureBucket,
  type Axis,
  coveredPct,
  estimateNote,
  estimatedPct,
  estimatedSourceNote,
  isUnknownBucket,
  measureName,
  shareOf,
  sourceName,
} from "@/lib/exposure";

import { useExposure } from "./useExposure";

const KNOWN_FILL = "var(--chart-1)";
const UNKNOWN_FILL = "color-mix(in srgb, var(--muted-foreground) 35%, transparent)";
const ROW_HEIGHT = 34;

function pct(n: number) {
  return `${n.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;
}

function BucketTooltip({ active, payload }: { active?: boolean; payload?: { payload: ExposureBucket }[] }) {
  if (!active || !payload?.length) return null;
  const b = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <div className="font-medium text-foreground">{b.label}</div>
      <div className="text-muted-foreground">
        {pct(b.pct)} · <span className="fv-sensitive">{formatEur(b.value_eur)}</span>
      </div>
      <ul className="mt-1 space-y-0.5 text-muted-foreground">
        {b.holdings.slice(0, 4).map((h) => (
          <li key={h.isin}>{h.name}</li>
        ))}
        {b.holdings.length > 4 && <li>y {b.holdings.length - 4} más</li>}
      </ul>
      <div className="mt-1 text-muted-foreground/80">Pulsa para ver el detalle</div>
    </div>
  );
}

function BucketDetail({ bucket, axis }: { bucket: ExposureBucket; axis: Axis }) {
  return (
    <div className="mt-3 rounded-lg border border-border p-3 text-sm">
      <div className="mb-2 font-medium">
        {bucket.label} · {pct(bucket.pct)}
      </div>
      <ul className="space-y-1.5">
        {bucket.holdings.map((h) => (
          <li key={h.isin} className="flex flex-wrap items-baseline justify-between gap-x-3">
            <span>
              {h.name}
              {h.segments.length > 0 && (
                <span className="text-muted-foreground">
                  {" — "}
                  {h.basis === "listing"
                    ? h.segments.map((s) => `${s.label}: ${estimateNote(axis)}`).join(", ")
                    : h.segments
                        .map((s) => `${s.label} (${pct(s.pct)} ${shareOf(h.measure)})`)
                        .join(", ")}
                </span>
              )}
            </span>
            <span className="tabular-nums text-muted-foreground fv-sensitive">
              {formatEur(h.value_eur)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ExposureChart({
  title,
  axis,
  buckets,
}: {
  title: string;
  axis: Axis;
  buckets: ExposureBucket[];
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const bucket = buckets.find((b) => b.key === selected) ?? null;

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-medium">{title}</h3>
        <span className="text-xs text-muted-foreground">
          {pct(coveredPct(buckets))} del valor con datos
          {estimatedPct(buckets) > 0 && ` (${pct(estimatedPct(buckets))} estimado)`}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={Math.max(2, buckets.length) * ROW_HEIGHT + 8}>
        <BarChart
          data={buckets}
          layout="vertical"
          margin={{ top: 0, right: 8, bottom: 0, left: 0 }}
          barCategoryGap={4}
        >
          {/* Headroom so the value label beside the longest bar never wraps. */}
          <XAxis type="number" hide domain={[0, (max: number) => max * 1.4]} />
          <YAxis
            type="category"
            dataKey="label"
            width={124}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
          />
          <Tooltip
            content={<BucketTooltip />}
            cursor={{ fill: "color-mix(in srgb, var(--muted-foreground) 10%, transparent)" }}
          />
          <Bar
            dataKey="pct"
            radius={[0, 4, 4, 0]}
            isAnimationActive={false}
            cursor="pointer"
            onClick={(_, index) => {
              const key = buckets[index]?.key ?? null;
              setSelected((prev) => (prev === key ? null : key));
            }}
          >
            {buckets.map((b) => (
              <Cell
                key={b.key}
                fill={isUnknownBucket(b.key) ? UNKNOWN_FILL : KNOWN_FILL}
                stroke={b.key === selected ? "var(--foreground)" : undefined}
              />
            ))}
            {/* Drawn by hand: Recharts' own label wraps "33,4 %" at the space. */}
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
      {bucket && <BucketDetail bucket={bucket} axis={axis} />}
    </div>
  );
}

function Sources({ exposure }: { exposure: Exposure }) {
  const withData = exposure.sources.filter((s) => s.url).length;
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        Fuentes: {withData} de {exposure.sources.length} posiciones con informe anual leído
      </summary>
      <ul className="mt-2 space-y-1">
        {exposure.sources.map((s) => (
          <li key={s.isin} className="flex flex-wrap items-baseline justify-between gap-x-3">
            <span>{s.name}</span>
            {s.url ? (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-muted-foreground underline-offset-2 hover:underline"
              >
                {sourceName(s.source)} {s.fiscal_year}
                {s.measure && s.measure !== "revenue" && ` · ${measureName(s.measure)}`}
                <ExternalLink className="h-3 w-3" />
              </a>
            ) : (
              <span className="text-muted-foreground">{s.detail}</span>
            )}
            {estimatedSourceNote(s.estimated) && (
              <span className="w-full text-right text-xs text-muted-foreground">
                {estimatedSourceNote(s.estimated)}
                {s.listing_sector && ` · ${s.listing_sector}`}
              </span>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function ExposureCharts({ ready }: { ready: boolean }) {
  const { exposure, error, reading, stalled, retry } = useExposure(ready);

  if (error) return <ErrorState message={error} onRetry={retry} />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Exposición por sector y región</CardTitle>
        <CardDescription>
          Valor de mercado repartido según los ingresos que cada empresa declara por segmento y
          por región en su último informe anual (10-K en la SEC, ESEF en la UE). Solo se usa un
          desglose si suma lo mismo que el total del informe. Si el informe no etiqueta una cifra
          de ingresos (bancos, aseguradoras, inmobiliarias), se reparte la que sí etiqueta y
          desglosa: margen bruto, ingresos de seguros o ingresos por alquiler, y la fuente lo
          indica. La asignación de cada segmento a un sector o región la hace un modelo de IA; el
          nombre original aparece al pulsar una barra. Una acción sin desglose en su informe se
          cuenta entera en el país de su ISIN y en el sector con el que cotiza en Yahoo Finance,
          marcado como estimado; los ETF y fondos quedan como «Sin datos».
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {!exposure ? (
          <LoadingDots text="Cargando exposición" />
        ) : (
          <>
            {(reading || stalled || exposure.unpriced.length > 0) && (
              <div className="space-y-1 text-xs text-muted-foreground">
                {reading && <LoadingDots text="Leyendo informes anuales" />}
                {!reading && stalled && (
                  <p>Algunos informes no se han podido leer ahora; se reintentará más tarde.</p>
                )}
                {exposure.unpriced.length > 0 && (
                  <p>
                    Sin precio y fuera del reparto:{" "}
                    {exposure.unpriced.map((u) => u.name).join(", ")}.
                  </p>
                )}
              </div>
            )}
            <div className="grid gap-8 lg:grid-cols-2">
              <ExposureChart title="Sector" axis="sector" buckets={exposure.sector} />
              <ExposureChart title="Región" axis="geography" buckets={exposure.geography} />
            </div>
            <Sources exposure={exposure} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
