import {
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
  Wallet,
  PieChart,
  BarChart3,
} from "lucide-react";

import { fmt } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingDots } from "@/components/loading-dots";

import type { Summary } from "./types";

interface PortfolioSummaryCardsProps {
  summary: Summary;
  pricesLoaded: boolean;
}

// Totals are fail-closed upstream: a null `unrealized_pl` / `total_market_value`
// means the backend refused to publish a partial figure, and the cards render
// "—" plus the reason instead of a subtotal.
export function PortfolioSummaryCards({ summary, pricesLoaded }: PortfolioSummaryCardsProps) {
  const plKnown = summary.unrealized_pl != null;
  const plPositive = (summary.unrealized_pl ?? 0) >= 0;
  const plColor = !plKnown
    ? "text-muted-foreground"
    : plPositive
      ? "text-emerald-600"
      : "text-red-600";
  const PlIcon = plPositive ? ArrowUpRight : ArrowDownRight;

  return (
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
              <div className="text-2xl font-bold fv-sensitive">
                {summary.total_market_value != null ? `${fmt(summary.total_market_value)} €` : "—"}
              </div>
              <p className="text-xs text-muted-foreground">
                {summary.valuation_complete ? (
                  <>Invertido: <span className="fv-sensitive">{summary.total_invested != null ? `${fmt(summary.total_invested)} €` : "—"}</span></>
                ) : (
                  "Valoración incompleta"
                )}
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
              <div className={`text-2xl font-bold fv-sensitive ${plColor}`}>
                {plKnown && plPositive ? "+" : ""}
                {plKnown ? `${fmt(summary.unrealized_pl)} €` : "—"}
              </div>
              <p className={`text-xs ${plColor}`}>
                {plKnown && plPositive ? "+" : ""}
                {plKnown
                  ? `${fmt(summary.unrealized_pl_pct)}%`
                  : !summary.cost_basis_complete
                    ? "Coste incompleto"
                    : "Valoración incompleta"}
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
          <div className="text-2xl font-bold fv-sensitive">
            {summary.total_invested != null ? `${fmt(summary.total_invested)} €` : "—"}
          </div>
          <p className="text-xs text-muted-foreground">
            {summary.cost_basis_complete ? "Coste base total" : "Coste incompleto"}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
