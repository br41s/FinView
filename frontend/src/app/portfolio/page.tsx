"use client";

import { Fragment, useEffect, useState, useCallback, Suspense } from "react";
import { useRouter } from "next/navigation";
import {
  Briefcase,
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
  Wallet,
  PieChart,
  BarChart3,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Target,
  Loader2,
  AlertCircle,
} from "lucide-react";

import { toast } from "sonner";
import { api, type OhlcBar } from "@/lib/api";
import { PriceChart } from "@/components/charts/PriceChart";
import {
  executionMarkers,
  sliceOhlc,
  CHART_SCOPES,
  type ChartScope,
} from "@/lib/chartMarkers";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingDots } from "@/components/loading-dots";
import { QuickNav } from "@/components/QuickNav";

interface Position {
  isin: string;
  ticker: string | null;
  name: string;
  country: string | null;
  broker: string;
  quantity: number;
  avg_cost_eur: number | null;
  total_cost_eur: number | null;
  current_price_eur: number | null;
  market_value_eur: number | null;
  unrealized_pl_eur: number | null;
  unrealized_pl_pct: number | null;
  weight_pct: number | null;
}

interface Summary {
  total_positions: number;
  unique_assets: number;
  brokers: number;
  total_invested: number;
  total_market_value: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
}

interface AccountBreakdown {
  broker: string;
  account_id: number;
  quantity: number;
  cost_eur: number | null;
  value_eur: number | null;
}

interface TxHistory {
  id: number;
  type: string;
  date: string;
  quantity: number;
  price: number;
  currency: string;
  net_eur: number;
}

interface DividendByYear {
  year: number;
  gross_eur: number;
  net_eur: number;
  count: number;
}

interface PositionDetail {
  isin: string;
  name: string;
  ticker: string | null;
  country: string | null;
  total_quantity: number;
  avg_cost_eur: number | null;
  total_cost_eur: number | null;
  current_price_eur: number | null;
  market_value_eur: number;
  unrealized_pl_eur: number | null;
  unrealized_pl_pct: number | null;
  accounts: AccountBreakdown[];
  transactions: TxHistory[];
  dividends_by_year: DividendByYear[];
}

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("es-ES", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

// Smallest whitelisted yfinance period that still covers the oldest transaction.
function periodForOldest(oldest: string | undefined): string {
  if (!oldest) return "2y";
  const years =
    (Date.now() - new Date(oldest).getTime()) / (365.25 * 24 * 3600 * 1000);
  if (years <= 2) return "2y";
  if (years <= 5) return "5y";
  if (years <= 10) return "10y";
  return "max";
}

const TX_LABELS: Record<string, string> = {
  BUY: "Compra",
  SELL: "Venta",
  DIVIDEND: "Dividendo",
  INTEREST: "Interés",
  FEE: "Comisión",
  SPINOFF: "Spinoff",
  CORPORATE_ACTION: "Acción corporativa",
};

const TX_COLORS: Record<string, string> = {
  BUY: "bg-emerald-100 text-emerald-700",
  SELL: "bg-red-100 text-red-700",
  DIVIDEND: "bg-blue-100 text-blue-700",
};

function PortfolioContent() {
  const router = useRouter();
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

  useEffect(() => {
    api.zonasClav
      .watchlist()
      .then((items) => setZcWatchlist(new Set(items.map((i) => i.ticker))))
      .catch(() => {});
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

  // Fetch OHLC for the expanded position once its detail (with ticker) is loaded.
  // Cached per ISIN so re-expanding doesn't refetch. Best-effort → empty hides the chart.
  useEffect(() => {
    if (!expandedIsin) return;
    const detail = details.get(expandedIsin);
    if (!detail?.ticker || ohlcByIsin.has(expandedIsin)) return;
    const dates = detail.transactions.map((t) => t.date).filter(Boolean).sort();
    const period = periodForOldest(dates[0]);
    api.charts
      .priceHistory(detail.ticker, period)
      .then((bars) =>
        setOhlcByIsin((prev) => new Map(prev).set(expandedIsin, bars)),
      )
      .catch(() =>
        setOhlcByIsin((prev) => new Map(prev).set(expandedIsin, [])),
      );
  }, [expandedIsin, details, ohlcByIsin]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6">
        <LoadingDots text="Cargando cartera" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center gap-4">
        <div className="rounded-full bg-destructive/10 p-4">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <div>
          <h3 className="text-lg font-medium mb-1">Error al cargar datos</h3>
          <p className="text-sm text-muted-foreground max-w-md">{error}</p>
        </div>
        <Button variant="outline" onClick={() => setRetryKey((k) => k + 1)}>
          Reintentar
        </Button>
      </div>
    );
  }

  const plColor =
    summary && summary.unrealized_pl >= 0 ? "text-emerald-600" : "text-red-600";
  const PlIcon =
    summary && summary.unrealized_pl >= 0 ? ArrowUpRight : ArrowDownRight;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Briefcase className="h-6 w-6" />
            Cartera
          </h1>
          <p className="text-muted-foreground">
            Posiciones abiertas con precios en tiempo real
          </p>
        </div>
        <div className="flex items-center gap-3">
          <QuickNav current="/portfolio" />
          <Button variant="outline" size="sm" onClick={() => router.push("/accounts")}>
            Cuentas
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">
                Valor de mercado
              </CardTitle>
              <Wallet className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {pricesLoaded ? (
                <>
                  <div className="text-2xl font-bold">
                    {fmt(summary.total_market_value)} €
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Invertido: {fmt(summary.total_invested)} €
                  </p>
                </>
              ) : (
                <LoadingDots text="" />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">
                Rentabilidad
              </CardTitle>
              {pricesLoaded ? (
                <PlIcon className={`h-4 w-4 ${plColor}`} />
              ) : (
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              )}
            </CardHeader>
            <CardContent>
              {pricesLoaded ? (
                <>
                  <div className={`text-2xl font-bold ${plColor}`}>
                    {summary.unrealized_pl >= 0 ? "+" : ""}
                    {fmt(summary.unrealized_pl)} €
                  </div>
                  <p className={`text-xs ${plColor}`}>
                    {summary.unrealized_pl_pct >= 0 ? "+" : ""}
                    {fmt(summary.unrealized_pl_pct)}%
                  </p>
                </>
              ) : (
                <LoadingDots text="" />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">Posiciones</CardTitle>
              <PieChart className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {summary.total_positions}
              </div>
              <p className="text-xs text-muted-foreground">
                {summary.unique_assets} activos · {summary.brokers} brokers
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">
                Total invertido
              </CardTitle>
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {fmt(summary.total_invested)} €
              </div>
              <p className="text-xs text-muted-foreground">Coste base total</p>
            </CardContent>
          </Card>
        </div>
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Activo</TableHead>
                  <TableHead className="text-right">Cantidad</TableHead>
                  <TableHead className="text-right">Coste medio</TableHead>
                  <TableHead className="text-right">Precio actual</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead className="text-right">P&L</TableHead>
                  <TableHead className="text-right">Peso</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.map((p) => {
                  const key = `${p.isin}-${p.broker}`;
                  const isExpanded = expandedIsin === p.isin;
                  const detail = details.get(p.isin);
                  const isLoadingThis = loadingDetail === p.isin;
                  const plPositive =
                    p.unrealized_pl_eur != null && p.unrealized_pl_eur >= 0;
                  const plClass = plPositive
                    ? "text-emerald-600"
                    : "text-red-600";
                  return (
                    <Fragment key={key}>
                      <TableRow
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => handleExpand(p.isin)}
                      >
                        <TableCell className="w-8 pr-0">
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-col">
                            <span className="font-medium">
                              {p.ticker || p.isin}
                            </span>
                            <span className="text-xs text-muted-foreground truncate max-w-50">
                              {p.name}
                            </span>
                          </div>
                          <Badge variant="outline" className="text-[10px] mt-1">
                            {p.broker}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmt(p.quantity, 2)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {p.avg_cost_eur != null ? `${fmt(p.avg_cost_eur, 2)} €` : "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {!pricesLoaded ? (
                            <span className="inline-flex gap-0.5 text-muted-foreground">
                              <span className="animate-pulse">·</span>
                              <span className="animate-pulse [animation-delay:150ms]">
                                ·
                              </span>
                              <span className="animate-pulse [animation-delay:300ms]">
                                ·
                              </span>
                            </span>
                          ) : p.current_price_eur ? (
                            `${fmt(p.current_price_eur, 2)} €`
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="text-right tabular-nums font-medium">
                          {!pricesLoaded ? (
                            <span className="inline-flex gap-0.5 text-muted-foreground">
                              <span className="animate-pulse">·</span>
                              <span className="animate-pulse [animation-delay:150ms]">
                                ·
                              </span>
                              <span className="animate-pulse [animation-delay:300ms]">
                                ·
                              </span>
                            </span>
                          ) : p.market_value_eur ? (
                            `${fmt(p.market_value_eur)} €`
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell
                          className={`text-right tabular-nums ${pricesLoaded ? plClass : ""}`}
                        >
                          {!pricesLoaded ? (
                            <span className="inline-flex gap-0.5 text-muted-foreground">
                              <span className="animate-pulse">·</span>
                              <span className="animate-pulse [animation-delay:150ms]">
                                ·
                              </span>
                              <span className="animate-pulse [animation-delay:300ms]">
                                ·
                              </span>
                            </span>
                          ) : p.unrealized_pl_eur != null ? (
                            <div>
                              <div>
                                {plPositive ? "+" : ""}
                                {fmt(p.unrealized_pl_eur)} €
                              </div>
                              <div className="text-xs">
                                {plPositive ? "+" : ""}
                                {fmt(p.unrealized_pl_pct)}%
                              </div>
                            </div>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {!pricesLoaded ? (
                            <span className="inline-flex gap-0.5 text-muted-foreground">
                              <span className="animate-pulse">·</span>
                              <span className="animate-pulse [animation-delay:150ms]">
                                ·
                              </span>
                              <span className="animate-pulse [animation-delay:300ms]">
                                ·
                              </span>
                            </span>
                          ) : p.weight_pct ? (
                            `${fmt(p.weight_pct, 1)}%`
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          {zcWatchlist.has((p.ticker ?? p.isin).toUpperCase()) ? (
                            <Badge variant="secondary" className="px-1.5 text-[10px]">
                              <Target className="h-3 w-3" />
                            </Badge>
                          ) : (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0"
                              title="Añadir a Zonas Clave"
                              disabled={zcAdding.has(p.ticker ?? p.isin)}
                              onClick={async (e) => {
                                e.stopPropagation();
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
                                  toast.error(`No se pudo añadir ${p.ticker ?? p.isin}`);
                                } finally {
                                  setZcAdding((prev) => {
                                    const next = new Set(prev);
                                    next.delete(ticker);
                                    return next;
                                  });
                                }
                              }}
                            >
                              {zcAdding.has(p.ticker ?? p.isin) ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Target className="h-4 w-4 text-muted-foreground" />
                              )}
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>

                      {/* Expanded detail */}
                      {isExpanded && (
                        <TableRow key={`${key}-detail`}>
                          <TableCell colSpan={9} className="bg-muted/30 p-4">
                            {isLoadingThis && !detail ? (
                              <LoadingDots text="Cargando detalle" />
                            ) : detail ? (
                              <div className="space-y-4">
                                {/* Summary grid */}
                                <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
                                  <div>
                                    <p className="text-xs text-muted-foreground">
                                      ISIN
                                    </p>
                                    <p className="font-mono text-sm">
                                      {p.isin}
                                    </p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">
                                      Valor actual
                                    </p>
                                    <p className="font-medium">
                                      {p.market_value_eur != null ? `${fmt(p.market_value_eur)} €` : "—"}
                                    </p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">
                                      Rentabilidad
                                    </p>
                                    <p className={`font-medium ${plClass}`}>
                                      {p.unrealized_pl_pct != null
                                        ? `${p.unrealized_pl_pct >= 0 ? "+" : ""}${fmt(p.unrealized_pl_pct)}%`
                                        : "—"}
                                    </p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">
                                      Peso cartera
                                    </p>
                                    <p className="font-medium">
                                      {p.weight_pct
                                        ? `${fmt(p.weight_pct, 1)}%`
                                        : "—"}
                                    </p>
                                  </div>
                                  {p.country && (
                                    <div>
                                      <p className="text-xs text-muted-foreground">
                                        País
                                      </p>
                                      <p className="font-medium">{p.country}</p>
                                    </div>
                                  )}
                                </div>

                                {/* Account breakdown */}
                                {detail.accounts.length > 1 && (
                                  <div>
                                    <h4 className="mb-2 text-sm font-semibold">
                                      Distribución por cuenta
                                    </h4>
                                    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                                      {detail.accounts.map((a) => (
                                        <div
                                          key={a.account_id}
                                          className="rounded-md border p-2"
                                        >
                                          <Badge
                                            variant="outline"
                                            className="text-[10px]"
                                          >
                                            {a.broker}
                                          </Badge>
                                          <p className="mt-1 text-sm">
                                            {fmt(a.quantity)} uds
                                          </p>
                                          <p className="text-xs text-muted-foreground">
                                            {a.value_eur
                                              ? `${fmt(a.value_eur)} €`
                                              : `${fmt(a.cost_eur)} € (coste)`}
                                          </p>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {detail.dividends_by_year.length > 0 && (
                                  <div>
                                    <h4 className="mb-2 text-sm font-semibold">
                                      Dividendos cobrados
                                    </h4>
                                    <Table>
                                      <TableHeader>
                                        <TableRow>
                                          <TableHead>Año</TableHead>
                                          <TableHead className="text-right">
                                            Bruto (EUR)
                                          </TableHead>
                                          <TableHead className="text-right">
                                            Neto (EUR)
                                          </TableHead>
                                          <TableHead className="text-right">
                                            Pagos
                                          </TableHead>
                                        </TableRow>
                                      </TableHeader>
                                      <TableBody>
                                        {detail.dividends_by_year.map((d) => (
                                          <TableRow key={d.year}>
                                            <TableCell className="font-medium">
                                              {d.year}
                                            </TableCell>
                                            <TableCell className="text-right tabular-nums">
                                              {fmt(d.gross_eur)} €
                                            </TableCell>
                                            <TableCell className="text-right tabular-nums font-medium text-blue-700">
                                              {fmt(d.net_eur)} €
                                            </TableCell>
                                            <TableCell className="text-right tabular-nums text-muted-foreground">
                                              {d.count}
                                            </TableCell>
                                          </TableRow>
                                        ))}
                                      </TableBody>
                                    </Table>
                                  </div>
                                )}

                                {(() => {
                                  const bars =
                                    ohlcByIsin.get(detail.isin) ?? [];
                                  if (!detail.ticker || bars.length === 0)
                                    return null;
                                  return (
                                    <div>
                                      <div className="mb-2 flex items-center justify-between">
                                        <h4 className="text-sm font-semibold">
                                          Precio y operaciones{" "}
                                          <span className="font-normal text-muted-foreground">
                                            ▲ compra · ▼ venta · ● dividendo
                                          </span>
                                        </h4>
                                        <div className="flex items-center gap-0.5">
                                          {CHART_SCOPES.map((s) => (
                                            <button
                                              key={s}
                                              onClick={() => setChartScope(s)}
                                              className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                                                chartScope === s
                                                  ? "bg-primary text-primary-foreground"
                                                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                              }`}
                                            >
                                              {s}
                                            </button>
                                          ))}
                                        </div>
                                      </div>
                                      <PriceChart
                                        data={sliceOhlc(bars, chartScope)}
                                        markers={executionMarkers(
                                          detail.transactions,
                                        )}
                                        height={360}
                                      />
                                    </div>
                                  );
                                })()}

                                <div>
                                  <h4 className="mb-2 text-sm font-semibold">
                                    Historial ({detail.transactions.length}{" "}
                                    operaciones)
                                  </h4>
                                  {detail.transactions.length === 0 ? (
                                    <p className="text-sm text-muted-foreground">
                                      No hay operaciones registradas
                                    </p>
                                  ) : (
                                    <Table>
                                      <TableHeader>
                                        <TableRow>
                                          <TableHead>Tipo</TableHead>
                                          <TableHead>Fecha</TableHead>
                                          <TableHead className="text-right">
                                            Cantidad
                                          </TableHead>
                                          <TableHead className="text-right">
                                            Precio
                                          </TableHead>
                                          <TableHead className="text-right">
                                            Neto (EUR)
                                          </TableHead>
                                        </TableRow>
                                      </TableHeader>
                                      <TableBody>
                                        {detail.transactions.map((tx) => (
                                          <TableRow key={tx.id}>
                                            <TableCell>
                                              <Badge
                                                className={
                                                  TX_COLORS[tx.type] ||
                                                  "bg-gray-100 text-gray-700"
                                                }
                                              >
                                                {TX_LABELS[tx.type] || tx.type}
                                              </Badge>
                                            </TableCell>
                                            <TableCell className="tabular-nums">
                                              {new Date(
                                                tx.date,
                                              ).toLocaleDateString("es-ES")}
                                            </TableCell>
                                            <TableCell className="text-right tabular-nums">
                                              {fmt(tx.quantity)}
                                            </TableCell>
                                            <TableCell className="text-right tabular-nums">
                                              {fmt(tx.price)} {tx.currency}
                                            </TableCell>
                                            <TableCell className="text-right tabular-nums font-medium">
                                              {fmt(tx.net_eur)} €
                                            </TableCell>
                                          </TableRow>
                                        ))}
                                      </TableBody>
                                    </Table>
                                  )}
                                </div>
                              </div>
                            ) : (
                              <p className="text-sm text-muted-foreground">
                                Error al cargar detalle
                              </p>
                            )}
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
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
