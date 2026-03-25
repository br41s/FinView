"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  DashboardStats,
  Casilla,
  DividendSummary,
  CapitalGain,
} from "@/lib/types";
import { FileUpload } from "@/components/FileUpload";
import { StatsCards } from "@/components/StatsCards";
import { CasillasTable } from "@/components/CasillasTable";
import { DividendsTable } from "@/components/DividendsTable";
import { CapitalGainsTable } from "@/components/CapitalGainsTable";

type Tab = "casillas" | "dividendos" | "ganancias";

export default function Home() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [casillas, setCasillas] = useState<Casilla[]>([]);
  const [dividends, setDividends] = useState<DividendSummary[]>([]);
  const [gains, setGains] = useState<CapitalGain[]>([]);
  const [tab, setTab] = useState<Tab>("casillas");
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [dashData, casData, divData, gainsData] = await Promise.all([
        api.dashboard() as Promise<DashboardStats>,
        api.casillas() as Promise<Casilla[]>,
        api.dividends() as Promise<DividendSummary[]>,
        api.capitalGains() as Promise<CapitalGain[]>,
      ]);
      setStats(dashData);
      setCasillas(casData);
      setDividends(divData);
      setGains(gainsData);
    } catch (e) {
      console.error("Error loading data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: "casillas", label: "Casillas fiscales", count: casillas.length },
    { key: "dividendos", label: "Dividendos", count: dividends.length },
    { key: "ganancias", label: "Ganancias de capital", count: gains.length },
  ];

  return (
    <main className="min-h-screen bg-[var(--bg)] text-neutral-100">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">FinView</h1>
            <p className="text-sm text-neutral-500">Dashboard fiscal de inversiones</p>
          </div>
          {stats && stats.fiscal_years.length > 0 && (
            <div className="text-sm text-neutral-400">
              Años fiscales: {stats.fiscal_years.join(", ")}
            </div>
          )}
        </div>

        {/* Upload */}
        <section className="mb-8">
          <FileUpload onImported={loadData} />
        </section>

        {/* Stats */}
        {loading && !stats && (
          <p className="text-neutral-500 text-center py-8 animate-pulse">Cargando datos...</p>
        )}

        {stats && stats.total_transactions > 0 && (
          <>
            <section className="mb-8">
              <StatsCards stats={stats} />
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
                    <span className="ml-2 text-xs bg-neutral-800 px-2 py-0.5 rounded-full">
                      {t.count}
                    </span>
                  </button>
                ))}
              </nav>
            </div>

            {/* Tab content */}
            <section className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
              {tab === "casillas" && <CasillasTable casillas={casillas} />}
              {tab === "dividendos" && <DividendsTable dividends={dividends} />}
              {tab === "ganancias" && <CapitalGainsTable gains={gains} />}
            </section>
          </>
        )}

        {stats && stats.total_transactions === 0 && (
          <p className="text-center text-neutral-500 py-12">
            No hay datos importados. Sube un PDF de Trade Republic para empezar.
          </p>
        )}
      </div>
    </main>
  );
}
