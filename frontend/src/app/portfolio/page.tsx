"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useRouter } from "next/navigation";
import { Briefcase, TrendingUp } from "lucide-react";

import { toast } from "sonner";
import { api, type OhlcBar } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";
import type { GeoSignal } from "@/lib/geo";
import { ErrorState } from "@/components/ErrorState";
import { SCOPE_PARAMS, type ChartScope } from "@/lib/chartMarkers";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingDots } from "@/components/loading-dots";
import { QuickNav } from "@/components/QuickNav";
import { HeaderActions } from "@/components/HeaderActions";
import { usePrivacyToggle } from "@/hooks/use-privacy-toggle";

import { PortfolioSummaryCards } from "./PortfolioSummaryCards";
import { PositionsMobileList } from "./PositionsMobileList";
import { PositionsTable } from "./PositionsTable";
import type { Position, PositionDetail, Summary } from "./types";

function PortfolioContent() {
  const router = useRouter();
  const { privacy, togglePrivacy } = usePrivacyToggle();
  const [positions, setPositions] = useState<Position[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [pricesLoaded, setPricesLoaded] = useState(false);
  const [expandedIsin, setExpandedIsin] = useState<string | null>(null);
  const [ohlcByIsin, setOhlcByIsin] = useState<Map<string, OhlcBar[]>>(new Map());
  const [chartScope, setChartScope] = useState<ChartScope>("MAX");
  const [details, setDetails] = useState<Map<string, PositionDetail>>(
    new Map(),
  );
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null);
  const [zcWatchlist, setZcWatchlist] = useState<Set<string>>(new Set());
  const [zcAdding, setZcAdding] = useState<Set<string>>(new Set());
  const [geoByTicker, setGeoByTicker] = useState<Map<string, GeoSignal>>(new Map());

  useEffect(() => {
    api.zonasClav
      .watchlist()
      .then((items) => setZcWatchlist(new Set(items.map((i) => i.ticker))))
      .catch(bestEffort("zonas watchlist membership"));
  }, []);

  // Keep only the highest-importance active signal per ticker so the badge
  // reflects the most relevant geopolitical risk on that position.
  useEffect(() => {
    api.geo
      .signals("active")
      .then((signals) => {
        const byTicker = new Map<string, GeoSignal>();
        for (const s of signals) {
          for (const t of s.tickers) {
            const key = t.symbol.toUpperCase();
            const existing = byTicker.get(key);
            if (!existing || s.importance > existing.importance) {
              byTicker.set(key, s);
            }
          }
        }
        setGeoByTicker(byTicker);
      })
      .catch(bestEffort("geo signal badges"));
  }, []);

  useEffect(() => {
    async function load() {
      setError(null);

      // Phase 1: positions + summary without live prices (must succeed)
      try {
        const [pos, sum] = await Promise.all([
          api.portfolio.positions(true) as Promise<Position[]>,
          api.portfolio.summary(true) as Promise<Summary>,
        ]);
        setPositions(pos);
        setSummary(sum);
        setLoading(false);
      } catch (e) {
        console.error("Failed to load portfolio:", e);
        setError("No se pudieron cargar los datos de la cartera. Comprueba tu conexión e inténtalo de nuevo.");
        setLoading(false);
        return;
      }

      // Phase 2: live prices (optional — failure leaves prices as "—")
      try {
        const [posWithPrices, sumWithPrices] = await Promise.all([
          api.portfolio.positions() as Promise<Position[]>,
          api.portfolio.summary() as Promise<Summary>,
        ]);
        setPositions(posWithPrices);
        setSummary(sumWithPrices);
        setPricesLoaded(true);
      } catch (e) {
        console.error("Failed to load live prices:", e);
        // non-critical — positions already shown without live prices
      }
    }
    load();
  }, [retryKey]);

  const handleExpand = useCallback(
    async (isin: string) => {
      if (expandedIsin === isin) {
        setExpandedIsin(null);
        return;
      }
      setExpandedIsin(isin);
      if (!details.has(isin)) {
        setLoadingDetail(isin);
        try {
          const data = (await api.portfolio.positionDetail(
            isin,
          )) as PositionDetail;
          setDetails((prev) => new Map(prev).set(isin, data));
        } catch (e) {
          console.error("Failed to load detail:", e);
        } finally {
          setLoadingDetail(null);
        }
      }
    },
    [expandedIsin, details],
  );

  async function handleAddToZonas(p: Position) {
    const ticker = p.ticker ?? p.isin;
    setZcAdding((prev) => new Set([...prev, ticker]));
    try {
      await api.zonasClav.addTicker(ticker, p.name);
      setZcWatchlist((prev) => new Set([...prev, ticker.toUpperCase()]));
      toast.success(`${p.name} añadido a Zonas Clave`, {
        action: {
          label: "Ir a Zonas Clave",
          onClick: () => router.push("/zonas-clave"),
        },
      });
    } catch {
      toast.error(`No se pudo añadir ${ticker}`);
    } finally {
      setZcAdding((prev) => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    }
  }

  // Fetch OHLC for the expanded position + selected scope. Cached per
  // "isin:scope" so switching scope/re-expanding doesn't refetch. Best-effort
  // → empty hides the chart.
  useEffect(() => {
    if (!expandedIsin) return;
    const detail = details.get(expandedIsin);
    const cacheKey = `${expandedIsin}:${chartScope}`;
    if (!detail?.ticker || ohlcByIsin.has(cacheKey)) return;
    const { period, interval } = SCOPE_PARAMS[chartScope];
    api.charts
      .priceHistory(detail.ticker, period, interval)
      .then((bars) =>
        setOhlcByIsin((prev) => new Map(prev).set(cacheKey, bars)),
      )
      .catch(() =>
        setOhlcByIsin((prev) => new Map(prev).set(cacheKey, [])),
      );
  }, [expandedIsin, chartScope, details, ohlcByIsin]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6">
        <LoadingDots text="Cargando cartera" />
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error} onRetry={() => setRetryKey((k) => k + 1)} />;
  }

  return (
    <div className="space-y-6 p-6" data-privacy={privacy ? "true" : "false"}>
      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Briefcase className="h-6 w-6" />
            Cartera
          </h1>
          <HeaderActions privacy={privacy} onTogglePrivacy={togglePrivacy} />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-muted-foreground">
            Posiciones abiertas con precios en tiempo real
          </p>
          <div className="flex items-center gap-3">
            <QuickNav current="/portfolio" />
            <Button variant="outline" size="sm" onClick={() => router.push("/accounts")}>
              Cuentas
            </Button>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <PortfolioSummaryCards summary={summary} pricesLoaded={pricesLoaded} />
      )}

      {/* Positions Table */}
      {positions.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <TrendingUp className="h-12 w-12 text-muted-foreground mb-4" />
            <CardTitle className="mb-2">Sin posiciones abiertas</CardTitle>
            <CardDescription>
              Importa datos desde el dashboard o añade transacciones
              manualmente.
            </CardDescription>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Posiciones ({positions.length})</CardTitle>
            <CardDescription>
              Pulsa en una posición para ver detalle y transacciones
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <PositionsTable
              positions={positions}
              pricesLoaded={pricesLoaded}
              expandedIsin={expandedIsin}
              details={details}
              loadingDetail={loadingDetail}
              onExpand={handleExpand}
              geoByTicker={geoByTicker}
              zcWatchlist={zcWatchlist}
              zcAdding={zcAdding}
              onAddToZonas={handleAddToZonas}
              ohlcByIsin={ohlcByIsin}
              chartScope={chartScope}
              setChartScope={setChartScope}
            />

            {/* Mobile: stacked cards instead of a horizontally-scrolling table */}
            <PositionsMobileList
              positions={positions}
              pricesLoaded={pricesLoaded}
              expandedIsin={expandedIsin}
              details={details}
              loadingDetail={loadingDetail}
              onExpand={handleExpand}
              geoByTicker={geoByTicker}
              zcWatchlist={zcWatchlist}
              zcAdding={zcAdding}
              onAddToZonas={handleAddToZonas}
              ohlcByIsin={ohlcByIsin}
              chartScope={chartScope}
              setChartScope={setChartScope}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function PortfolioPage() {
  return (
    <Suspense
      fallback={
        <div className="p-6">
          <Skeleton className="h-8 w-48" />
        </div>
      }
    >
      <PortfolioContent />
    </Suspense>
  );
}
