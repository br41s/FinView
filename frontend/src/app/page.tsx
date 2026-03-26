"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  DashboardStats,
  Casilla,
  DividendSummary,
  CapitalGain,
  DividendsByCountry,
  DividendsMonthly,
  TopDividendPayer,
  CapitalGainsBreakdown,
  PatrimonioComposition,
  DividendYield,
  WithholdingsByCountry,
  CompanyDividendsYearly,
} from "@/lib/types";
import { FileUpload } from "@/components/FileUpload";
import { StatsCards } from "@/components/StatsCards";
import { CasillasTable } from "@/components/CasillasTable";
import { DividendsTable } from "@/components/DividendsTable";
import { CapitalGainsTable } from "@/components/CapitalGainsTable";
import { DividendYieldTable } from "@/components/DividendYieldTable";
import { DividendsByCountryChart } from "@/components/charts/DividendsByCountryChart";
import { DividendsMonthlyChart } from "@/components/charts/DividendsMonthlyChart";
import { TopPayersChart } from "@/components/charts/TopPayersChart";
import { CapitalGainsChart } from "@/components/charts/CapitalGainsChart";
import { PatrimonioChart } from "@/components/charts/PatrimonioChart";
import { WithholdingsChart } from "@/components/charts/WithholdingsChart";
import { GrossDividendsByCountryChart } from "@/components/charts/GrossDividendsByCountryChart";
import { CompanyDividendsChart } from "@/components/charts/CompanyDividendsChart";

type Tab = "graficas" | "rendimiento" | "casillas" | "dividendos" | "ganancias";

export default function Home() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [casillas, setCasillas] = useState<Casilla[]>([]);
  const [dividends, setDividends] = useState<DividendSummary[]>([]);
  const [gains, setGains] = useState<CapitalGain[]>([]);
  const [tab, setTab] = useState<Tab>("graficas");
  const [loading, setLoading] = useState(true);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

  // Chart data
  const [divByCountry, setDivByCountry] = useState<DividendsByCountry[]>([]);
  const [divMonthly, setDivMonthly] = useState<DividendsMonthly[]>([]);
  const [topPayers, setTopPayers] = useState<TopDividendPayer[]>([]);
  const [gainsBreakdown, setGainsBreakdown] = useState<CapitalGainsBreakdown[]>([]);
  const [patrimonio, setPatrimonio] = useState<PatrimonioComposition[]>([]);
  const [dividendYield, setDividendYield] = useState<DividendYield[]>([]);
  const [withholdings, setWithholdings] = useState<WithholdingsByCountry[]>([]);
  const [companyDividends, setCompanyDividends] = useState<CompanyDividendsYearly[]>([]);

  const loadData = useCallback(async (year?: number | null) => {
    setLoading(true);
    const y = year ?? undefined;
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

      // Load chart data in parallel
      const [divC, divM, topP, gainsB, patrim, divY, withh, compDiv] = await Promise.all([
        api.charts.dividendsByCountry(y) as Promise<DividendsByCountry[]>,
        api.charts.dividendsMonthly(y) as Promise<DividendsMonthly[]>,
        api.charts.topDividendPayers(y) as Promise<TopDividendPayer[]>,
        api.charts.capitalGainsBreakdown(y) as Promise<CapitalGainsBreakdown[]>,
        api.charts.patrimonioComposition(y) as Promise<PatrimonioComposition[]>,
        api.charts.dividendYield(y) as Promise<DividendYield[]>,
        api.charts.withholdingsByCountry(y) as Promise<WithholdingsByCountry[]>,
        api.charts.dividendsByCompanyYearly() as Promise<CompanyDividendsYearly[]>,
      ]);
      setDivByCountry(divC);
      setDivMonthly(divM);
      setTopPayers(topP);
      setGainsBreakdown(gainsB);
      setPatrimonio(patrim);
      setDividendYield(divY);
      setWithholdings(withh);
      setCompanyDividends(compDiv);
    } catch (e) {
      console.error("Error loading data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(selectedYear);
  }, [loadData, selectedYear]);

  const showFiscal = selectedYear !== null;

  // Reset to non-fiscal tab when switching to "Todos los años"
  useEffect(() => {
    if (!showFiscal && (tab === "casillas" || tab === "ganancias")) {
      setTab("graficas");
    }
  }, [showFiscal, tab]);

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "graficas", label: "Gráficas" },
    { key: "rendimiento", label: "Rendimiento", count: dividendYield.filter(d => Number.parseFloat(d.yield_on_cost) > 0).length },
    ...(showFiscal ? [{ key: "casillas" as Tab, label: "Casillas fiscales", count: casillas.length }] : []),
    { key: "dividendos", label: "Dividendos", count: dividends.length },
    ...(showFiscal ? [{ key: "ganancias" as Tab, label: "Ganancias de capital", count: gains.length }] : []),
  ];

  return (
    <main className="min-h-screen bg-(--bg) text-neutral-100">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">FinView</h1>
            <p className="text-sm text-neutral-500">Dashboard fiscal de inversiones</p>
          </div>
          {(stats?.fiscal_years?.length ?? 0) > 0 && (
            <select
              aria-label="Seleccionar año fiscal"
              value={selectedYear ?? ""}
              onChange={(e) =>
                setSelectedYear(e.target.value ? Number(e.target.value) : null)
              }
              className="bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-blue-500"
            >
              <option value="">Todos los años</option>
              {stats?.fiscal_years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Upload */}
        <section className="mb-8">
          <FileUpload onImported={() => loadData(selectedYear)} />
        </section>

        {/* Stats */}
        {loading && !stats && (
          <p className="text-neutral-500 text-center py-8 animate-pulse">Cargando datos...</p>
        )}

        {stats && stats.total_transactions > 0 && (
          <>
            <section className="mb-8">
              <StatsCards stats={stats} withholdings={withholdings} showFiscal={showFiscal} />
            </section>

            {/* Tabs */}
            <div className="border-b border-neutral-800 mb-6">
              <nav className="flex gap-6">
                {tabs.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                      tab === t.key
                        ? "border-blue-500 text-blue-400"
                        : "border-transparent text-neutral-500 hover:text-neutral-300"
                    }`}
                  >
                    {t.label}
                    {t.count !== undefined && (
                      <span className="ml-2 text-xs bg-neutral-800 px-2 py-0.5 rounded-full">
                        {t.count}
                      </span>
                    )}
                  </button>
                ))}
              </nav>
            </div>

            {/* Tab content */}
            {tab === "graficas" && (
              <section className="space-y-6">
                {/* Row 1: Dividends by country (donut) + Patrimonio (fiscal) */}
                <div className={`grid grid-cols-1 ${showFiscal ? "lg:grid-cols-2" : ""} gap-6`}>
                  <DividendsByCountryChart data={divByCountry} />
                  {showFiscal && <PatrimonioChart data={patrimonio} />}
                </div>
                {/* Row 2: Monthly + Gross dividends by country (bar) */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <DividendsMonthlyChart data={divMonthly} />
                  <GrossDividendsByCountryChart data={divByCountry} />
                </div>
                {/* Row 3: Retenciones (fiscal) + Top payers */}
                <div className={`grid grid-cols-1 ${showFiscal ? "lg:grid-cols-2" : ""} gap-6`}>
                  {showFiscal && <WithholdingsChart data={withholdings} />}
                  <TopPayersChart data={topPayers} />
                </div>
                {/* Row 4: Capital gains (fiscal) */}
                {showFiscal && (
                  <div>
                    <CapitalGainsChart data={gainsBreakdown} />
                  </div>
                )}
                {/* Row 5: Company dividends over time (full width) */}
                <CompanyDividendsChart data={companyDividends} />
              </section>
            )}

            {tab === "rendimiento" && <DividendYieldTable data={dividendYield} />}

            <section className={tab === "graficas" || tab === "rendimiento" ? "hidden" : "bg-neutral-900 border border-neutral-800 rounded-xl p-6"}>
              {tab === "casillas" && <CasillasTable casillas={casillas} dividendsByCountry={divByCountry} />}
              {tab === "dividendos" && <DividendsTable dividends={dividends} />}
              {tab === "ganancias" && <CapitalGainsTable gains={gains} />}
            </section>
          </>
        )}

        {stats?.total_transactions === 0 && (
          <p className="text-center text-neutral-500 py-12">
            No hay datos importados. Sube un PDF de Trade Republic o DEGIRO para empezar.
          </p>
        )}
      </div>
    </main>
  );
}
