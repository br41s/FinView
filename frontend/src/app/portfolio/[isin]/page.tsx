"use client";

import { useEffect, useState, Suspense } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
} from "lucide-react";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

interface AccountBreakdown {
  broker: string;
  account_id: number;
  quantity: number;
  cost_eur: number;
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

interface PositionDetail {
  isin: string;
  name: string;
  ticker: string | null;
  country: string | null;
  total_quantity: number;
  avg_cost_eur: number;
  total_cost_eur: number;
  current_price_eur: number | null;
  market_value_eur: number;
  unrealized_pl_eur: number;
  unrealized_pl_pct: number;
  accounts: AccountBreakdown[];
  transactions: TxHistory[];
}

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("es-ES", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
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

function PositionDetailContent() {
  const params = useParams();
  const router = useRouter();
  const isin = decodeURIComponent(params.isin as string);
  const [detail, setDetail] = useState<PositionDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = (await api.portfolio.positionDetail(
          isin,
        )) as PositionDetail;
        setDetail(data);
      } catch (e) {
        console.error("Failed to load position:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [isin]);

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 sm:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="p-6 text-center">
        <p className="text-muted-foreground">Posición no encontrada</p>
        <Button
          variant="outline"
          className="mt-4"
          onClick={() => router.push("/portfolio")}
        >
          Volver a cartera
        </Button>
      </div>
    );
  }

  const plPositive = detail.unrealized_pl_eur >= 0;
  const plColor = plPositive ? "text-emerald-600" : "text-red-600";
  const PlIcon = plPositive ? ArrowUpRight : ArrowDownRight;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => router.push("/portfolio")}
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              {detail.ticker || detail.isin}
            </h1>
            {detail.country && (
              <Badge variant="outline">{detail.country}</Badge>
            )}
          </div>
          <p className="text-muted-foreground">{detail.name}</p>
          <p className="text-xs text-muted-foreground mt-1">
            ISIN: {detail.isin}
          </p>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Posición</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {fmt(detail.total_quantity, 2)}
            </div>
            <p className="text-xs text-muted-foreground">
              unidades en {detail.accounts.length} cuenta
              {detail.accounts.length !== 1 && "s"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Precio actual</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {detail.current_price_eur
                ? `${fmt(detail.current_price_eur)} €`
                : "—"}
            </div>
            <p className="text-xs text-muted-foreground">
              Coste medio: {fmt(detail.avg_cost_eur)} €
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Valor</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {fmt(detail.market_value_eur)} €
            </div>
            <p className="text-xs text-muted-foreground">
              Invertido: {fmt(detail.total_cost_eur)} €
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-1">
              P&L
              <PlIcon className={`h-4 w-4 ${plColor}`} />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${plColor}`}>
              {plPositive ? "+" : ""}
              {fmt(detail.unrealized_pl_eur)} €
            </div>
            <p className={`text-xs ${plColor}`}>
              {plPositive ? "+" : ""}
              {fmt(detail.unrealized_pl_pct)}%
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Per-Account Breakdown */}
      {detail.accounts.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle>Distribución por cuenta</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Broker</TableHead>
                  <TableHead className="text-right">Cantidad</TableHead>
                  <TableHead className="text-right">Coste</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.accounts.map((a) => (
                  <TableRow key={a.account_id}>
                    <TableCell>
                      <Badge variant="outline">{a.broker}</Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmt(a.quantity)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmt(a.cost_eur)} €
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {a.value_eur ? `${fmt(a.value_eur)} €` : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Transaction History */}
      <Card>
        <CardHeader>
          <CardTitle>
            Historial de transacciones ({detail.transactions.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {detail.transactions.length === 0 ? (
            <div className="flex flex-col items-center py-8">
              <TrendingUp className="h-8 w-8 text-muted-foreground mb-2" />
              <p className="text-muted-foreground">
                No hay transacciones registradas
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Fecha</TableHead>
                  <TableHead className="text-right">Cantidad</TableHead>
                  <TableHead className="text-right">Precio</TableHead>
                  <TableHead className="text-right">Neto (EUR)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.transactions.map((tx) => (
                  <TableRow key={tx.id}>
                    <TableCell>
                      <Badge
                        className={
                          TX_COLORS[tx.type] || "bg-gray-100 text-gray-700"
                        }
                      >
                        {TX_LABELS[tx.type] || tx.type}
                      </Badge>
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {new Date(tx.date).toLocaleDateString("es-ES")}
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
        </CardContent>
      </Card>
    </div>
  );
}

export default function PositionDetailPage() {
  return (
    <Suspense
      fallback={
        <div className="p-6">
          <Skeleton className="h-8 w-64" />
        </div>
      }
    >
      <PositionDetailContent />
    </Suspense>
  );
}
