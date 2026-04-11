"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
  Wallet,
  PieChart,
  BarChart3,
  ArrowLeft,
} from "lucide-react";

import { api } from "@/lib/api";
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

interface Position {
  isin: string;
  ticker: string | null;
  name: string;
  country: string | null;
  broker: string;
  quantity: number;
  avg_cost_eur: number;
  total_cost_eur: number;
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

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("es-ES", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function PortfolioContent() {
  const router = useRouter();
  const [positions, setPositions] = useState<Position[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [pos, sum] = await Promise.all([
          api.portfolio.positions() as Promise<Position[]>,
          api.portfolio.summary() as Promise<Summary>,
        ]);
        setPositions(pos);
        setSummary(sum);
      } catch (e) {
        console.error("Failed to load portfolio:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-96" />
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Cartera</h1>
          <p className="text-muted-foreground">
            Posiciones abiertas con precios en tiempo real
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => router.push("/accounts")}>
            Cuentas
          </Button>
          <Button variant="outline" onClick={() => router.push("/")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Dashboard fiscal
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
              <div className="text-2xl font-bold">
                {fmt(summary.total_market_value)} €
              </div>
              <p className="text-xs text-muted-foreground">
                Invertido: {fmt(summary.total_invested)} €
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">
                Rentabilidad
              </CardTitle>
              <PlIcon className={`h-4 w-4 ${plColor}`} />
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${plColor}`}>
                {summary.unrealized_pl >= 0 ? "+" : ""}
                {fmt(summary.unrealized_pl)} €
              </div>
              <p className={`text-xs ${plColor}`}>
                {summary.unrealized_pl_pct >= 0 ? "+" : ""}
                {fmt(summary.unrealized_pl_pct)}%
              </p>
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
              Importa datos desde el dashboard fiscal o añade transacciones
              manualmente.
            </CardDescription>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Posiciones ({positions.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Activo</TableHead>
                  <TableHead className="text-right">Cantidad</TableHead>
                  <TableHead className="text-right">Coste medio</TableHead>
                  <TableHead className="text-right">Precio actual</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead className="text-right">P&L</TableHead>
                  <TableHead className="text-right">Peso</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.map((p) => {
                  const plPositive =
                    p.unrealized_pl_eur != null && p.unrealized_pl_eur >= 0;
                  const plClass = plPositive
                    ? "text-emerald-600"
                    : "text-red-600";
                  return (
                    <TableRow
                      key={`${p.isin}-${p.broker}`}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() =>
                        router.push(`/portfolio/${encodeURIComponent(p.isin)}`)
                      }
                    >
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
                        {fmt(p.avg_cost_eur, 2)} €
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {p.current_price_eur
                          ? `${fmt(p.current_price_eur, 2)} €`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums font-medium">
                        {p.market_value_eur
                          ? `${fmt(p.market_value_eur)} €`
                          : "—"}
                      </TableCell>
                      <TableCell
                        className={`text-right tabular-nums ${plClass}`}
                      >
                        {p.unrealized_pl_eur != null ? (
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
                        {p.weight_pct ? `${fmt(p.weight_pct, 1)}%` : "—"}
                      </TableCell>
                    </TableRow>
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
