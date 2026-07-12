"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { signOut } from "next-auth/react";
import { api, clearAuthToken, invalidateCache } from "@/lib/api";
import type {
  DashboardStats,
  Casilla,
  DividendSummary,
  CapitalGain,
  CrossBrokerLot,
  FIFOAdjustment,
  OptionAssignment,
  DividendsByCountry,
  DividendsMonthly,
  TopDividendPayer,
  CapitalGainsBreakdown,
  PatrimonioComposition,
  DividendYield,
  WithholdingsByCountry,
  CompanyDividendsYearly,
  YearlyMetrics,
} from "@/lib/types";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingDots } from "@/components/loading-dots";
import { FileUpload } from "@/components/FileUpload";
import { ImportedFilesList } from "@/components/ImportedFilesList";
import { StatsCards } from "@/components/StatsCards";
import { CasillasTable } from "@/components/CasillasTable";
import { DeclaracionView } from "@/components/DeclaracionView";
import { DividendsTable } from "@/components/DividendsTable";
import { CapitalGainsTable } from "@/components/CapitalGainsTable";
import { DividendYieldTable } from "@/components/DividendYieldTable";
import { YearlyComparisonView } from "@/components/YearlyComparisonView";
import { DividendsByCountryChart } from "@/components/charts/DividendsByCountryChart";
import { DividendsMonthlyChart } from "@/components/charts/DividendsMonthlyChart";
import { TopPayersChart } from "@/components/charts/TopPayersChart";
import { CapitalGainsChart } from "@/components/charts/CapitalGainsChart";
import { PatrimonioChart } from "@/components/charts/PatrimonioChart";
import { WithholdingsChart } from "@/components/charts/WithholdingsChart";
import { GrossDividendsByCountryChart } from "@/components/charts/GrossDividendsByCountryChart";
import { CompanyDividendsChart } from "@/components/charts/CompanyDividendsChart";
import { QuickNav } from "@/components/QuickNav";
import {
  Upload as UploadIcon,
  BarChart3,
  Calculator,
  TrendingUp,
  Coins,
  FileText,
  LineChart,
  CalendarRange,
  AlertCircle,
  Info,
  Eye,
  EyeOff,
  CreditCard,
  LogOut,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatEur } from "@/lib/format";

function ErrorState({
  message,
  onRetry,
}: Readonly<{ message: string; onRetry: () => void }>) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
      <div className="rounded-full bg-destructive/10 p-4">
        <AlertCircle className="h-8 w-8 text-destructive" />
      </div>
      <div>
        <h3 className="text-lg font-medium mb-1">Error al cargar datos</h3>
        <p className="text-sm text-muted-foreground max-w-md">{message}</p>
      </div>
      <Button variant="outline" onClick={onRetry}>
        Reintentar
      </Button>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <LoadingDots text="Cargando datos fiscales" />
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  description,
}: Readonly<{
  icon: React.ElementType;
  title: string;
  description: string;
}>) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="rounded-full bg-muted p-4 mb-4">
        <Icon className="h-8 w-8 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-medium mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-md">{description}</p>
    </div>
  );
}

// C3: compact IRPF summary card — shown above Casillas and Ganancias views
const IRPF_BOXES = [
  { n: 27,  label: "Intereses",        cls: "text-blue-500"    },
  { n: 29,  label: "Dividendos",       cls: "text-green-500"   },
  { n: 332, label: "Ganancias capital", cls: "text-emerald-500" },
  { n: 337, label: "Pérdidas capital",  cls: "text-red-500"     },
] as const;

function IrpfSummary({ casillas }: Readonly<{ casillas: Casilla[] }>) {
  if (casillas.length === 0) return null;
  const get = (n: number) => casillas.find((c) => c.casilla === n);
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-2">
      {IRPF_BOXES.map(({ n, label, cls }) => {
        const c = get(n);
        return (
          <Card key={n}>
            <CardHeader className="pb-1 pt-3 px-4">
              <CardTitle className="text-xs text-muted-foreground">
                Casilla {n} · {label}
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3">
              <p className={`text-base font-bold tabular-nums ${cls}`}>
                {c ? formatEur(c.amount_eur) : "—"}
              </p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

type View =
  | "graficas"
  | "rendimiento"
  | "casillas"
  | "declaracion"
  | "dividendos"
  | "ganancias"
  | "comparativa"
  | "importar";

export default function Home() {
  // useSearchParams (in DashboardContent) requires a Suspense boundary at build
  // time — same pattern as /billing and /pricing.
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <DashboardContent />
    </Suspense>
  );
}

function DashboardContent() {
  const searchParams = useSearchParams();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [casillas, setCasillas] = useState<Casilla[]>([]);
  const [dividends, setDividends] = useState<DividendSummary[]>([]);
  const [gains, setGains] = useState<CapitalGain[]>([]);
  const [view, setView] = useState<View>("graficas");
  const [loading, setLoading] = useState(true);
  // Secondary data (slow yfinance yield, yearly comparison, year-only fiscal
  // tables) streams in after first paint — it must not block the dashboard.
  const [secondaryLoading, setSecondaryLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importRefreshKey, setImportRefreshKey] = useState(0);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [filterCountry, setFilterCountry] = useState<string | null>(null);

  // Chart data
  const [divByCountry, setDivByCountry] = useState<DividendsByCountry[]>([]);
  const [divMonthly, setDivMonthly] = useState<DividendsMonthly[]>([]);
  const [topPayers, setTopPayers] = useState<TopDividendPayer[]>([]);
  const [gainsBreakdown, setGainsBreakdown] = useState<CapitalGainsBreakdown[]>(
    [],
  );
  const [patrimonio, setPatrimonio] = useState<PatrimonioComposition[]>([]);
  const [dividendYield, setDividendYield] = useState<DividendYield[]>([]);
  const [withholdings, setWithholdings] = useState<WithholdingsByCountry[]>([]);
  const [companyDividends, setCompanyDividends] = useState<
    CompanyDividendsYearly[]
  >([]);
  const [crossBrokerLots, setCrossBrokerLots] = useState<CrossBrokerLot[]>([]);
  const [fifoAdjustments, setFifoAdjustments] = useState<FIFOAdjustment[]>([]);
  const [optionAssignments, setOptionAssignments] = useState<
    OptionAssignment[]
  >([]);
  const [yearlyComparison, setYearlyComparison] = useState<YearlyMetrics[]>([]);

  // Privacy mode: blurs sensitive monetary values. Persisted in localStorage so
  // the choice survives reloads. Starts hidden=false to avoid a flash of blur.
  const [privacy, setPrivacy] = useState(false);
  useEffect(() => {
    setPrivacy(localStorage.getItem("fv-privacy") === "1");
  }, []);
  const togglePrivacy = useCallback(() => {
    setPrivacy((prev) => {
      const next = !prev;
      localStorage.setItem("fv-privacy", next ? "1" : "0");
      return next;
    });
  }, []);

  // Guards against stale responses: a rapid year switch can leave an older
  // (slow) request in flight; only the latest load is allowed to set state.
  const loadSeq = useRef(0);

  const loadData = useCallback(async (year?: number | null) => {
    const seq = ++loadSeq.current;
    const isCurrent = () => seq === loadSeq.current;

    setLoading(true);
    setSecondaryLoading(true);
    setError(null);
    const y = year ?? undefined;

    // Fire-and-forget: warm price cache in background so portfolio/options load fast
    api.portfolio.warmPrices();

    // ── Secondary data ────────────────────────────────────────────────
    // Slow (dividend-yield hits yfinance) or view-specific data. Streamed in
    // so it never blocks the main dashboard's first paint; a single failure
    // degrades only its own view instead of breaking the whole page.
    const set = <T,>(setter: (v: T) => void) => (v: T) => {
      if (isCurrent()) setter(v);
    };
    const secondary: Promise<unknown>[] = [
      (api.charts.dividendYield(y) as Promise<DividendYield[]>)
        .then(set(setDividendYield))
        .catch((e) => console.error("dividend-yield:", e)),
      (api.yearlyComparison() as Promise<{ years: YearlyMetrics[] }>)
        .then((d) => set(setYearlyComparison)(d.years))
        .catch((e) => console.error("yearly-comparison:", e)),
    ];
    if (y) {
      secondary.push(
        (api.crossBrokerLots(y) as Promise<CrossBrokerLot[]>)
          .then(set(setCrossBrokerLots))
          .catch((e) => console.error("cross-broker-lots:", e)),
        (api.fifoAdjustments(y) as Promise<FIFOAdjustment[]>)
          .then(set(setFifoAdjustments))
          .catch((e) => console.error("fifo-adjustments:", e)),
        (api.optionAssignments(y) as Promise<OptionAssignment[]>)
          .then(set(setOptionAssignments))
          .catch((e) => console.error("option-assignments:", e)),
      );
    } else {
      setCrossBrokerLots([]);
      setFifoAdjustments([]);
      setOptionAssignments([]);
    }
    void Promise.allSettled(secondary).then(() => {
      if (isCurrent()) setSecondaryLoading(false);
    });

    // ── Core + dashboard charts ───────────────────────────────────────
    // All fast SQL aggregations, fired together in a single round-trip group.
    // This is everything the default (gráficas) view needs, so first paint
    // waits only on these — not on the slow yfinance call above.
    try {
      const [
        dashData,
        casData,
        divData,
        gainsData,
        divC,
        divM,
        topP,
        gainsB,
        patrim,
        withh,
        compDiv,
      ] = await Promise.all([
        api.dashboard(y) as Promise<DashboardStats>,
        api.casillas(y) as Promise<Casilla[]>,
        api.dividends(y) as Promise<DividendSummary[]>,
        api.capitalGains(y) as Promise<CapitalGain[]>,
        api.charts.dividendsByCountry(y) as Promise<DividendsByCountry[]>,
        api.charts.dividendsMonthly(y) as Promise<DividendsMonthly[]>,
        api.charts.topDividendPayers(y) as Promise<TopDividendPayer[]>,
        api.charts.capitalGainsBreakdown(y) as Promise<CapitalGainsBreakdown[]>,
        api.charts.patrimonioComposition(y) as Promise<PatrimonioComposition[]>,
        api.charts.withholdingsByCountry(y) as Promise<WithholdingsByCountry[]>,
        api.charts.dividendsByCompanyYearly() as Promise<
          CompanyDividendsYearly[]
        >,
      ]);
      if (!isCurrent()) return;
      setStats(dashData);
      setCasillas(casData);
      setDividends(divData);
      setGains(gainsData);
      setDivByCountry(divC);
      setDivMonthly(divM);
      setTopPayers(topP);
      setGainsBreakdown(gainsB);
      setPatrimonio(patrim);
      setWithholdings(withh);
      setCompanyDividends(compDiv);
    } catch (e) {
      console.error("Error loading data:", e);
      if (isCurrent())
        setError("No se pudieron cargar los datos del dashboard. Comprueba tu conexión e inténtalo de nuevo.");
    } finally {
      if (isCurrent()) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(selectedYear);
  }, [loadData, selectedYear]);

  // N2: navigate to ?view=importar from QuickNav or external link.
  // Search param (not hash): useSearchParams re-renders on router.push even when
  // the page is already mounted; pushState never fires hashchange.
  useEffect(() => {
    if (searchParams.get("view") === "importar") {
      setView("importar");
      const params = new URLSearchParams(window.location.search);
      params.delete("view");
      const qs = params.toString();
      window.history.replaceState(null, "", window.location.pathname + (qs ? `?${qs}` : ""));
    }
  }, [searchParams]);

  const showFiscal = selectedYear !== null;

  // Reset to non-fiscal view when switching to "Todos los años"
  useEffect(() => {
    if (
      !showFiscal &&
      (view === "casillas" || view === "ganancias" || view === "declaracion")
    ) {
      setView("graficas");
    }
  }, [showFiscal, view]);

  // Clear country filter when year changes
  useEffect(() => { setFilterCountry(null); }, [selectedYear]);

  const hasData = stats && stats.total_transactions > 0;

  const fiscalYears = stats?.fiscal_years ?? [];

  return (
    <div className="space-y-6 p-3 sm:p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <BarChart3 className="h-6 w-6" />
            Dashboard
          </h1>
          <p className="text-muted-foreground">
            Resumen fiscal y de dividendos de tu cartera
          </p>
        </div>
        <div className="flex items-center gap-2">
          {fiscalYears.length > 0 && (
            <select
              aria-label="Seleccionar año fiscal"
              value={selectedYear ?? ""}
              onChange={(e) => {
                const year = e.target.value ? Number(e.target.value) : null;
                // Sync reset: fiscal tabs unmount with the year, so leave them
                // before paint instead of waiting for the effect below.
                if (
                  year === null &&
                  (view === "casillas" || view === "ganancias" || view === "declaracion")
                ) {
                  setView("graficas");
                }
                setSelectedYear(year);
              }}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">Todos los años</option>
              {fiscalYears.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={togglePrivacy}
            aria-pressed={privacy}
            title={privacy ? "Mostrar importes" : "Ocultar importes"}
            aria-label={privacy ? "Mostrar importes" : "Ocultar importes"}
          >
            {privacy ? (
              <EyeOff className="h-4 w-4" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => (window.location.href = "/billing")}
            title="Facturación"
            aria-label="Facturación"
          >
            <CreditCard className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => {
              clearAuthToken();
              invalidateCache();
              signOut({ callbackUrl: "/login" });
            }}
            title="Cerrar sesión"
            aria-label="Cerrar sesión"
          >
            <LogOut className="h-4 w-4" />
          </Button>
          <QuickNav current="/dashboard" />
        </div>
      </div>

      {/* View tabs — same pattern as /options */}
      <Tabs value={view} onValueChange={(v) => setView(v as View)}>
        <div className="w-full overflow-x-auto">
          <TabsList className="w-full sm:w-auto">
            <TabsTrigger value="graficas" aria-label="Dashboard">
              <BarChart3 className="h-4 w-4 sm:mr-1" />
              <span className="hidden sm:inline">Dashboard</span>
            </TabsTrigger>
            <TabsTrigger value="rendimiento" aria-label="Rendimiento">
              <TrendingUp className="h-4 w-4 sm:mr-1" />
              <span className="hidden sm:inline">Rendimiento</span>
            </TabsTrigger>
            <TabsTrigger value="dividendos" aria-label="Dividendos">
              <Coins className="h-4 w-4 sm:mr-1" />
              <span className="hidden sm:inline">Dividendos</span>
              {hasData && !loading && dividends.length > 0 && (
                <Badge
                  variant="secondary"
                  className="ml-1 px-1.5 py-0.5 text-xs tabular-nums"
                >
                  {dividends.length}
                </Badge>
              )}
            </TabsTrigger>
            {showFiscal && (
              <>
                <TabsTrigger value="casillas" aria-label="Casillas fiscales">
                  <FileText className="h-4 w-4 sm:mr-1" />
                  <span className="hidden sm:inline">Casillas</span>
                </TabsTrigger>
                <TabsTrigger value="ganancias" aria-label="Ganancias de capital">
                  <LineChart className="h-4 w-4 sm:mr-1" />
                  <span className="hidden sm:inline">Ganancias</span>
                </TabsTrigger>
                <TabsTrigger value="declaracion" aria-label="Mi declaración">
                  <Calculator className="h-4 w-4 sm:mr-1" />
                  <span className="hidden sm:inline">Mi declaración</span>
                </TabsTrigger>
              </>
            )}
            <TabsTrigger value="comparativa" aria-label="Comparativa anual">
              <CalendarRange className="h-4 w-4 sm:mr-1" />
              <span className="hidden sm:inline">Comparativa</span>
            </TabsTrigger>
            <TabsTrigger value="importar" aria-label="Importar datos">
              <UploadIcon className="h-4 w-4 sm:mr-1" />
              <span className="hidden sm:inline">Importar</span>
            </TabsTrigger>
          </TabsList>
        </div>
      </Tabs>

      {/* Content */}
      <main data-privacy={privacy ? "true" : "false"}>
          {/* Import view */}
          {view === "importar" && (
            <div className="max-w-3xl mx-auto space-y-6">
              <FileUpload
                onImported={() => {
                  loadData(selectedYear);
                  setImportRefreshKey((k) => k + 1);
                }}
              />
              <ImportedFilesList
                key={importRefreshKey}
                onDeleted={() => {
                  loadData(selectedYear);
                  setImportRefreshKey((k) => k + 1);
                }}
              />
            </div>
          )}

          {/* Loading state */}
          {view !== "importar" && loading && <DashboardSkeleton />}

          {/* Error state */}
          {view !== "importar" && !loading && error && (
            <ErrorState
              message={error}
              onRetry={() => loadData(selectedYear)}
            />
          )}

          {/* No data state */}
          {view !== "importar" && !loading && !hasData && (
            <EmptyState
              icon={UploadIcon}
              title="No hay datos importados"
              description="Sube un informe de Trade Republic, DEGIRO, IBKR, ING, BBVA o eToro para empezar."
            />
          )}

          {/* Dashboard (charts + stats) */}
          {view === "graficas" && hasData && (
            <div className="space-y-6">
              {/* C4: fiscal year context label */}
              {showFiscal && (
                <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <Info className="h-3.5 w-3.5 shrink-0" />
                  Datos del año fiscal {selectedYear}
                </div>
              )}
              <StatsCards
                stats={stats}
                withholdings={withholdings}
                showFiscal={showFiscal}
              />
              <div
                className={`grid grid-cols-1 ${showFiscal ? "lg:grid-cols-2" : ""} gap-6`}
              >
                <div className="space-y-2">
                  <DividendsByCountryChart
                    data={divByCountry}
                    activeCountry={filterCountry}
                    onCountryClick={setFilterCountry}
                  />
                  {filterCountry && (
                    <div className="flex items-center gap-2 px-1 text-sm">
                      <span className="text-muted-foreground">Filtro activo:</span>
                      <Badge variant="secondary" className="gap-1">
                        {filterCountry}
                        <button
                          onClick={() => setFilterCountry(null)}
                          className="ml-0.5 opacity-60 hover:opacity-100"
                          aria-label="Quitar filtro"
                        >
                          ×
                        </button>
                      </Badge>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-xs"
                        onClick={() => setView("dividendos")}
                      >
                        Ver dividendos →
                      </Button>
                    </div>
                  )}
                </div>
                {showFiscal && <PatrimonioChart data={patrimonio} />}
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <DividendsMonthlyChart data={divMonthly} />
                <GrossDividendsByCountryChart data={divByCountry} />
              </div>
              <div
                className={`grid grid-cols-1 ${showFiscal ? "lg:grid-cols-2" : ""} gap-6`}
              >
                {showFiscal && <WithholdingsChart data={withholdings} />}
                <TopPayersChart data={topPayers} />
              </div>
              {showFiscal && <CapitalGainsChart data={gainsBreakdown} />}
              {!showFiscal && <CompanyDividendsChart data={companyDividends} />}
            </div>
          )}

          {/* Rendimiento */}
          {view === "rendimiento" &&
            hasData &&
            (secondaryLoading && dividendYield.length === 0 ? (
              <DashboardSkeleton />
            ) : dividendYield.length > 0 ? (
              <DividendYieldTable data={dividendYield} />
            ) : (
              <EmptyState
                icon={TrendingUp}
                title="Sin datos de rendimiento"
                description="Importa datos con dividendos para ver el rendimiento de tu cartera."
              />
            ))}

          {/* Casillas */}
          {view === "casillas" &&
            hasData &&
            (casillas.length > 0 ? (
              <>
                <IrpfSummary casillas={casillas} />
                <CasillasTable
                  casillas={casillas}
                  dividendsByCountry={divByCountry}
                  fiscalYear={selectedYear}
                />
              </>
            ) : (
              <EmptyState
                icon={FileText}
                title="Sin casillas fiscales"
                description="Selecciona un año fiscal con datos importados para ver las casillas."
              />
            ))}

          {/* Mi declaración — estimación base del ahorro */}
          {view === "declaracion" && hasData && selectedYear !== null && (
            <DeclaracionView fiscalYear={selectedYear} />
          )}

          {/* Dividendos */}
          {view === "dividendos" &&
            hasData &&
            (dividends.length > 0 ? (
              <>
                {filterCountry && (
                  <div className="flex items-center gap-2 mb-4 text-sm">
                    <span className="text-muted-foreground">País:</span>
                    <Badge variant="secondary" className="gap-1">
                      {filterCountry}
                      <button
                        onClick={() => setFilterCountry(null)}
                        className="ml-0.5 opacity-60 hover:opacity-100"
                        aria-label="Quitar filtro"
                      >
                        ×
                      </button>
                    </Badge>
                  </div>
                )}
                <DividendsTable
                  dividends={filterCountry ? dividends.filter((d) => d.country === filterCountry) : dividends}
                  dividendYield={dividendYield}
                />
              </>
            ) : (
              <EmptyState
                icon={Coins}
                title="Sin dividendos"
                description="No se encontraron dividendos para el periodo seleccionado."
              />
            ))}

          {/* Ganancias */}
          {view === "ganancias" &&
            hasData &&
            (gains.length > 0 ? (
              <>
                <IrpfSummary casillas={casillas} />
                <CapitalGainsTable
                  gains={gains}
                  crossBrokerLots={crossBrokerLots}
                  fifoAdjustments={fifoAdjustments}
                  optionAssignments={optionAssignments}
                />
              </>
            ) : (
              <EmptyState
                icon={LineChart}
                title="Sin ganancias de capital"
                description="No se encontraron operaciones de compra/venta para el periodo seleccionado."
              />
            ))}

          {/* Comparativa anual */}
          {view === "comparativa" &&
            hasData &&
            (secondaryLoading && yearlyComparison.length === 0 ? (
              <DashboardSkeleton />
            ) : yearlyComparison.length > 0 ? (
              <YearlyComparisonView
                data={yearlyComparison}
                onYearSelect={(year) => { setSelectedYear(year); setView("graficas"); }}
              />
            ) : (
              <EmptyState
                icon={CalendarRange}
                title="Sin datos para comparar"
                description="Importa datos de varios años fiscales para ver la comparativa anual."
              />
            ))}
        </main>
    </div>
  );
}
