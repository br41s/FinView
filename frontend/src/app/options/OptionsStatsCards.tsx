import { Activity, BarChart3, Bell, TrendingUp, Zap } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fmtDateTime } from "@/lib/format";

import type { AgentStatus, Snapshot } from "./types";

/**
 * The five stat cards under the Options Monitor header.
 *
 * Each card has a one-line mobile row (`sm:hidden`) and the icon+title desktop
 * card (`hidden sm:flex/block`). Moved out of page.tsx unchanged. The shared
 * `StatCard` in components/StatsCards.tsx renders a different card (single
 * label/value pair, no icon, no mobile variant), so it is not reused here.
 */

// Global P/C sentiment — average put_call_ratio_volume across all latest snapshots
function globalPCSentiment(latestSnapshots: readonly Snapshot[]) {
  const ratios = latestSnapshots
    .map((s) => (s.put_call_ratio_volume != null ? Number(s.put_call_ratio_volume) : null))
    .filter((v): v is number => v !== null && !isNaN(v));
  if (ratios.length === 0) return null;
  const avg = ratios.reduce((a, b) => a + b, 0) / ratios.length;
  const label = avg < 0.7 ? "Alcista" : avg > 1.0 ? "Bajista" : "Neutral";
  const color = avg < 0.7 ? "text-emerald-600" : avg > 1.0 ? "text-red-600" : "text-amber-500";
  return { avg, label, color, count: ratios.length };
}

export interface OptionsStatsCardsProps {
  positionsCount: number;
  watchlistCount: number;
  agentStatus: AgentStatus | null;
  alertsTotal: number;
  unreadCount: number;
  unusualCount: number;
  /** Latest snapshot per ticker — the P/C average is taken over these. */
  latestSnapshots: readonly Snapshot[];
}

export function OptionsStatsCards({
  positionsCount,
  watchlistCount,
  agentStatus,
  alertsTotal,
  unreadCount,
  unusualCount,
  latestSnapshots,
}: OptionsStatsCardsProps) {
  const globalPC = globalPCSentiment(latestSnapshots);

  return (
    <div className="grid gap-2 sm:gap-4 sm:grid-cols-2 lg:grid-cols-5">
      <Card>
        <div className="flex items-center justify-between px-4 py-3 sm:hidden">
          <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Posiciones</span> en cartera · {watchlistCount} en watchlist</p>
          <span className="ml-3 shrink-0 text-base font-bold">{positionsCount}</span>
        </div>
        <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
          <CardTitle className="text-sm font-medium">Posiciones</CardTitle>
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent className="hidden sm:block">
          <div className="text-2xl font-bold">{positionsCount}</div>
          <p className="text-xs text-muted-foreground">en cartera · {watchlistCount} en watchlist</p>
        </CardContent>
      </Card>
      <Card>
        <div className="flex items-center justify-between px-4 py-3 sm:hidden">
          <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Ciclos</span>{" "}{agentStatus?.last_cycle ? `último ${new Date(agentStatus.last_cycle).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}` : "sin ciclos aún"}</p>
          <span className="ml-3 shrink-0 text-base font-bold">{agentStatus?.total_cycles ?? 0}</span>
        </div>
        <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
          <CardTitle className="text-sm font-medium">Ciclos</CardTitle>
          <Activity className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent className="hidden sm:block">
          <div className="text-2xl font-bold">{agentStatus?.total_cycles ?? 0}</div>
          <p className="text-xs text-muted-foreground">{agentStatus?.last_cycle ? `Último: ${fmtDateTime(agentStatus.last_cycle)}` : "Sin ciclos aún"}</p>
        </CardContent>
      </Card>
      <Card>
        <div className="flex items-center justify-between px-4 py-3 sm:hidden">
          <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Alertas</span> {alertsTotal} total (7d)</p>
          <span className="ml-3 shrink-0 text-base font-bold">{unreadCount}</span>
        </div>
        <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
          <CardTitle className="text-sm font-medium">Alertas</CardTitle>
          <Bell className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent className="hidden sm:block">
          <div className="text-2xl font-bold">{unreadCount}</div>
          <p className="text-xs text-muted-foreground">{alertsTotal} total (7d)</p>
        </CardContent>
      </Card>
      <Card>
        <div className="flex items-center justify-between px-4 py-3 sm:hidden">
          <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Smart Money</span> actividad inusual (7d)</p>
          <span className="ml-3 shrink-0 text-base font-bold">{unusualCount}</span>
        </div>
        <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
          <CardTitle className="text-sm font-medium">Smart Money</CardTitle>
          <Zap className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent className="hidden sm:block">
          <div className="text-2xl font-bold">{unusualCount}</div>
          <p className="text-xs text-muted-foreground">Actividad inusual (7d)</p>
        </CardContent>
      </Card>
      <Card>
        <div className="flex items-center justify-between px-4 py-3 sm:hidden">
          <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Sentimiento</span> P/C {globalPC ? `${globalPC.avg.toFixed(2)} · ${globalPC.count} tickers` : "—"}</p>
          <span className={`ml-3 shrink-0 text-base font-bold ${globalPC?.color ?? "text-muted-foreground"}`}>{globalPC?.label ?? "—"}</span>
        </div>
        <CardHeader className="hidden flex-row items-center justify-between pb-2 sm:flex">
          <CardTitle className="text-sm font-medium">Sentimiento P/C</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent className="hidden sm:block">
          {globalPC ? (
            <>
              <div className={`text-2xl font-bold ${globalPC.color}`}>{globalPC.label}</div>
              <p className="text-xs text-muted-foreground">P/C medio {globalPC.avg.toFixed(2)} · {globalPC.count} tickers</p>
            </>
          ) : (
            <>
              <div className="text-2xl font-bold text-muted-foreground">—</div>
              <p className="text-xs text-muted-foreground">Sin datos aún</p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
