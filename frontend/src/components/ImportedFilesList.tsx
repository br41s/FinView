"use client";

import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { api, deleteImport, deleteAllImports } from "@/lib/api";
import type { ImportRecord } from "@/lib/types";
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
import { Trash2, FileText, Loader2 } from "lucide-react";

const BROKER_LABELS: Record<string, string> = {
  tr: "Trade Republic",
  degiro: "DEGIRO",
  ibkr: "IBKR",
  ing: "ING",
  bbva: "BBVA",
  etoro: "eToro",
};

const BROKER_COLORS: Record<string, string> = {
  tr: "bg-blue-500/15 text-blue-400",
  degiro: "bg-green-500/15 text-green-400",
  ibkr: "bg-red-500/15 text-red-400",
  ing: "bg-orange-500/15 text-orange-400",
  bbva: "bg-cyan-500/15 text-cyan-400",
  etoro: "bg-purple-500/15 text-purple-400",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ImportedFilesList({
  onDeleted,
}: Readonly<{ onDeleted: () => void }>) {
  const [records, setRecords] = useState<ImportRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deletingAll, setDeletingAll] = useState(false);

  // A promise chain rather than async/await: every setState runs inside a
  // continuation, so the mount effect can call this synchronously.
  const loadRecords = useCallback(
    () =>
      api
        .imports()
        .then((data) => setRecords(data as ImportRecord[]))
        .catch(() => toast.error("Error al cargar importaciones"))
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const handleDelete = useCallback(
    async (record: ImportRecord) => {
      const confirmed = window.confirm(
        `¿Eliminar "${record.filename}"?\n\nSe borrarán todas las transacciones, casillas y datos asociados a esta importación.`,
      );
      if (!confirmed) return;

      setDeletingId(record.id);
      try {
        await deleteImport(record.id);
        toast.success("Importación eliminada", {
          description: `${record.filename} (${record.fiscal_year ?? "—"})`,
        });
        await loadRecords();
        onDeleted();
      } catch {
        toast.error("Error al eliminar importación");
      } finally {
        setDeletingId(null);
      }
    },
    [loadRecords, onDeleted],
  );

  const handleDeleteAll = useCallback(async () => {
    const confirmed = window.confirm(
      "¿Borrar TODOS los archivos importados?\n\nSe eliminarán todas las transacciones, posiciones, casillas y datos de todos los brokers. Esta acción no se puede deshacer.",
    );
    if (!confirmed) return;

    setDeletingAll(true);
    try {
      await deleteAllImports();
      toast.success("Todos los datos eliminados");
      await loadRecords();
      onDeleted();
    } catch {
      toast.error("Error al eliminar todos los datos");
    } finally {
      setDeletingAll(false);
    }
  }, [loadRecords, onDeleted]);

  // Group records by fiscal year
  const byYear = records.reduce<Record<number, ImportRecord[]>>((acc, r) => {
    const year = r.fiscal_year ?? 0;
    if (!acc[year]) acc[year] = [];
    acc[year].push(r);
    return acc;
  }, {});

  const sortedYears = Object.keys(byYear)
    .map(Number)
    .sort((a, b) => b - a);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Cargando importaciones…
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground text-sm">
        <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
        No hay archivos importados
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button
          variant="destructive"
          size="sm"
          onClick={handleDeleteAll}
          disabled={deletingAll || deletingId !== null}
        >
          {deletingAll ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="mr-2 h-4 w-4" />
          )}
          Borrar todo
        </Button>
      </div>
      {sortedYears.map((year) => (
        <div key={year}>
          <h3 className="text-sm font-medium text-muted-foreground mb-2">
            {year === 0 ? "Sin año fiscal" : `Año fiscal ${year}`}
            <span className="ml-2 text-xs opacity-60">
              ({byYear[year].length}{" "}
              {byYear[year].length === 1 ? "archivo" : "archivos"})
            </span>
          </h3>
          <div className="overflow-x-auto rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Archivo</TableHead>
                  <TableHead>Broker</TableHead>
                  <TableHead className="hidden sm:table-cell">
                    Registros
                  </TableHead>
                  <TableHead className="hidden sm:table-cell">
                    Importado
                  </TableHead>
                  <TableHead className="w-15" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {byYear[year].map((record) => (
                  <TableRow key={record.id}>
                    <TableCell className="font-mono text-xs max-w-50 truncate">
                      {record.filename}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={
                          BROKER_COLORS[record.broker.toLowerCase()] ??
                          "bg-muted text-muted-foreground"
                        }
                      >
                        {BROKER_LABELS[record.broker.toLowerCase()] ??
                          record.broker}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-muted-foreground">
                      {record.record_count}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-muted-foreground text-xs">
                      {formatDate(record.imported_at)}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => handleDelete(record)}
                        disabled={deletingId === record.id}
                        title="Eliminar importación"
                      >
                        {deletingId === record.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      ))}
    </div>
  );
}
