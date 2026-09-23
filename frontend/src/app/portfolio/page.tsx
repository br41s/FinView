"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter } from "next/navigation";
import { Briefcase, TrendingUp } from "lucide-react";

import { toast } from "sonner";
import { api } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";
import type { GeoSignal } from "@/lib/geo";
import { ErrorState } from "@/components/ErrorState";
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
import type { Position } from "./types";
import { usePortfolioData } from "./usePortfolioData";
import { usePositionDetails } from "./usePositionDetails";

function PortfolioContent() {
  const router = useRouter();
  const { privacy, togglePrivacy } = usePrivacyToggle();
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

  // Called after the two badge effects on purpose: effects run in declaration
  // order, so this keeps the mount-time fetch order zonas → geo → portfolio
  // → OHLC exactly as it was when everything was inline.
  const { positions, summary, loading, error, pricesLoaded, retry } = usePortfolioData();
  const {
    expandedIsin,
    details,
    loadingDetail,
    handleExpand,
    ohlcByIsin,
    chartScope,
    setChartScope,
  } = usePositionDetails();

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

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6">
        <LoadingDots text="Cargando cartera" />
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error} onRetry={retry} />;
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
