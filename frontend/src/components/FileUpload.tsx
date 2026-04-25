"use client";

import { useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import {
  uploadTRReport,
  uploadDGReport,
  uploadIBKRReport,
  uploadINGReport,
  uploadBBVAReport,
  uploadEToroReport,
} from "@/lib/api";
import type { ImportResult, DataIssue } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Upload,
  FileUp,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Info,
} from "lucide-react";

type BrokerKey = "tr" | "degiro" | "ibkr" | "ing" | "bbva" | "etoro";
type UploadMapKey = "tr" | "degiro" | "ibkr" | "ing" | "etoro";

type BrokerConfig = {
  readonly key: BrokerKey;
  readonly label: string;
  readonly shortLabel: string;
  readonly accept: string;
  readonly color: string;
  readonly multi: boolean;
};

const BROKERS: BrokerConfig[] = [
  {
    key: "tr",
    label: "Trade Republic",
    shortLabel: "TR",
    accept: ".pdf,.csv",
    color: "bg-neutral-800 hover:bg-neutral-700 border-neutral-600",
    multi: false,
  },
  {
    key: "degiro",
    label: "DEGIRO",
    shortLabel: "DEGIRO",
    accept: ".pdf",
    color: "bg-orange-950/50 hover:bg-orange-900/50 border-orange-700/40",
    multi: false,
  },
  {
    key: "ibkr",
    label: "IBKR",
    shortLabel: "IBKR",
    accept: ".csv",
    color: "bg-red-950/50 hover:bg-red-900/50 border-red-700/40",
    multi: false,
  },
  {
    key: "ing",
    label: "ING",
    shortLabel: "ING",
    accept: ".pdf",
    color: "bg-orange-950/40 hover:bg-orange-900/40 border-orange-600/30",
    multi: false,
  },
  {
    key: "bbva",
    label: "BBVA",
    shortLabel: "BBVA",
    accept: ".pdf",
    color: "bg-blue-950/50 hover:bg-blue-900/50 border-blue-700/40",
    multi: true,
  },
  {
    key: "etoro",
    label: "eToro",
    shortLabel: "eToro",
    accept: ".xlsx",
    color: "bg-green-950/50 hover:bg-green-900/50 border-green-700/40",
    multi: false,
  },
];

interface FileUploadProps {
  readonly onImported: () => void;
}

function detectBroker(
  filename: string,
): "tr" | "degiro" | "ibkr" | "ing" | "bbva" | "etoro" | null {
  const lower = filename.toLowerCase();
  if (
    lower.startsWith("dg-") ||
    lower.includes("degiro") ||
    lower.includes("informe anual")
  )
    return "degiro";
  if (
    lower.startsWith("tr-") ||
    lower.includes("trade republic") ||
    lower.includes("tax_report") ||
    lower.includes("transaction export")
  )
    return "tr";
  if (
    lower.startsWith("ibkr") ||
    lower.includes("interactive") ||
    lower.includes("u1104")
  )
    return "ibkr";
  if (
    lower.includes("ing") ||
    lower.includes("información fiscal") ||
    lower.includes("informacion fiscal")
  )
    return "ing";
  if (lower.includes("bbva")) return "bbva";
  if (lower.includes("etoro") || lower.includes("account-statement"))
    return "etoro";
  return null;
}

export function FileUpload({ onImported }: FileUploadProps) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingBroker, setLoadingBroker] = useState(null as string | null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const brokerInputRefs = useRef({} as Record<string, HTMLInputElement | null>);

  const notifyResult = useCallback(
    (res: ImportResult) => {
      if (res.status === "success" || res.status === "replaced") {
        toast.success(
          `${res.status === "replaced" ? "Reemplazado" : "Importado"} — Año fiscal ${res.fiscal_year}`,
          {
            description: res.counts
              ? `${res.counts.dividends} dividendos, ${res.counts.transactions} transacciones`
              : undefined,
          },
        );
        onImported();
      } else if (res.status === "duplicate") {
        toast.warning("Importación duplicada", { description: res.message });
      }
    },
    [onImported],
  );

  const uploadBroker = useCallback(async (file: File, broker: string) => {
    const uploadMap = {
      degiro: uploadDGReport,
      tr: uploadTRReport,
      ibkr: uploadIBKRReport,
      ing: uploadINGReport,
      etoro: uploadEToroReport,
    };
    const upload = uploadMap[broker as UploadMapKey];
    return upload(file);
  }, []);

  const handleFiles = useCallback(
    async (files: File[]) => {
      const invalidFile = files.find((f) => {
        const ext = f.name.toLowerCase();
        return (
          !ext.endsWith(".pdf") &&
          !ext.endsWith(".csv") &&
          !ext.endsWith(".xlsx")
        );
      });
      if (invalidFile) {
        setError("Solo se aceptan archivos PDF, CSV o XLSX");
        return;
      }

      const brokers = files.map((f) => detectBroker(f.name));
      const hasBBVA = brokers.includes("bbva");

      setLoading(true);
      setLoadingBroker(null);
      setError(null);
      setResult(null);

      try {
        let res: ImportResult;
        if (hasBBVA) {
          const bbvaFiles = files.filter(
            (f) => detectBroker(f.name) === "bbva",
          );
          if (bbvaFiles.length === 0 || bbvaFiles.length > 3) {
            setError("BBVA: selecciona entre 1 y 3 archivos PDF del mismo año");
            return;
          }
          res = await uploadBBVAReport(bbvaFiles);
        } else {
          const file = files[0];
          const broker = detectBroker(file.name);
          if (!broker) {
            setError(
              "No se pudo detectar el broker. El archivo debe contener 'TR-', 'DG-', 'IBKR', 'ING', 'BBVA' o 'eToro'.",
            );
            return;
          }
          res = await uploadBroker(file, broker);
        }
        setResult(res);
        notifyResult(res);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Error desconocido";
        setError(msg);
        toast.error("Error de importación", { description: msg });
      } finally {
        setLoading(false);
      }
    },
    [onImported, notifyResult, uploadBroker],
  );

  return (
    <Card
      className={`border-2 border-dashed transition-colors ${
        dragging
          ? "border-primary bg-primary/5"
          : "border-border hover:border-muted-foreground/50"
      }`}
    >
      <CardContent
        className="p-8 text-center"
        role="region"
        aria-label="Zona de carga de archivos"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const files = Array.from(e.dataTransfer.files);
          if (files.length > 0) handleFiles(files);
        }}
      >
        <div className="mb-3">
          <Upload className="h-10 w-10 mx-auto text-muted-foreground" />
        </div>
        <p className="text-muted-foreground mb-4 text-sm">
          Arrastra aquí archivos de Trade Republic (PDF o CSV), DEGIRO (PDF),
          IBKR (CSV), ING (PDF), BBVA (1-3 PDFs) o eToro (XLSX)
        </p>
        <input
          type="file"
          accept=".pdf,.csv,.xlsx"
          multiple
          id="file-upload"
          aria-label="Seleccionar archivos"
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length > 0) handleFiles(files);
          }}
        />
        <Button
          variant="default"
          onClick={() => document.getElementById("file-upload")?.click()}
          disabled={loading}
        >
          {loading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Procesando...
            </>
          ) : (
            <>
              <FileUp className="mr-2 h-4 w-4" />
              Seleccionar archivos
            </>
          )}
        </Button>

        {/* Broker-specific buttons */}
        <div className="mt-6 border-t border-border pt-5">
          <p className="text-xs text-muted-foreground mb-3">
            O selecciona directamente por broker:
          </p>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            {BROKERS.map((b) => (
              <div key={b.key}>
                <input
                  type="file"
                  accept={b.accept}
                  multiple={b.multi}
                  className="hidden"
                  aria-label={`Importar archivo de ${b.label}`}
                  ref={(el) => {
                    brokerInputRefs.current[b.key] = el;
                  }}
                  onChange={async (e) => {
                    const files = Array.from(e.target.files ?? []);
                    if (files.length === 0) return;
                    setLoading(true);
                    setLoadingBroker(b.key);
                    setError(null);
                    setResult(null);
                    try {
                      let res: ImportResult;
                      if (b.key === "bbva") {
                        res = await uploadBBVAReport(files);
                      } else {
                        res = await uploadBroker(files[0], b.key);
                      }
                      setResult(res);
                      notifyResult(res);
                    } catch (err: unknown) {
                      const msg =
                        err instanceof Error
                          ? err.message
                          : "Error desconocido";
                      setError(msg);
                      toast.error("Error de importación", { description: msg });
                    } finally {
                      setLoading(false);
                      setLoadingBroker(null);
                      e.target.value = "";
                    }
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  className={`w-full text-xs border ${b.color}`}
                  disabled={loading}
                  onClick={() => brokerInputRefs.current[b.key]?.click()}
                >
                  {loadingBroker === b.key ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <>
                      <span className="font-medium">{b.shortLabel}</span>
                      <span className="text-muted-foreground ml-1 hidden sm:inline">
                        {b.accept.replace(".", "").toUpperCase()}
                      </span>
                    </>
                  )}
                </Button>
              </div>
            ))}
          </div>
        </div>

        {(result?.status === "success" || result?.status === "replaced") && (
          <div className="mt-4 p-4 bg-green-500/10 border border-green-500/20 rounded-lg text-sm">
            <p className="text-green-400 font-medium flex items-center justify-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              {result.status === "replaced" ? "Reemplazado" : "Importado"} — Año
              fiscal {result.fiscal_year}
            </p>
            {result.status === "replaced" && result.message && (
              <p className="mt-1 text-yellow-400/80 text-xs">
                {result.message}
              </p>
            )}
            {result.counts && (
              <div className="mt-2 flex gap-4 justify-center text-muted-foreground text-xs">
                <span>{result.counts.dividends} dividendos</span>
                <span>{result.counts.transactions} transacciones</span>
                <span>{result.counts.capital_gains} ganancias</span>
                <span>{result.counts.casillas} casillas</span>
              </div>
            )}
            {result.issues && result.issues.length > 0 && (
              <div className="mt-3 border-t border-green-500/20 pt-3">
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  Supervisor de datos — {result.issues.length} aviso
                  {result.issues.length === 1 ? "" : "s"}
                </p>
                <div className="space-y-1.5 text-left">
                  {result.issues.map((issue: DataIssue) => {
                    const isResolved = issue.status === "auto_resolved";
                    const isWarning = issue.severity === "warning";
                    let colorClass =
                      "bg-blue-500/10 border border-blue-500/20 text-blue-300";
                    let IssueIcon = Info;
                    if (isResolved) {
                      colorClass =
                        "bg-green-500/10 border border-green-500/20 text-green-300";
                      IssueIcon = CheckCircle2;
                    } else if (isWarning) {
                      colorClass =
                        "bg-yellow-500/10 border border-yellow-500/20 text-yellow-300";
                      IssueIcon = AlertTriangle;
                    }
                    return (
                      <div
                        key={issue.id}
                        className={`text-xs px-3 py-2 rounded ${colorClass}`}
                      >
                        <span className="font-medium flex items-center gap-1">
                          <IssueIcon className="h-3 w-3" />
                          {issue.issue_type.replaceAll("_", " ")}
                        </span>
                        {issue.isin && (
                          <span className="text-muted-foreground ml-1">
                            ({issue.isin})
                          </span>
                        )}
                        <p className="mt-0.5 text-muted-foreground">
                          {issue.description}
                        </p>
                        {issue.auto_resolution && (
                          <p className="mt-0.5 italic text-green-400/70">
                            {issue.auto_resolution}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {result?.status === "duplicate" && (
          <p className="mt-4 text-yellow-400 text-sm flex items-center justify-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {result.message}
          </p>
        )}

        {error && <p className="mt-4 text-destructive text-sm">{error}</p>}
      </CardContent>
    </Card>
  );
}
