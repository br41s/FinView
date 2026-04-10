"use client";

import { useState } from "react";
import type { YearlyMetrics } from "@/lib/types";
import { formatEur, plColor } from "@/lib/format";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

type SortKey = keyof YearlyMetrics;

export function YearlyComparisonView({
  data,
}: Readonly<{ data: YearlyMetrics[] }>) {
  const [sortKey, setSortKey] = useState<SortKey>("fiscal_year");
  const [sortAsc, setSortAsc] = useState(true);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(key === "fiscal_year");
    }
  };

  const sorted = [...data].sort((a, b) => {
    const av =
      typeof a[sortKey] === "string"
        ? Number.parseFloat(a[sortKey] as string)
        : (a[sortKey] as number);
    const bv =
      typeof b[sortKey] === "string"
        ? Number.parseFloat(b[sortKey] as string)
        : (b[sortKey] as number);
    return sortAsc ? av - bv : bv - av;
  });

  const arrow = (key: SortKey) => {
    if (sortKey !== key) return "";
    return sortAsc ? " ↑" : " ↓";
  };

  // Chart data
  const chartData = data.map((y) => ({
    year: String(y.fiscal_year),
    Dividendos: Number.parseFloat(y.dividends_gross),
    Ganancias: Number.parseFloat(y.gains),
    Pérdidas: Math.abs(Number.parseFloat(y.losses)),
    Retenciones: Math.abs(Number.parseFloat(y.withholdings)),
  }));

  // Totals
  const totals = data.reduce(
    (acc, y) => ({
      dividends: acc.dividends + Number.parseFloat(y.dividends_gross),
      gains: acc.gains + Number.parseFloat(y.gains),
      losses: acc.losses + Number.parseFloat(y.losses),
      net: acc.net + Number.parseFloat(y.net_capital),
      withholdings: acc.withholdings + Number.parseFloat(y.withholdings),
    }),
    { dividends: 0, gains: 0, losses: 0, net: 0, withholdings: 0 },
  );

  return (
    <div className="space-y-6">
      {/* Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Evolución anual</CardTitle>
          <CardDescription>
            Comparativa de dividendos, ganancias y pérdidas por año fiscal
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="hsl(var(--border))"
              />
              <XAxis
                dataKey="year"
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <YAxis
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
                tickFormatter={(v: number) =>
                  v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)
                }
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                  color: "hsl(var(--foreground))",
                }}
                formatter={(value) => formatEur(Number(value))}
              />
              <Legend />
              <Bar dataKey="Dividendos" fill="#22c55e" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Ganancias" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Pérdidas" fill="#ef4444" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Retenciones" fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle>Detalle por año fiscal</CardTitle>
          <CardDescription>
            Métricas agregadas de {data.length} años fiscales (
            {data.length > 0 ? data[0].fiscal_year : "—"} –{" "}
            {data.at(-1)?.fiscal_year ?? "—"})
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                {(
                  [
                    ["fiscal_year", "Año"],
                    ["dividends_gross", "Dividendos brutos"],
                    ["gains", "Ganancias"],
                    ["losses", "Pérdidas"],
                    ["net_capital", "Neto capital"],
                    ["withholdings", "Retenciones"],
                    ["brokers", "Brokers"],
                    ["positions", "Posiciones"],
                  ] as [SortKey, string][]
                ).map(([key, label]) => (
                  <TableHead
                    key={key}
                    className={`cursor-pointer select-none hover:text-foreground ${key === "fiscal_year" ? "" : "text-right"}`}
                    onClick={() => handleSort(key)}
                  >
                    {label}
                    {arrow(key)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((y) => (
                <TableRow key={y.fiscal_year}>
                  <TableCell className="font-medium">{y.fiscal_year}</TableCell>
                  <TableCell className="text-right font-mono text-green-400">
                    {formatEur(y.dividends_gross)}
                  </TableCell>
                  <TableCell
                    className={`text-right font-mono ${plColor(y.gains)}`}
                  >
                    {formatEur(y.gains)}
                  </TableCell>
                  <TableCell
                    className={`text-right font-mono ${plColor(y.losses)}`}
                  >
                    {formatEur(y.losses)}
                  </TableCell>
                  <TableCell
                    className={`text-right font-mono ${plColor(y.net_capital)}`}
                  >
                    {formatEur(y.net_capital)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-amber-400">
                    {formatEur(y.withholdings)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant="secondary">{y.brokers}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant="outline">{y.positions}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow className="font-semibold">
                <TableCell>Total</TableCell>
                <TableCell className="text-right font-mono text-green-400">
                  {formatEur(totals.dividends)}
                </TableCell>
                <TableCell
                  className={`text-right font-mono ${plColor(totals.gains)}`}
                >
                  {formatEur(totals.gains)}
                </TableCell>
                <TableCell
                  className={`text-right font-mono ${plColor(totals.losses)}`}
                >
                  {formatEur(totals.losses)}
                </TableCell>
                <TableCell
                  className={`text-right font-mono ${plColor(totals.net)}`}
                >
                  {formatEur(totals.net)}
                </TableCell>
                <TableCell className="text-right font-mono text-amber-400">
                  {formatEur(totals.withholdings)}
                </TableCell>
                <TableCell />
                <TableCell />
              </TableRow>
            </TableFooter>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
