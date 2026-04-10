"use client";

import type { CrossValidationResult } from "@/lib/types";
import { formatEur } from "@/lib/format";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CheckCircle2, AlertTriangle, MinusCircle } from "lucide-react";

function StatusBadge({ status }: Readonly<{ status: string }>) {
  switch (status) {
    case "match":
      return (
        <Badge className="bg-green-500/15 text-green-400 border-green-500/30 gap-1">
          <CheckCircle2 className="h-3 w-3" />
          Match
        </Badge>
      );
    case "mismatch":
      return (
        <Badge className="bg-red-500/15 text-red-400 border-red-500/30 gap-1">
          <AlertTriangle className="h-3 w-3" />
          Diferencia
        </Badge>
      );
    default:
      return (
        <Badge variant="secondary" className="gap-1">
          <MinusCircle className="h-3 w-3" />
          Sin ref.
        </Badge>
      );
  }
}

export function CrossValidationTable({
  data,
}: Readonly<{ data: CrossValidationResult }>) {
  const { rows, total_match, total_mismatch, total_no_ref } = data;
  const total = total_match + total_mismatch + total_no_ref;

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Coincidencias</CardDescription>
            <CardTitle className="text-2xl text-green-400">
              {total_match}/{total}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Diferencias</CardDescription>
            <CardTitle className="text-2xl text-red-400">
              {total_mismatch}/{total}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Sin referencia TR</CardDescription>
            <CardTitle className="text-2xl text-muted-foreground">
              {total_no_ref}/{total}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Detail table */}
      <Card>
        <CardHeader>
          <CardTitle>
            Validación cruzada — Año fiscal {data.fiscal_year}
          </CardTitle>
          <CardDescription>
            Comparación de los importes calculados por FinView vs los datos de
            referencia del informe de Trade Republic. Para casillas
            multi-broker, se compara solo la parte de TR.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-20">Modelo</TableHead>
                  <TableHead className="w-20">Casilla</TableHead>
                  <TableHead>Descripción</TableHead>
                  <TableHead className="text-right">FinView (total)</TableHead>
                  <TableHead className="text-right">Comparado</TableHead>
                  <TableHead className="text-right">TR Referencia</TableHead>
                  <TableHead className="text-right">Diferencia</TableHead>
                  <TableHead className="w-28">Estado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={`${row.modelo}-${row.casilla}`}>
                    <TableCell className="font-mono text-muted-foreground">
                      {row.modelo}
                    </TableCell>
                    <TableCell className="font-mono font-medium">
                      {row.casilla}
                    </TableCell>
                    <TableCell>
                      <div>{row.description}</div>
                      {row.is_multi_broker && (
                        <div className="text-xs text-muted-foreground mt-1">
                          {row.brokers.map((b) => (
                            <span key={b.broker} className="mr-2">
                              {b.broker}: {formatEur(b.amount_eur)}
                            </span>
                          ))}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatEur(row.finview_amount)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {row.is_multi_broker ? (
                        <span
                          className="text-blue-400"
                          title="Solo la parte de TR (multi-broker)"
                        >
                          {formatEur(row.compare_amount)}
                        </span>
                      ) : (
                        formatEur(row.compare_amount)
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {row.tr_amount == null ? "—" : formatEur(row.tr_amount)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {row.difference == null ? (
                        "—"
                      ) : (
                        <span
                          className={
                            Number.parseFloat(row.difference) === 0
                              ? "text-green-400"
                              : "text-red-400"
                          }
                        >
                          {formatEur(row.difference)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
