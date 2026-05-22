"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
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
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingDots } from "@/components/loading-dots";
import { AppSidebar, type View } from "@/components/app-sidebar";
import { FileUpload } from "@/components/FileUpload";
import { ImportedFilesList } from "@/components/ImportedFilesList";
import { StatsCards } from "@/components/StatsCards";
import { CasillasTable } from "@/components/CasillasTable";
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
  TrendingUp,
  Coins,
  FileText,
  LineChart,
  CalendarRange,
  AlertCircle,
} from "lucide-react";

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

const viewTitles: Record<View, string> = {
  graficas: "Dashboard",
  rendimiento: "Rendimiento",
  casillas: "Casillas fiscales",
  dividendos: "Dividendos",
  ganancias: "Ganancias de capital",
  comparativa: "Comparativa anual",
  importar: "Importar datos",
};

export default function Home() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [casillas, setCasillas] = useState<Casilla[]>([]);
  const [dividends, setDividends] = useState<DividendSummary[]>([]);
  const [gains, setGains] = useState<CapitalGain[]>([]);
  const [view, setView] = useState<View>("graficas");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importRefreshKey, setImportRefreshKey] = useState(0);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

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

  const loadData = useCallback(async (year?: number | null) => {
    setLoading(true);
    setError(null);
    const y = year ?? undefined;

    // Fire-and-forget: warm price cache in background so portfolio/options load fast
    api.portfolio.warmPrices();

    try {
      const [dashData, casData, divData, gainsData] = await Promise.all([
        api.dashboard(y) as Promise<DashboardStats>,
        api.casillas(y) as Promise<Casilla[]>,
        api.dividends(y) as Promise<DividendSummary[]>,
        api.capitalGains(y) as Promise<CapitalGain[]>,
      ]);
      setStats(dashData);
      setCasillas(casData);
      setDividends(divData);
      setGains(gainsData);

      if (y) {
        const [cblData, adjData, assignData] = await Promise.all([
          api.crossBrokerLots(y) as Promise<CrossBrokerLot[]>,
          api.fifoAdjustments(y) as Promise<FIFOAdjustment[]>,
          api.optionAssignments(y) as Promise<OptionAssignment[]>,
        ]);
        setCrossBrokerLots(cblData);
        setFifoAdjustments(adjData);
        setOptionAssignments(assignData);
      } else {
        setCrossBrokerLots([]);
        setFifoAdjustments([]);
        setOptionAssignments([]);
      }

      const [divC, divM, topP, gainsB, patrim, divY, withh, compDiv, ycData] =
        await Promise.all([
          api.charts.dividendsByCountry(y) as Promise<DividendsByCountry[]>,
          api.charts.dividendsMonthly(y) as Promise<DividendsMonthly[]>,
          api.charts.topDividendPayers(y) as Promise<TopDividendPayer[]>,
          api.charts.capitalGainsBreakdown(y) as Promise<
            CapitalGainsBreakdown[]
          >,
          api.charts.patrimonioComposition(y) as Promise<
            PatrimonioComposition[]
          >,
          api.charts.dividendYield(y) as Promise<DividendYield[]>,
          api.charts.withholdingsByCountry(y) as Promise<
            WithholdingsByCountry[]
          >,
          api.charts.dividendsByCompanyYearly() as Promise<
            CompanyDividendsYearly[]
          >,
          api.yearlyComparison() as Promise<{ years: YearlyMetrics[] }>,
        ]);
      setDivByCountry(divC);
      setDivMonthly(divM);
      setTopPayers(topP);
      setGainsBreakdown(gainsB);
      setPatrimonio(patrim);
      setDividendYield(divY);
      setWithholdings(withh);
      setCompanyDividends(compDiv);
      setYearlyComparison(ycData.years);
    } catch (e) {
      console.error("Error loading data:", e);
      setError("No se pudieron cargar los datos del dashboard. Comprueba tu conexión e inténtalo de nuevo.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(selectedYear);
  }, [loadData, selectedYear]);

  const showFiscal = selectedYear !== null;

  // Reset to non-fiscal view when switching to "Todos los años"
  useEffect(() => {
    if (!showFiscal && (view === "casillas" || view === "ganancias")) {
      setView("graficas");
    }
  }, [showFiscal, view]);

  const counts = {
    rendimiento: dividendYield.filter(
      (d) => Number.parseFloat(d.yield_on_cost) > 0,
    ).length,
    casillas: casillas.length,
    dividendos: dividends.length,
    ganancias: gains.length,
  };

  const hasData = stats && stats.total_transactions > 0;

  return (
    <SidebarProvider>
      <AppSidebar
        currentView={view}
        onViewChange={setView}
        selectedYear={selectedYear}
        onYearChange={setSelectedYear}
        fiscalYears={stats?.fiscal_years ?? []}
        counts={hasData ? counts : undefined}
      />
      <SidebarInset>
        {/* Header */}
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4!" />
          <h1 className="text-sm font-medium">{viewTitles[view]}</h1>
          <div className="ml-auto flex items-center gap-2">
            {selectedYear && (
              <span className="text-xs text-muted-foreground">
                Año fiscal {selectedYear}
              </span>
            )}
            <QuickNav current="/dashboard" />
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-3 sm:p-6">
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
              <StatsCards
                stats={stats}
                withholdings={withholdings}
                showFiscal={showFiscal}
              />
              <div
                className={`grid grid-cols-1 ${showFiscal ? "lg:grid-cols-2" : ""} gap-6`}
              >
                <DividendsByCountryChart data={divByCountry} />
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
            (dividendYield.length > 0 ? (
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
              <CasillasTable
                casillas={casillas}
                dividendsByCountry={divByCountry}
                fiscalYear={selectedYear}
              />
            ) : (
              <EmptyState
                icon={FileText}
                title="Sin casillas fiscales"
                description="Selecciona un año fiscal con datos importados para ver las casillas."
              />
            ))}

          {/* Dividendos */}
          {view === "dividendos" &&
            hasData &&
            (dividends.length > 0 ? (
              <DividendsTable dividends={dividends} dividendYield={dividendYield} />
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
              <CapitalGainsTable
                gains={gains}
                crossBrokerLots={crossBrokerLots}
                fifoAdjustments={fifoAdjustments}
                optionAssignments={optionAssignments}
              />
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
            (yearlyComparison.length > 0 ? (
              <YearlyComparisonView data={yearlyComparison} />
            ) : (
              <EmptyState
                icon={CalendarRange}
                title="Sin datos para comparar"
                description="Importa datos de varios años fiscales para ver la comparativa anual."
              />
            ))}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
